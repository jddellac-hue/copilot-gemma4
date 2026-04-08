# CLAUDE.md

> This file is read automatically by Claude Code when you open a session
> in this repository. It is the entry point for Claude Code to understand
> the project conventions, the code layout, and the rules it must respect.
>
> Keep this file **concise**. Deep details belong in `docs/kb/` (design) or
> `docs/README-operator.md` (operations). This file points to them.

## What this project is

A **multi-provider agentic harness** supporting Ollama (Gemma, local),
Anthropic (Claude, en ligne) and OpenAI-compatible endpoints (GitHub
Copilot, OpenAI, Azure). It provides: a ReAct agent loop, a tool registry
(filesystem, sandboxed bash, Dynatrace, Kubernetes, runbook RAG,
Concourse), a three-state permission policy (allow/ask/deny), a bubblewrap
sandbox (with automatic subprocess fallback), OpenTelemetry observability,
and an MCP server that re-exposes the tool surface to other clients.

The harness is the **skeleton**; the model is the **brain**. They are
decoupled — swapping the model means editing one line in a profile YAML.
Three providers are implemented via the `ModelClient` protocol in
`model.py`: `OllamaClient`, `AnthropicClient`, `OpenAIClient`.

## Reading order for a new session

Read these files in order if you need to understand the project:

1. `README.md` — project overview, quick start, layout
2. `docs/README-operator.md` — install, run, troubleshoot, ops tooling setup
3. `docs/kb/agent-harness-kb.md` — design KB, *why* each choice was made
4. `.github/copilot-instructions.md` — conventions also applicable to you

You do **not** need to read all of them for every task. For a bug fix,
often `README.md` + the relevant module is enough. For an architecture
change, read the KB section for the relevant sub-system first.

## Project layout (the parts you'll touch most)

```
src/harness/
├── agent.py              # ReAct loop
├── model.py              # ModelClient protocol + Ollama client
├── anthropic_client.py   # Anthropic (Claude) client
├── openai_client.py      # OpenAI-compat client (Copilot, etc.)
├── memory.py             # Conversation memory + compaction
├── permissions.py        # allow/ask/deny policy
├── sandbox.py            # bubblewrap / subprocess (auto-fallback)
├── observability.py      # OTel tracing & metrics
├── mcp_server.py         # Expose harness tools as MCP
├── cli.py                # Typer entry point (run, mcp-serve, eval)
└── tools/
    ├── base.py           # Tool dataclass + decorator
    ├── registry.py       # ToolRegistry
    ├── filesystem.py     # read/list/search/write/edit (workspace-scoped)
    ├── bash.py           # Sandboxed shell
    ├── dynatrace.py      # dynatrace_dql, problems, entity_search
    ├── kubernetes.py     # kubectl_get/describe/logs (LOCKED context)
    ├── runbooks.py       # Chroma RAG over markdown runbooks
    └── concourse.py      # concourse_pipelines/builds/build_logs

config/profiles/          # dev, ci, gemma4-*, claude-*, copilot, ops, prod-ro
eval/tasks/               # 7 reproducible eval tasks (YAML)
tests/unit/               # Permissions, sandbox, tools, k8s, runbooks, SSE
tests/integration/        # Agent loop with mocked model
```

## Commands you will need

```bash
# Install (all extras)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,anthropic,openai]"

# Run unit tests — should report "54 passed"
pytest tests/ -q

# Lint + type check (required before committing)
ruff check src tests eval
mypy src

# Run the agent against a real task (requires Ollama + gemma model)
harness run --profile config/profiles/dev.yaml --workspace . "<task>"

# Expose as MCP server (for Copilot / Claude Desktop / other clients)
harness mcp-serve --profile config/profiles/dev.yaml --workspace .

# Run the eval suite (requires a running Ollama)
harness eval --profile config/profiles/ci.yaml
```

## Hard rules — never violate these

These are non-negotiable. Violating any of them means the PR gets rejected
on review, or worse, someone gets compromised.

1. **No `subprocess.run`, `os.system`, `os.popen` outside of `sandbox.py`.**
   The sole exception is `tools/kubernetes.py`, which calls `kubectl` with
   a hand-built argv and a locked `--context`. Do not add new exceptions.

2. **No widening of the Kubernetes resource allow-list** (`ALLOWED_RESOURCES`
   in `tools/kubernetes.py`) to include mutating verbs: `apply`, `delete`,
   `create`, `edit`, `patch`, `scale`, `rollout`, `exec`. The harness is
   read-only for Kubernetes by design.

3. **No `default: allow` in any profile.** The default must always be
   `ask` (dev) or `deny` (ci, prod-ro, ops).

4. **No secrets in code, configs, tests, or fixtures.** Tokens come from
   environment variables exclusively. Never commit a `.env`. Never log a
   token.

