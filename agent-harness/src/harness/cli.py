"""CLI entry point.

Sub-commands:
- `harness run`            : interactive agent session
- `harness mcp-serve`      : expose the harness as an MCP server (stdio)
- `harness openai-serve`   : expose an OpenAI-compatible HTTP endpoint
- `harness eval`           : run the eval suite
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.prompt import Confirm

from harness.agent import Agent, AgentConfig
from harness.memory import Memory
from harness.model import ModelClient, OllamaClient
from harness.observability import ObservabilityConfig, setup_observability
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

app = typer.Typer(help="Local agent harness around Gemma (Ollama).")
console = Console()


DEVOPS_PRACTICES = """
## DevOps practices — mandatory at every iteration

Follow the local pipeline before every push, no exceptions:
1. Code       — implement the change
2. Lint       — 0 errors (ruff / eslint / tsc)
3. Unit tests — maintain existing + add tests for new code (fix → regression test)
4. Integ/E2E  — if applicable
5. Docs       — update ALL impacted files (README, SKILL.md, CLAUDE.md, CHANGELOG)
6. Commit     — conventional commit message (<type>(<scope>): <description>)
7. Push       — only when pipeline is green

Imperative rules:
- Never push without all tests passing.
- Never push with lint errors.
- Always maintain AND increase tests — each feat/fix adds tests, never regress.
- Always update docs at each iteration.
- One commit = one logical change.
- Never commit secrets (.env, tokens, credentials).
- Never hand back control mid-pipeline — finish all steps.
- Always propose next steps at each milestone.
- Never defer a problem — fix flaky tests, warnings, fragilities immediately.

Commit types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert.
Breaking changes: add ! after type, add BREAKING CHANGE footer.

## SonarQube iteration loop — when sonarqube tools are available

When a sonarqube_quality_gate or sonarqube_issues tool is available, apply
this iterative workflow after each significant code change:

1. CHECK  — call sonarqube_quality_gate to get the gate status
2. If gate is OK → done, move on
3. If gate is ERROR/WARN → call sonarqube_issues to get the failing issues
4. FIX    — fix issues in priority order: BLOCKER → CRITICAL → MAJOR → MINOR
5. VERIFY — re-run lint + tests after each fix (never break existing tests)
6. LOOP   — repeat from step 1 (max 5 iterations)

Priority rules:
- BLOCKER/CRITICAL: fix in source code immediately
- VULNERABILITY/SECURITY_HOTSPOT: upgrade dependency or fix code, document if suppressed
- MAJOR: fix in source code
- MINOR: fix or accept with justification

Exit criteria: quality gate OK, 0 BLOCKER, 0 CRITICAL.
Do NOT fix issues on generated code (JAXB, MapStruct, Lombok).

## Java testing — when jacoco_coverage tool is available

When writing or improving Java tests:
1. Call jacoco_coverage to identify classes with most missed branches
2. Write tests targeting those classes first (highest impact)
3. Re-run `mvn verify -Pjacoco -DskipITs` via bash, then call jacoco_coverage again
4. Iterate until coverage meets the threshold configured in pom.xml

Conventions:
- JUnit 5 + AssertJ + Mockito — never JUnit 4
- @DisplayName on every test (in French), @Nested by method under test
- @Tag("unit") or @Tag("integration") on every test class
- Minimum 2 meaningful assertions per test
- Never modify production code (src/main/java) when writing tests
- Never delete an existing passing test
- Exclude generated code (JAXB, MapStruct, Lombok) from coverage
"""

SYSTEM_PROMPT_CODING = """You are a coding agent operating in a developer's
workspace. You have access to filesystem and bash tools that run inside a
sandbox. Work step by step:

1. Understand the task before acting.
2. Read relevant files before editing them.
3. Make small, reversible changes; verify with tests when possible.
4. Never invent file contents or tool results.
5. If you are unsure, ask the user.

When invoking a tool, choose the most specific one available.
If a search_rag tool is available, use it to retrieve domain expertise
(Angular, Quarkus, Oracle, Concourse, Dynatrace, DevOps, testing, etc.)
before making technology-specific decisions.
NEVER read files in the skills/ directory directly. Use search_rag
for domain knowledge. If search_rag is not available, do not attempt
to access skills/ content by any other means.
""" + DEVOPS_PRACTICES

OPS_PRACTICES = """
## OPS practices — observe before acting

Motto: do not water the desert — a warning that has always existed and
causes no problem is not a problem.

Classification grid:
- RED ERROR    — uncaught exception, test failure, build failure → fix immediately
- ORANGE WARN  — deprecated API in use, abnormal timeout, retry exhausted → fix if real impact
- YELLOW SLOW  — Maven phase > 2x baseline, test > 10s, GC pause > 1s → investigate
- WHITE NOISE  — JPA/Hibernate deprecations on generated code, WireMock port warnings,
                 Cucumber publish reminder, PKIX metadata warnings → IGNORE

