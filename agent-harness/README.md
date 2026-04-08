# agent-harness

> Multi-provider agentic harness — coding & ops profiles, MCP integration,
> sandboxed execution, observability-first.

A **« skeleton not a brain »** : the harness handles orchestration,
permissions, sandboxing, memory and tool routing. The brain is whichever
model you point it at — supports **Ollama** (Gemma, local),
**Anthropic** (Claude, en ligne) and **OpenAI-compatible** endpoints
(GitHub Copilot, OpenAI, Azure, etc.).

## Why

Most agentic CLIs are tied to a specific cloud model. This one is built
explicitly to:

- Run **fully offline** with a local model, or online with Claude / Copilot
- Be **auditable** end-to-end (every tool call is logged with its decision)
- Be **safe by default** (sandboxed bash, three-state permissions, deny-list
  for sensitive paths)
- Be **observable** in production (OpenTelemetry tracing → Dynatrace / Loki)
- Plug into existing IDE workflows via **MCP** (Model Context Protocol)

## Three usage modes

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  CLI standalone │    │   MCP server     │    │ OpenAI-compat    │
│  harness run    │    │ harness mcp-serve│    │ harness openai-  │
│                 │    │                  │    │ serve            │
└────────┬────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                      │                       │
         └──────────────────────┼───────────────────────┘
                                ▼
                    ┌────────────────────┐
                    │  Agent Harness     │
                    │  (this project)    │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │  Model Provider    │
                    │  Ollama / Claude / │
                    │  Copilot / OpenAI  │
                    └────────────────────┘
```

| Mode             | When to use                                              |
|------------------|----------------------------------------------------------|
| **CLI**          | One-off tasks, scripting, terminal usage                 |
| **MCP server**   | Integration into Copilot agent mode (VS Code, IntelliJ), Claude Desktop, Cline, Goose, … |
| **OpenAI-compat**| Clients that need to swap an OpenAI base URL but cannot speak MCP |

## Quick start

```bash
# Install
git clone <repo> && cd agent-harness
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,anthropic,openai]"

# Option A: Local (Ollama + Gemma 4)
ollama pull gemma4:e4b
harness run --profile config/profiles/dev.yaml --workspace . \
    "Find the largest file in this repo and tell me its size"

# Option B: Claude (en ligne)
export ANTHROPIC_API_KEY=sk-ant-...
harness run --profile config/profiles/claude-online.yaml --workspace . \
    "Find the largest file in this repo and tell me its size"

# Option C: GitHub Copilot (en ligne)
export GITHUB_TOKEN=ghp_...
harness run --profile config/profiles/copilot.yaml --workspace . \
    "Find the largest file in this repo and tell me its size"
```

## Workspace

Le `--workspace` (ou le 2ème argument des tasks mise) définit le
répertoire de travail de l'agent. L'agent peut lire, écrire et exécuter
des commandes **uniquement** dans ce répertoire (enforced par le
sandbox et les filesystem tools).

```bash
# Travailler dans le répertoire courant (par défaut)
mise run agent:coding -- "Explique ce code"

# Travailler sur un autre projet, depuis n'importe où
mise run agent:coding -- "Trouve les bugs" ~/projects/mon-api