5. **No bypass of the workspace boundary in filesystem tools.** The
   `_resolve()` helper in `tools/filesystem.py` must be used for every
   path. Never construct a `Path` directly from user input.

6. **No new `dangerous` tool without a red-team eval task.** If you add a
   tool with `risk="dangerous"`, you must also add an eval task under
   `eval/tasks/` that verifies the permission policy catches its worst-case
   abuse. See `07-redteam-prompt-injection.yaml` for the pattern.

7. **No direct imports of `Agent`, `Memory`, or `OllamaClient` from tool
   modules.** Tools only import from `harness.tools.base`. This keeps
   sub-systems decoupled.

## Coding conventions

- **Python 3.11+**, full type hints, `from __future__ import annotations`
  at the top of every module.
- **Strict mypy**. `Any` requires a comment justifying it.
- **Ruff** for linting and import sorting. Configuration in
  `pyproject.toml`.
- **Dataclasses** for value objects; Pydantic only at IO boundaries
  (config, MCP schemas).
- **Module-level docstrings** are mandatory and should explain *why*, not
  *what*.
- **Logging**, never `print`, except in `cli.py` (Rich for UX).
- **No top-level side effects** in `src/harness/` modules. Configuration
  must be explicit and passed in.

## Testing conventions

- Unit tests in `tests/unit/`, integration in `tests/integration/`.
- The agent loop is tested with `ScriptedModel` (see
  `tests/integration/test_agent_loop.py`) — never require a live Ollama in
  unit or integration tests.
- The eval suite under `eval/tasks/` is the **only** place that calls a
  real model. It runs in CI against `gemma:2b-instruct` for speed.
- When you fix a bug, add a regression test **before** the fix.
- When you add a tool, add unit tests for its pure logic (validation,
  parsing, argv construction) before the code that calls an external
  service.

## Profiles — which one to use when

**Local (Ollama) :**
- `dev.yaml` — everyday coding sessions, mutations gated behind `ask`
- `gemma4-coding.yaml` — Gemma 4 26B MoE, production coding
- `gemma4-doc.yaml` — Gemma 4 26B MoE, documentation
- `ci.yaml` — deterministic, non-interactive (Gemma 4 E4B)
- `ci-gemma4.yaml` — deterministic, non-interactive (Gemma 4 26B MoE)

**En ligne :**
- `claude-online.yaml` — Claude Sonnet, interactive
- `ci-claude.yaml` — Claude Sonnet, non-interactive (evals)
- `copilot.yaml` — GitHub Copilot / Models API, interactive
- `ci-copilot.yaml` — GitHub Copilot, non-interactive (evals)

**Ops :**
- `ops.yaml` — full ops stack (Dynatrace + K8s + Runbooks + Concourse)
- `prod-ro.yaml` — minimal read-only profile for investigating a workspace

To investigate a **different** Kubernetes cluster, copy `ops.yaml` to
`ops-<cluster>.yaml` and change the `kubernetes.context`. Do NOT try to
make the harness switch context at runtime ��� it's forbidden by design.

## Common tasks and where to look

| Task                                     | Start in                                 |
|------------------------------------------|------------------------------------------|
| Add a new tool                           | `src/harness/tools/` + `tests/unit/`     |
| Change permission logic                  | `src/harness/permissions.py`             |
| Add a new sandbox backend                | `src/harness/sandbox.py`                 |
| Wire a new MCP server as a client        | `src/harness/mcp_server.py` (as example) |
| Add a new profile                        | `config/profiles/` (copy an existing)    |
| Add a new eval task                      | `eval/tasks/` + `eval/README.md`         |
| Fix a flaky test                         | Reproduce locally first, then `tests/`   |
| Trace a runtime issue                    | `docs/README-operator.md` § 11           |
| Understand *why* something is the way it is | `docs/kb/agent-harness-kb.md`         |

## When in doubt

- If a change touches more than two sub-systems, reconsider — the design
  keeps them decoupled for a reason.
- If a test would require mocking five things, the code under test is
  probably doing too much.
- If you find yourself wanting to bypass the sandbox "just for this case",
  stop and ask.
- If the change involves a new external dependency, check whether it can
  go in an **optional extra** (`pyproject.toml: [project.optional-dependencies]`)
  rather than the core dependency set.

## What this project is NOT

- Not a framework. It's a harness for one user (or one team) running one
  model locally. Resist the urge to add plugin systems, abstract factories,
  or multi-tenant machinery.
- Not a replacement for Claude Code, Copilot, or Aider. It complements
  them — the MCP server makes the harness callable *from* those tools.
- Not a production mutation tool. Every design decision biases toward
  observation. Mutations, when needed, should go through the existing
  change-management process, not through an agent.
