# Mode opératoire : Agent Harness en console (terminal)

> Guide pour utiliser l'agent harness directement en ligne de commande,
> via nos tasks mise ou via des outils CLI tiers avec MCP.

---

## Nos tasks mise (intégrées, prêtes à l'emploi)

### Chat interactif (avec RAG skills)

```bash
mise run chat -- coding     # Chat code (Gemma 4 26B MoE, RAG activé)
mise run chat -- doc        # Chat documentation
mise run chat -- general    # Chat général
```

Le chat enrichit chaque message avec le contexte des 18 skills RAG.
Commandes : `/help`, `/skills <query>`, `/rag on|off`, `/save`, `/quit`.

### Agent avec outils (harness complet)

```bash
# Gemma 4 local (gratuit, offline)
mise run agent:coding -- "Trouve et corrige les bugs dans main.py"
mise run agent:coding -- "Ajoute des tests pour utils.py" ~/autre-projet

# Agent documentation
mise run agent:doc -- "Génère un README pour ce projet"

# Claude Sonnet (en ligne, ANTHROPIC_API_KEY requis)
mise run agent:claude -- "Refactorise le module auth"

# GitHub Copilot (en ligne, GITHUB_TOKEN requis)
mise run agent:copilot -- "Explique l'architecture"
```

L'agent a accès à : filesystem, bash sandboxé, search_skills (RAG),
et en profil ops : Dynatrace, Kubernetes, runbooks, Concourse.

### Serveurs pour outils tiers

```bash
# Serveur MCP (stdio) — pour Claude Code, Codex, Goose, etc.
mise run agent:mcp -- coding

# Serveur OpenAI-compatible (HTTP) — pour Aider, Continue, Cline, etc.
mise run agent:serve           # http://127.0.0.1:11500/v1
mise run agent:serve -- doc    # mode documentation
mise run agent:serve -- claude # Claude comme cerveau
```

---

## Outils CLI tiers — les meilleurs avec notre harness

### Tier 1 : compatibilité complète (MCP + openai-serve + Ollama)

| Outil | MCP | openai-serve | Ollama | Gratuit | Install |
|---|---|---|---|---|---|
| **Codex CLI** (OpenAI) | Oui | Oui | Oui (`--oss`) | Oui | `npm i -g @openai/codex` |
| **Goose** (Block) | Oui | Oui | Oui | Oui | `brew install goose` |
| **MCPHost** | Oui | Oui | Oui | Oui | `go install github.com/mark3labs/mcphost@latest` |
| **gptme** | Oui | Oui | Oui | Oui | `pip install gptme` |

### Tier 2 : MCP ou openai-serve (pas les deux)

