"""Expose the harness tool surface as an MCP server over stdio.

This is the integration point for GitHub Copilot agent mode (in IntelliJ
or VS Code), Claude Desktop, Cline, Goose, and any other MCP client.

What is exposed:
- The full tool registry (filesystem, bash, etc.)
- Subject to the same PermissionPolicy as the standalone agent

What is NOT exposed:
- The Ollama model itself (the consuming client brings its own brain)
- The agent loop

Use `harness mcp-serve --profile config/profiles/dev.yaml` to start.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent
from mcp.types import Tool as MCPTool

from harness.permissions import PermissionPolicy
from harness.sandbox import Sandbox, SandboxConfig
from harness.tools import ToolRegistry
from harness.tools.bash import build_bash_tool
from harness.tools.concourse import ConcourseConfig, build_concourse_tools
from harness.tools.dynatrace import DynatraceConfig, build_dynatrace_tools
from harness.tools.filesystem import build_filesystem_tools
from harness.tools.jacoco import build_jacoco_tool
from harness.tools.kubernetes import KubernetesConfig, build_kubernetes_tools
from harness.tools.rabbitmq import RabbitMQConfig, build_rabbitmq_tools
from harness.tools.runbooks import RunbooksConfig, build_runbooks_tools
from harness.tools.skills import SkillsConfig, build_skills_tools
from harness.tools.sonarqube import SonarQubeConfig, build_sonarqube_tools

# Filesystem and bash tools are redundant in MCP mode: the consuming client
# (Claude Code, Copilot, Cline…) already has its own, with its own sandbox.
# They are only registered when explicitly requested via expose_filesystem.

logger = logging.getLogger(__name__)


def _build_registry(profile: dict[str, Any], workspace: Path) -> tuple[
    ToolRegistry, PermissionPolicy
]:
    sandbox_cfg = profile.get("sandbox", {})
    sandbox = Sandbox(
        SandboxConfig(
            backend=sandbox_cfg.get("backend", "bubblewrap"),
            allow_network=sandbox_cfg.get("allow_network", False),
            max_output_bytes=sandbox_cfg.get("max_output_bytes", 16 * 1024),
        )
    )
    registry = ToolRegistry()

    # Filesystem + bash: only when the profile explicitly opts in.
    # In MCP mode the client already has its own Read/Write/Edit/Glob/Bash.
    if profile.get("mcp", {}).get("expose_filesystem", False):
        registry.register_many(build_filesystem_tools(workspace))
        registry.register(build_bash_tool(sandbox, workspace))
        registry.register(build_jacoco_tool(workspace))

    ops_tools_cfg = profile.get("ops_tools", {})
    if ops_tools_cfg.get("dynatrace", {}).get("enabled"):
        registry.register_many(
            build_dynatrace_tools(
                DynatraceConfig.from_dict(ops_tools_cfg["dynatrace"])
            )
        )
    if ops_tools_cfg.get("kubernetes", {}).get("enabled"):
        registry.register_many(
            build_kubernetes_tools(
                KubernetesConfig.from_dict(ops_tools_cfg["kubernetes"])
            )
        )
    if ops_tools_cfg.get("runbooks", {}).get("enabled"):
        registry.register_many(
            build_runbooks_tools(
                RunbooksConfig.from_dict(ops_tools_cfg["runbooks"])
            )
        )
    if ops_tools_cfg.get("concourse", {}).get("enabled"):
        registry.register_many(
            build_concourse_tools(
                ConcourseConfig.from_dict(ops_tools_cfg["concourse"])
            )
        )
    if ops_tools_cfg.get("skills", {}).get("enabled"):
        _repo_root = Path(__file__).resolve().parent.parent.parent.parent
        registry.register_many(
            build_skills_tools(
                SkillsConfig.from_dict(ops_tools_cfg["skills"], base_dir=_repo_root)
            )
        )
    if ops_tools_cfg.get("sonarqube", {}).get("enabled"):
        registry.register_many(
            build_sonarqube_tools(
                SonarQubeConfig.from_dict(ops_tools_cfg["sonarqube"])
            )
        )
    if ops_tools_cfg.get("rabbitmq", {}).get("enabled"):
        registry.register_many(
            build_rabbitmq_tools(
                RabbitMQConfig.from_dict(ops_tools_cfg["rabbitmq"])
            )
        )

    permissions = PermissionPolicy.from_dict(
        profile=profile.get("name", "mcp"),
        data=profile.get("permissions", {}),
    )
    return registry, permissions


def serve_stdio(profile: dict[str, Any], workspace: Path) -> None:
    """Run the MCP server over stdio. Blocks until the client disconnects."""
    registry, permissions = _build_registry(profile, workspace)
    server: Server = Server("agent-harness")

    @server.list_tools()
    async def list_tools() -> list[MCPTool]:
        return [
            MCPTool(
                name=t.name,
                description=t.description,
                inputSchema=t.parameters,
            )
            for t in registry.all()
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        decision = permissions.check(name, arguments)
        if decision == "deny":
            return [
                TextContent(
                    type="text",
                    text=f"[ERROR] permission denied by policy for tool {name}",
                )
            ]
        # In MCP mode, "ask" decisions are escalated to the client by
        # returning an explicit prompt. The client is expected to surface it.
        if decision == "ask":
            return [
                TextContent(
                    type="text",
                    text=(
                        f"[CONFIRMATION REQUIRED] tool {name} with args "
                        f"{arguments}. Re-call with the explicit "
                        "`__confirmed__: true` flag in arguments to proceed."
                    ),
                )
                if not arguments.get("__confirmed__")
                else TextContent(type="text", text="confirmed")
            ]
        result = registry.dispatch(name, arguments)
        return [TextContent(type="text", text=result.to_message_content())]

    async def main() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(main())
