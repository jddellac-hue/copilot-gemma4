# Instructions for GitHub Copilot

> This file is automatically loaded by GitHub Copilot (in VS Code, JetBrains
> IDEs, and the Copilot CLI) when working in this repository. It teaches
> Copilot the conventions of the project.

## Project context

This repository is a **local agentic harness** built around a Gemma model
served by Ollama. It is a Python 3.11+ project. The harness can be used in
three ways:

1. As a **standalone CLI** (`harness run`)
2. As an **MCP server** (`harness mcp-serve`) that other agentic clients —
   including Copilot agent mode itself — can call into
3. As an **OpenAI-compatible HTTP endpoint** (`harness openai-serve`) for
   clients that cannot speak MCP

When asked to integrate this project with another tool, prefer the **MCP
path**: it is the most stable and most portable.

## Coding conventions

- **Python 3.11+** with full type hints. We use `from __future__ import
  annotations` at the top of every module.
- **Strict mypy** is enforced in CI. Avoid `Any` unless unavoidable.
- **Ruff** for linting and import sorting; configuration in `pyproject.toml`.
- **Dataclasses** are preferred over plain classes for value objects;
  Pydantic is used only at IO boundaries (config, MCP schemas).
- **Docstrings** in Google or NumPy style. Module-level docstrings are
  required and should explain the *why* of the module, not just the *what*.
- **No top-level side effects** in any module under `src/harness/` —
  configuration must be explicit.
- **Logging**, never `print`, except in `cli.py` where Rich is used for UX.

## Testing conventions

- **pytest** with `pytest-asyncio` for async tests.
- Unit tests live in `tests/unit/`, integration tests in `tests/integration/`.
- The agent loop is tested with a **mocked Ollama client** that replays
  scripted responses; do not require a live model in unit/integration tests.
- The **eval suite** under `eval/tasks/` *does* require a live model and is
  the only place that calls Ollama for real. CI gates merges on the eval
  baseline.

## Security conventions — these are mandatory

- **Never** introduce a tool that bypasses the `Sandbox` for shell execution.
- **Never** widen the `permissions` default to `allow` in any profile.
- **Never** write to `~/.ssh`, `~/.aws`, `~/.kube`, `~/.gnupg`, `/etc/`,
  `/usr/`, or any path matched by the deny patterns in
  `config/profiles/dev.yaml`.
- When adding a new tool, you must declare its `risk` and `side_effects`
  honestly. A tool that calls the network has `network` in side_effects;
  a tool that runs subprocess has `exec`. The permission system relies on
  this.
- Any new `dangerous` tool must be added to the eval suite's red-teaming
  task before being merged.

## Architectural conventions

- The six sub-systems (agent loop, tool registry, memory, permissions, MCP
  clients, sandbox) are **decoupled**. A change to one must not require a
  change to another. If you find yourself touching three of them in one PR,
  reconsider the design.
- New tools go under `src/harness/tools/` and must be wired in via the
  `ToolRegistry`. They should never directly import `Agent`, `Memory`, or
  `OllamaClient` — only the `Tool` and `ToolResult` types from
  `harness.tools.base`.
- The `sandbox` module is the **only** module allowed to call
  `subprocess.run` for arbitrary shell commands. All other modules use the
  `Sandbox` API.

## Documentation conventions

- The **design KB** lives at `docs/kb/agent-harness-kb.md` and is the
  authoritative reference for the architecture. Update it when changing the
  design.
- The **operator runbook** lives at `docs/README-operator.md`. Update it when
  changing deployment, configuration, or operational procedures.
- Public-facing changes go in the project `README.md`.

## What Copilot should NOT do in this repo

- Do not suggest `requests`/`urllib` calls outside of explicit network tools.
- Do not suggest `os.system`, `os.popen`, or `subprocess.run` outside of the
  `sandbox` module — **with one exception**: `tools/kubernetes.py` uses
  `subprocess.run` directly for `kubectl`, with strict argv construction
  and locked context. Do not loosen that pattern.
- Do not suggest disabling type checks, lint rules, or tests to "make it
  pass". If the tests are wrong, fix the tests; if the types are wrong, fix
  the types.
- Do not suggest committing secrets, API keys, or `.env` files.
- Do not suggest pulling unverified MCP servers or npm/pip packages.

## Ops tools (Dynatrace / Kubernetes / Runbooks / Skills / Concourse)

The harness ships with five optional ops integrations under
`src/harness/tools/`:

- `dynatrace.py` — `dynatrace_dql`, `dynatrace_problems`,
  `dynatrace_entity_search`. All read-only via the Dynatrace API.
- `kubernetes.py` — `kubectl_get`, `kubectl_describe`, `kubectl_logs`. The
  context is **locked at the profile level**; the model cannot override it.
  Resource kinds are validated against an allow-list. Pod/container names
  go through a strict regex. **Never widen the kind allow-list to include
  mutating verbs**.
- `runbooks.py` — `search_runbooks` (RAG over a markdown directory via
  Chroma). Optional dep; install with `pip install agent-harness[rag]`.
- `skills.py` — `search_skills` (RAG over domain skill documentation via
  Chroma). Indexes a skills directory where each subdirectory is a domain
  (angular, oracle, quarkus, etc.). Supports optional `domain` filter.
  Optional dep; install with `pip install agent-harness[rag]`.
- `concourse.py` — `concourse_pipelines`, `concourse_builds`,
  `concourse_build_logs`. Read-only via the Concourse v1 API.

When adding capabilities to these modules:

- New Dynatrace tools must remain read-only. The harness explicitly does
  not provide a `dynatrace_settings_write` or similar.
- New kubectl verbs must NOT include `apply`, `delete`, `create`, `edit`,
  `patch`, `scale`, `rollout`, or `exec`. These are blocked at the profile
  level too, but the code-level barrier is the first defence.
- New Concourse tools must not call mutating endpoints (`pause-pipeline`,
  `unpause-pipeline`, `trigger-build`, etc.).

The opt-in for each block is in `config/profiles/ops.yaml` under
`ops_tools.<integration>.enabled`. Tokens are loaded from environment
variables, never committed.
