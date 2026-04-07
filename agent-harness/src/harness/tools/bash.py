"""Bash execution tool, delegating isolation to the sandbox module."""

from __future__ import annotations

from pathlib import Path

from harness.sandbox import Sandbox
from harness.tools.base import Tool, ToolResult, tool


def build_bash_tool(sandbox: Sandbox, workspace: Path) -> Tool:
    """Build a bash tool bound to a sandbox and workspace."""

    @tool(
        name="bash",
        description=(
            "Execute a shell command inside the sandbox. The command runs "
            "with the workspace as CWD. Use this for git, build tools, "
            "linters, test runners. Avoid commands that mutate state outside "
            "the workspace; they will be refused. Output is truncated at 16 "
            "KiB; redirect to a file if you need more."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout_s": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 600,
                    "default": 60,
                },
            },
            "required": ["command"],
        },
        risk="dangerous",
        side_effects={"exec", "read", "write"},
    )
    def bash(args: dict) -> ToolResult:
        result = sandbox.run(
            command=args["command"],
            cwd=workspace,
            timeout_s=int(args.get("timeout_s", 60)),
        )
        body = (
            f"$ {args['command']}\n"
            f"--- exit code: {result.exit_code}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}\n"
        )
        return ToolResult(
            ok=(result.exit_code == 0),
            content=body,
            metadata={
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )

    return bash
