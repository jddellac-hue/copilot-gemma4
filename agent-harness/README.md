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
pip install -e ".[dev,rag,anthropic,openai]"

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

## IntelliJ — Gemma local dans le chat IDE

Le harness expose un serveur OpenAI-compatible qui permet d'utiliser
Gemma (ou Claude, Copilot) comme LLM dans le chat intégré d'IntelliJ.
Chaque message déclenche une session agent complète : le modèle
raisonne, appelle les outils (read file, bash, etc.), et retourne la
réponse finale.

### 1. Démarrer le serveur

```bash
mise run agent:serve               # Gemma 4 coding (défaut)
mise run agent:serve -- doc        # Gemma 4 documentation
mise run agent:serve -- claude     # Claude Sonnet (en ligne)
mise run agent:serve -- copilot    # GitHub Copilot (en ligne)
```

### 2. Configurer IntelliJ

- **Settings > Tools > AI Assistant > Custom LLM Provider**
- URL : `http://127.0.0.1:11500/v1`
- API Key : `any-key-works` (le serveur n'authentifie pas)
- Model : `gemma4:26b-a4b-it-q8_0`

### 3. Utiliser dans le chat IntelliJ

Ouvrir le chat AI intégré et poser des questions sur le code. Le
serveur tourne sur le workspace courant par défaut. Pour l'utiliser
sur un autre projet :

```bash
mise run agent:serve -- coding ~/autre-projet
```

> Le serveur doit tourner en arrière-plan pendant toute la session.
> Arrêter avec Ctrl+C.

## Copilot + MCP (outils du harness dans le chat Copilot)

Le repo fournit `.github/mcp/servers.json`, `.vscode/mcp.json` et
`.github/chatmodes/` pour exposer les **outils** du harness via MCP.
Dans ce mode, Copilot garde son propre modèle (GPT-4o) mais peut
utiliser les outils du harness (filesystem, bash sandboxé, Dynatrace,
K8s, etc.).

### Setup VS Code

Automatique. Ouvrir le workspace `copilot-gemma4/`, passer Copilot
Chat en mode Agent — les outils du harness apparaissent.

### Setup IntelliJ

1. Installer le plugin **GitHub Copilot** dans IntelliJ
2. Ouvrir le workspace `copilot-gemma4/`
3. Le plugin découvre `.github/mcp/servers.json` automatiquement
4. Dans Copilot Chat, les chatmodes apparaissent :
   - **Coding Agent** — filesystem + bash (pour le dev)
   - **Ops Investigation** — Dynatrace + K8s + runbooks + Concourse

> **Prérequis** : le harness doit être installé (`mise run agent:setup`).
> Le serveur MCP est lancé automatiquement par le plugin Copilot.

### Chatmodes disponibles

| Chatmode | Outils | Usage |
|----------|--------|-------|
| Coding Agent | read/write/edit/search files, bash | Explorer, analyser, modifier du code |
| Ops Investigation | Dynatrace, K8s, runbooks, Concourse | Investigation d'incidents en read-only |

## Comparaison des deux modes

| | AI Assistant + openai-serve | Copilot + MCP |
|---|---|---|
| **Cerveau** | Gemma local (ou Claude/Copilot) | GPT-4o (GitHub) |
| **Outils** | Intégrés dans la boucle agent | Via MCP |
| **Offline** | Oui (avec Gemma) | Non |
| **Vitesse** | ~30 tok/s (CPU) | Rapide (cloud) |
| **Coût** | Gratuit | Licence Copilot |
| **Config** | `mise run agent:serve` + Custom LLM | Automatique (MCP discovery) |
| **Commande** | `mise run agent:serve` | `mise run agent:mcp` (ou auto) |

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
│       ├── bash.py               # Sandboxed shell
│       ├── dynatrace.py          # DQL, problems, entity search
│       ├── kubernetes.py         # kubectl get/describe/logs (locked context)
│       ├── runbooks.py           # RAG over markdown runbooks (Chroma)
│       ├── skills.py             # RAG over domain skills (Chroma, 10 domains)
│       └── concourse.py          # Pipelines, builds, build logs
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

## Domain skills (RAG)

L'agent dispose d'un outil `search_skills` qui lui donne accès à une
base de connaissances métier sur 10 domaines techniques. Cet outil
utilise un RAG local (Chroma + embeddings CPU) pour retrouver les
extraits pertinents par recherche sémantique.

### Domaines disponibles

| Domaine | Contenu |
|---------|---------|
| `angular` | Angular 15, Jest, Cypress, Apache, Kustomize |
| `base` | Oracle 19c Docker, Flyway, schemas, migrations |
| `concourse` | Concourse 7.14.3, Kind K8s, 3 pipelines |
| `devops` | Cycle DevOps, conventional commits, testing pyramid, CI/CD |
| `dynatrace` | DQL, Grail, entités, relations, app development |
| `kubernetes` | Diagnostic pods, probes, Kustomize, Helm, RBAC, NetworkPolicy |
| `oracle` | CDB/PDB, ARCHIVELOG, GoldenGate, DataGuard, tablespace monitoring |
| `quarkus` | Quarkus 2.16/3.x, Kafka, JPA, Dev Services, dual datasources |
| `template` | Cookiecutter Streamlit, uv, K8s/Kustomize 4 overlays |
| `test` | Docker Compose 7 services, Behave, Playwright, E2E |

### Comment ça marche

```
DÉMARRAGE (une fois par session agent)
  1. Chroma ouvre la collection "agent_skills"
     persistée dans ~/.local/share/agent-harness/chroma/
  2. Parcourt copilot-gemma4/skills/**/*.md
  3. Découpe chaque fichier en chunks de ~800 chars (par sections ##)
  4. Upsert dans Chroma (idempotent : même hash SHA256 = skip)
  → ~994 chunks indexés, quasi-instantané après le premier run

RUNTIME (à chaque appel search_skills)
  1. Le modèle appelle search_skills(query="...", domain="quarkus")
  2. Chroma fait une recherche vectorielle (embedding similarity)
     directement dans son index — PAS de relecture des fichiers .md
  3. Retourne les top-5 chunks avec score, fichier source, section, domaine
  4. Le modèle utilise ces extraits pour formuler sa réponse
```

### Où vivent les données

| Quoi | Où |
|------|---|
| Fichiers source | `copilot-gemma4/skills/` (dans le repo, versionnés) |
| Index vectoriel | `~/.local/share/agent-harness/chroma/` (local, regénéré auto) |
| Modèle d'embedding | `all-MiniLM-L6-v2` (~80 Mo, téléchargé au 1er run, CPU-only) |

### Activation

Le skill RAG est activé dans 6 profils (dev, gemma4-coding, gemma4-doc,
claude-online, copilot, ops) via `ops_tools.skills.enabled: true`.
Le chemin est relatif (`path: skills`) et résolu automatiquement par
rapport au repo root.

Prérequis : `pip install agent-harness[rag]` (inclus dans `agent:setup`).

### Ajouter un nouveau skill

1. Créer `skills/<domain>/SKILL.md`
2. Optionnel : `skills/<domain>/references/*.md`, `versions/*.md`
3. Relancer l'agent → Chroma ré-indexe automatiquement les nouveaux fichiers

## License

MIT. See `LICENSE`.

## Status

Early stage. The harness is a **starting point**, not a finished product.
Expect to extend the tool registry for your own use cases.