| Outil | MCP | openai-serve | Gratuit | Install |
|---|---|---|---|---|
| **Claude Code** | Oui (complet) | Non | API costs | `npm i -g @anthropic-ai/claude-code` |
| **Aider** | Non (issue #4506) | Oui | Oui | `pip install aider-chat` |
| **Gemini CLI** | Oui | Non (bientôt) | Oui | `npm i -g @anthropic-ai/gemini-cli` |
| **Copilot CLI** | Oui | Oui (BYOK) | Licence Copilot | `npm i -g @github/copilot` |
| **Junie CLI** | Oui | Non | BYOK | `curl -fsSL https://junie.jetbrains.com/install.sh \| bash` |

---

## Configurations détaillées

### Codex CLI + harness MCP + Gemma local

```bash
# Installer
npm install -g @openai/codex

# Configurer (~/.codex/config.toml)
cat > ~/.codex/config.toml << 'EOF'
[model_providers.harness]
name = "Agent Harness"
base_url = "http://localhost:11500/v1"

[profiles.local]
model_provider = "harness"
model = "gemma4-coding"

[mcp_servers.harness-tools]
command = "/chemin/complet/copilot-gemma4/agent-harness/.venv/bin/harness"
args = ["mcp-serve", "--profile", "config/profiles/dev.yaml", "--workspace", "."]
EOF

# Démarrer le serveur harness
mise run agent:serve &

# Lancer Codex avec le profil local
codex --profile local
```

### Goose + harness MCP

```bash
# Installer
brew install goose  # ou curl -fsSL https://github.com/block/goose/releases/download/stable/download_cli.sh | bash

# Configurer (~/.config/goose/config.yaml)
cat > ~/.config/goose/config.yaml << 'EOF'
extensions:
  harness:
    type: stdio
    command: /chemin/complet/copilot-gemma4/agent-harness/.venv/bin/harness
    args:
      - mcp-serve
      - --profile
      - /chemin/complet/copilot-gemma4/agent-harness/config/profiles/dev.yaml
      - --workspace
      - .
EOF

# Lancer
goose
```

### Claude Code + harness MCP

```bash
# Installer
npm install -g @anthropic-ai/claude-code

# Ajouter le serveur MCP
claude mcp add harness \
  /chemin/complet/copilot-gemma4/agent-harness/.venv/bin/harness \
  mcp-serve \
  --profile config/profiles/dev.yaml \
  --workspace .

# Vérifier
claude mcp list

# Lancer
claude
```

### Aider + harness openai-serve (pas de MCP, mais excellent pour le git)

```bash
# Installer
pip install aider-chat

# Démarrer le serveur harness
mise run agent:serve &

# Lancer Aider avec le harness comme LLM
OPENAI_API_BASE=http://localhost:11500/v1 \
OPENAI_API_KEY=any-key-works \
aider --model openai/gemma4-coding
```

Aider est le meilleur outil pour les workflows git (commit, diff, history).

### MCPHost + Ollama + harness MCP (le plus léger)

```bash
# Installer
go install github.com/mark3labs/mcphost@latest

# Configurer (mcp-config.json)
cat > mcp-config.json << 'EOF'
{
  "mcpServers": {
    "harness": {
      "command": "/chemin/complet/copilot-gemma4/agent-harness/.venv/bin/harness",
      "args": ["mcp-serve", "--profile", "config/profiles/dev.yaml", "--workspace", "."]
    }
  }
}
EOF

# Lancer avec Ollama
mcphost -m ollama:gemma4:26b-a4b-it-q8_0 --config mcp-config.json
```

---

## Outils de debug MCP

Pour inspecter et tester les outils exposés par le harness :

```bash
# mcptools — Swiss Army knife MCP
brew tap f/mcptools && brew install mcp
mcp tools -- harness mcp-serve --profile config/profiles/dev.yaml
mcp call read_file '{"path":"README.md"}' -- harness mcp-serve --profile config/profiles/dev.yaml

# mcpc (Apify) — client MCP universel
npm install -g @apify/mcpc
mcpc tools --stdio -- harness mcp-serve --profile config/profiles/dev.yaml
```

---

## Matrice de décision

| Besoin | Outil recommandé | Pourquoi |
|---|---|---|
| Chat rapide en terminal | `mise run chat -- coding` | Intégré, RAG, aucune dépendance externe |
| Agent avec outils, offline | `mise run agent:coding` | Harness complet, Gemma local |
| Agent cloud puissant | `mise run agent:claude` | Claude Sonnet, outils harness |
| Git-focused (commit, diff) | **Aider** + `agent:serve` | Meilleure intégration git |
| Multi-MCP, flexible | **Goose** ou **Codex CLI** | Support MCP + Ollama + cloud |
| Léger, juste MCP + Ollama | **MCPHost** | Minimal, Go, rapide |
| Debug MCP | **mcptools** | Inspecter les outils sans LLM |
| Claude uniquement | **Claude Code** | MCP complet, meilleur agent Claude |

---

## Résumé des commandes

```bash
# === NOS TASKS (prêtes à l'emploi) ===
mise run chat -- coding              # Chat + RAG
mise run agent:coding -- "tâche"     # Agent Gemma local
mise run agent:claude -- "tâche"     # Agent Claude
mise run agent:serve                 # Serveur OpenAI-compat
mise run agent:mcp -- coding         # Serveur MCP

# === OUTILS TIERS ===
codex --profile local                # Codex + harness
goose                                # Goose + harness MCP
claude                               # Claude Code + harness MCP
aider --model openai/gemma4-coding   # Aider + harness endpoint
mcphost -m ollama:gemma4:26b-a4b-it-q8_0 --config mcp.json  # MCPHost
```