Remediation rules:
- Fix: real test failures, new OWASP CVEs, Sonar blockers/majors, recurring timeouts
- Skip: warnings on generated code, deprecations outside your control, info messages

## SRE — when sre_slo_status tool is available

When investigating reliability or preparing a release:
1. Call sre_slo_status to check all SLOs
2. Focus on SLOs with status WARNING or FAILURE
3. Check error budget remaining — if < 20%, reliability work takes priority over features
4. For each failing SLO: identify the SLI, find the root cause (DQL/logs/metrics)

SRE principles:
- Alert on SLO burn rate, never on raw metrics
- Error budget healthy → ship features; error budget exhausted → prioritize reliability
- Every alert must have a runbook (use search_runbooks)
- Prefer 4 golden signals: latency, traffic, errors, saturation
"""

SYSTEM_PROMPT_OPS = """You are an operations assistant. By default you
operate in READ-ONLY mode: you observe and diagnose, you do not mutate
production state without explicit confirmation. Always cite the source
(file, log line, metric query) for any factual claim. Prefer DQL queries
over guesswork. When asked to take a mutating action, restate the action
and its blast radius before proposing to execute it.
If a search_rag tool is available, use it to retrieve domain expertise
(Dynatrace DQL, Kubernetes, Oracle, Concourse pipelines, etc.) before
making technology-specific decisions.
NEVER read files in the skills/ directory directly. Use search_rag
for domain knowledge. If search_rag is not available, do not attempt
to access skills/ content by any other means.
""" + OPS_PRACTICES + DEVOPS_PRACTICES


def _load_profile(profile_path: Path) -> dict[str, Any]:
    if not profile_path.exists():
        raise typer.BadParameter(f"profile not found: {profile_path}")
    with profile_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_agent(profile: dict[str, Any], workspace: Path) -> Agent:
    logging.basicConfig(level=profile.get("log_level", "INFO"))

    model_cfg = profile["model"]
    provider = model_cfg.get("provider", "ollama")
    model: ModelClient
    if provider == "anthropic":
        from harness.anthropic_client import AnthropicClient

        model = AnthropicClient(
            model=model_cfg["name"],
            temperature=model_cfg.get("temperature", 0.2),
            max_tokens=model_cfg.get("max_tokens", 4096),
        )
    elif provider == "openai":
        from harness.openai_client import OpenAIClient

        model = OpenAIClient(
            model=model_cfg["name"],
            base_url=model_cfg.get("endpoint", "https://api.openai.com/v1"),
            api_key_env=model_cfg.get("api_key_env", "OPENAI_API_KEY"),
            temperature=model_cfg.get("temperature", 0.2),
            max_tokens=model_cfg.get("max_tokens", 4096),
        )
    else:
        model = OllamaClient(
            model=model_cfg["name"],
            endpoint=model_cfg.get("endpoint", "http://localhost:11434"),
            temperature=model_cfg.get("temperature", 0.2),
            num_ctx=model_cfg.get("num_ctx", 8192),
        )

    sandbox_cfg = profile.get("sandbox", {})
    sandbox = Sandbox(
        SandboxConfig(
            backend=sandbox_cfg.get("backend", "bubblewrap"),
            allow_network=sandbox_cfg.get("allow_network", False),
            max_output_bytes=sandbox_cfg.get("max_output_bytes", 16 * 1024),
            extra_ro_binds=sandbox_cfg.get("extra_ro_binds", []),
        )
    )

    tools = ToolRegistry()
    tools.register_many(build_filesystem_tools(workspace))
    tools.register(build_bash_tool(sandbox, workspace))
    tools.register(build_jacoco_tool(workspace))

    # Optional ops tools — wired only when enabled in the profile
    ops_tools_cfg = profile.get("ops_tools", {})
    if ops_tools_cfg.get("dynatrace", {}).get("enabled"):
        tools.register_many(
            build_dynatrace_tools(
                DynatraceConfig.from_dict(ops_tools_cfg["dynatrace"])
            )
        )
    if ops_tools_cfg.get("kubernetes", {}).get("enabled"):
        tools.register_many(
            build_kubernetes_tools(
                KubernetesConfig.from_dict(ops_tools_cfg["kubernetes"])
            )
        )
    if ops_tools_cfg.get("runbooks", {}).get("enabled"):
        tools.register_many(
            build_runbooks_tools(
                RunbooksConfig.from_dict(ops_tools_cfg["runbooks"])
            )
        )
    if ops_tools_cfg.get("concourse", {}).get("enabled"):
        tools.register_many(
            build_concourse_tools(
                ConcourseConfig.from_dict(ops_tools_cfg["concourse"])
            )
        )
    if ops_tools_cfg.get("skills", {}).get("enabled"):
        # Skills are part of the harness repo, not the workspace.
        # Resolve relative paths against the repo root (parent of agent-harness/).
        _repo_root = Path(__file__).resolve().parent.parent.parent.parent
        tools.register_many(
            build_skills_tools(
                SkillsConfig.from_dict(ops_tools_cfg["skills"], base_dir=_repo_root)
            )
        )
    if ops_tools_cfg.get("sonarqube", {}).get("enabled"):
        tools.register_many(
            build_sonarqube_tools(
                SonarQubeConfig.from_dict(ops_tools_cfg["sonarqube"])
            )
        )
    if ops_tools_cfg.get("rabbitmq", {}).get("enabled"):
        tools.register_many(
            build_rabbitmq_tools(
                RabbitMQConfig.from_dict(ops_tools_cfg["rabbitmq"])
            )
        )

    permissions = PermissionPolicy.from_dict(
        profile=profile.get("name", "unknown"),
        data=profile.get("permissions", {}),
    )

    obs_cfg = profile.get("observability", {})
    obs = setup_observability(
        ObservabilityConfig(
            enabled=obs_cfg.get("enabled", True),
            service_name=obs_cfg.get("service_name", "agent-harness"),
            otlp_endpoint=obs_cfg.get("otlp_endpoint"),
        )
    )

    profile_name = profile.get("profile_type", "coding")
    system_prompt = (
        SYSTEM_PROMPT_OPS if profile_name == "ops" else SYSTEM_PROMPT_CODING
    )
    memory = Memory(
        system_prompt=system_prompt,
        soft_budget_tokens=profile.get("memory", {}).get("soft_budget_tokens", 6000),
    )

    agent_cfg = profile.get("agent", {})
    config = AgentConfig(
        max_steps=agent_cfg.get("max_steps", 25),
        token_budget=agent_cfg.get("token_budget", 50_000),
        wall_clock_timeout_s=agent_cfg.get("wall_clock_timeout_s", 600),
    )

    def confirm(call: Any) -> bool:
        return Confirm.ask(
            f"[bold yellow]Allow tool[/] [cyan]{call.name}[/] with args "
            f"{call.arguments}?",
            default=True,
        )

    return Agent(
        model=model,
        tools=tools,
        permissions=permissions,
        memory=memory,
        observability=obs,
        config=config,
        confirm_callback=confirm,
    )


@app.command()
def run(
    profile: Path = typer.Option(
        Path("config/profiles/dev.yaml"), "--profile", "-p"
    ),
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w"),
    request: str = typer.Argument(..., help="The user request to send"),
) -> None:
    """Run a single agent session."""
    profile_data = _load_profile(profile)
    agent = _build_agent(profile_data, workspace)
    console.print(f"[bold]Profile:[/] {profile}")
    console.print(f"[bold]Workspace:[/] {workspace}")
    result = agent.run(request)
    console.print("\n[bold green]── Final answer ──[/]")
    console.print(result)


@app.command("mcp-serve")
def mcp_serve(
    profile: Path = typer.Option(
        Path("config/profiles/dev.yaml"), "--profile", "-p"
    ),
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w"),
) -> None:
    """Expose the harness tools as an MCP server over stdio.

    This makes the harness consumable by Copilot agent mode, Claude Desktop,
    Cline, and any other MCP client. The model itself is NOT exposed; only
    the tool surface (filesystem, bash, etc.) operating under the same
    permission policy as the standalone agent.
    """
    from harness.mcp_server import serve_stdio

    profile_data = _load_profile(profile)
    serve_stdio(profile_data, workspace)


@app.command("openai-serve")
def openai_serve(
    profile: Path = typer.Option(
        Path("config/profiles/dev.yaml"), "--profile", "-p"
    ),
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w"),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(11500),
) -> None:
    """Expose an OpenAI-compatible /v1/chat/completions endpoint.

    Useful for clients that can swap the OpenAI base URL but cannot speak
    MCP. The endpoint wraps the full agent loop, not just the model — so
    each request is a full agentic session with tool use.

    Works with: JetBrains AI Assistant, Continue.dev, Open WebUI, etc.
    """
    from harness.openai_server import run_server

    profile_data = _load_profile(profile)
    run_server(profile_data, workspace, host, port)


@app.command("eval")
def eval_cmd(
    profile: Path = typer.Option(
        Path("config/profiles/dev.yaml"), "--profile", "-p"
    ),
    tasks_dir: Path = typer.Option(Path("eval/tasks")),
    report: Path = typer.Option(Path("eval/report.json")),
) -> None:
    """Run the eval suite and produce a report."""
    from eval.runner import run_suite

    profile_data = _load_profile(profile)
    exit_code = run_suite(profile_data, tasks_dir, report)
    raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