# Le harness reste dans copilot-gemma4/, seul le workspace change
```

Cela permet d'utiliser l'agent sur n'importe quel repo sans avoir
besoin d'y installer quoi que ce soit.

## GitHub Copilot integration

This repo ships with `.github/copilot-instructions.md`,
`.github/mcp/servers.json` and `.vscode/mcp.json` so the harness is
discoverable as an MCP server by Copilot agent mode out of the box.

- **VS Code** : automatic. Open the workspace, switch Copilot Chat to Agent
  mode, the harness tools appear.
- **Copilot CLI** : set `COPILOT_PROVIDER=ollama` and let it discover the
  MCP servers in `.github/mcp/`.
- **IntelliJ** : configure the Copilot plugin to load
  `.github/mcp/servers.json` (or copy entries into the plugin settings).
  See `docs/README-operator.md` § 5.3 for details and the JetBrains AI
  Assistant alternative.

## Project layout

```
agent-harness/
├── .github/
│   ├── copilot-instructions.md   # Project conventions for Copilot
│   ├── mcp/servers.json          # MCP server registration
│   ├── chatmodes/                # Custom Copilot Chat modes
│   └── workflows/ci.yml          # Lint, tests, eval suite
├── .vscode/mcp.json              # VS Code MCP config (mirror)
├── src/harness/
│   ├── agent.py                  # ReAct loop
│   ├── model.py                  # ModelClient protocol + Ollama client
│   ├── anthropic_client.py       # Anthropic (Claude) client
│   ├── openai_client.py          # OpenAI-compatible client (Copilot, etc.)
│   ├── memory.py                 # Working & long-term memory
│   ├── permissions.py            # Allow/ask/deny policy
│   ├── sandbox.py                # bubblewrap / subprocess
│   ├── observability.py          # OTel tracing & metrics
│   ├── mcp_server.py             # Expose harness as MCP
│   ├── cli.py                    # Typer entry point
│   └── tools/
│       ├── base.py               # Tool dataclass + decorator
│       ├── registry.py           # Tool registry
│       ├── filesystem.py         # read/list/search/write/edit
│       └── bash.py               # Sandboxed shell
├── config/profiles/
│   ├── dev.yaml                  # Dev profile (ask before mutations)
│   ├── ci.yaml                   # CI profile (deterministic)
│   ├── gemma4-coding.yaml        # Gemma 4 26B MoE (production coding)
│   ├── gemma4-doc.yaml           # Gemma 4 26B MoE (documentation)
│   ├── claude-online.yaml        # Claude Sonnet (en ligne)
│   ├── copilot.yaml              # GitHub Copilot / Models API
│   ├── ci-gemma4.yaml            # CI non-interactif, Gemma 4
│   ├── ci-claude.yaml            # CI non-interactif, Claude
│   ├── ci-copilot.yaml           # CI non-interactif, Copilot
│   ├── ops.yaml                  # Full ops stack (Dynatrace+K8s+...)
│   └── prod-ro.yaml              # Read-only ops profile
├── eval/
│   ├── tasks/                    # 7 reproducible eval tasks
│   ├── runner.py                 # Eval orchestrator
│   └── README.md
├── tests/
│   ├── unit/                     # Tools, permissions, sandbox
│   └── integration/              # Agent loop with mocked model
├── docs/
│   ├── kb/agent-harness-kb.md    # Design knowledge base (1000+ lines)
│   └── README-operator.md        # Operator runbook
├── pyproject.toml
└── README.md                     # ← you are here
```

## Documentation

Three documents, each with a clear audience:

| File                              | Audience            | Purpose                          |
|-----------------------------------|---------------------|----------------------------------|
| `README.md` (this)                | Anyone              | Project overview, quick start    |
| `docs/kb/agent-harness-kb.md`     | Designer / engineer | Architecture, *why* of decisions |
| `docs/README-operator.md`         | Operator on call    | Install, run, troubleshoot       |

## Safety model in one paragraph

Every tool call goes through a **PermissionPolicy** that returns *allow*,
*ask* or *deny* based on the active profile and a regex match against the
JSON-serialised arguments. *deny* refuses; *ask* prompts the human; *allow*
proceeds. Tool calls that escape the workspace, touch sensitive paths
(`~/.ssh`, `~/.aws`, `~/.kube`, `/etc`), or match dangerous bash patterns
(`rm -rf /`, pipes to shell, `sudo`, etc.) are hard-denied at the sandbox
level regardless of the profile. Every decision is appended to a
**JSON-Lines audit log**.

## Ops integrations (optional)

The `ops` profile (`config/profiles/ops.yaml`) wires four read-only
integrations for production investigation work:

| Tool                       | Backend         | Purpose                                |
|----------------------------|-----------------|----------------------------------------|
| `dynatrace_dql`            | Dynatrace API   | DQL queries on Grail                   |
| `dynatrace_problems`       | Dynatrace API   | List open / recent problems            |
| `dynatrace_entity_search`  | Dynatrace API   | Search monitored entities              |
| `kubectl_get/describe/logs`| `kubectl` CLI   | Read-only K8s, locked context          |
| `search_runbooks`          | Chroma (local)  | Semantic search over markdown runbooks |
| `concourse_pipelines`      | Concourse v1    | List pipelines                         |
| `concourse_builds`         | Concourse v1    | Recent builds for a pipeline / job     |
| `concourse_build_logs`     | Concourse v1    | SSE log stream of a build              |

**Multi-environment safety for Kubernetes** : the `--context` flag is
locked at the profile level. The model cannot override it. Mutating verbs
(`apply`, `delete`, `patch`, `scale`, `exec`, ...) are not in the
allow-list and never reach kubectl. To investigate another cluster, the
operator switches profile (one profile per cluster) — there is no way to
do it from inside an agent session.

**Activation** : each block in `ops_tools.<integration>` is opt-in via
`enabled: true`. Tokens come from environment variables
(`DT_API_TOKEN`, `CONCOURSE_TOKEN`), never committed.

See `docs/README-operator.md` § 6 for the full activation procedure.

## License

MIT. See `LICENSE`.

## Status

Early stage. The harness is a **starting point**, not a finished product.
Expect to extend the tool registry for your own use cases.
