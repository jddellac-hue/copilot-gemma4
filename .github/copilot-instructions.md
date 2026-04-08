# Projet pseudo-copilot — instructions projet

## Ce que fait l'outil

**pseudo-copilot** est un harness agentique multi-provider : un squelette
qui orchestre des outils (filesystem, bash sandboxé, Dynatrace, Kubernetes,
runbook RAG, Concourse) autour d'un cerveau interchangeable.

Trois providers sont supportés :
- **Ollama** (Gemma 4, local, gratuit, CPU-only)
- **Anthropic** (Claude Sonnet, en ligne, rapide)
- **OpenAI-compatible** (GitHub Copilot / Models API, OpenAI, Azure)

Le harness fournit : boucle ReAct, registre d'outils, permissions
allow/ask/deny, sandbox bubblewrap (avec fallback subprocess automatique),
observabilité OpenTelemetry, et serveur MCP pour intégration IDE.

## Structure du projet

```
pseudo-copilot/
├── .github/
│   ├── copilot-instructions.md     ← source de vérité (Copilot + Claude)
│   └── knowledge/gemma4/           ← KB sur Gemma 4 (variantes, hardware, deploy)
├── CLAUDE.md                       ← redirige vers copilot-instructions.md
└── copilot-gemma4/
    ├── mise.toml                   ← config mise (env vars, tasks)
    ├── scripts/ensure-model.sh     ← auto-install des modèles Ollama
    ├── .mise/tasks/                ← 26 tasks mise (agent, chat, model, test)
    └── agent-harness/              ← LE COEUR DU PROJET
        ├── src/harness/            ← Code Python (agent, model, tools, sandbox)
        ├── config/profiles/        ← 11 profils YAML (dev, ci, gemma4, claude, copilot, ops)
        ├── eval/tasks/             ← 7 tâches d'éval reproductibles
        ├── tests/                  ← 96 tests (unit + integration)
        └── docs/                   ← KB design + runbook opérateur
```

## Conventions

- **Python 3.11+**, type hints stricts, `from __future__ import annotations`
- **Ruff** pour le lint, **mypy** en mode strict
- **Dataclasses** pour les objets internes, Pydantic aux frontières I/O
- **Pas de subprocess en dehors de `sandbox.py`** (exception : `kubernetes.py`)
- **Pas de secrets dans le code** — tokens via variables d'environnement uniquement
- **Pas de `default: allow`** dans les profils de permissions
- Tout outil `dangerous` doit avoir un eval task red-team associé

## Tests

```bash
cd copilot-gemma4/agent-harness

# Tests unitaires + intégration (96 tests, pas besoin d'Ollama)
.venv/bin/pytest tests/ -q

# Évaluation avec modèle réel (requiert Ollama ou API key)
mise run agent:eval -- gemma4        # local, ~5 min
mise run agent:eval -- claude        # en ligne, ~2 min
mise run agent:eval -- copilot       # en ligne, ~2 min
```

## Commandes principales

```bash
# Installation
mise run agent:setup

# Agents (workspace courant par défaut, ou chemin en 2ème argument)
mise run agent:coding  -- "tâche"                   # Gemma 4 local
mise run agent:coding  -- "tâche" ~/autre-projet     # sur un autre repo
mise run agent:doc     -- "tâche"                   # Gemma 4 local (doc)
mise run agent:claude  -- "tâche"                   # Claude Sonnet
mise run agent:copilot -- "tâche"                   # GitHub Copilot

# Serveur OpenAI-compatible (pour IntelliJ, Continue.dev, etc.)
mise run agent:serve               # Gemma 4 coding (défaut, port 11500)
mise run agent:serve -- claude     # Claude Sonnet
# IntelliJ : Settings > Tools > AI Assistant > Custom LLM
#   URL : http://127.0.0.1:11500/v1 | Clé : any-key-works

# Évaluations
mise run agent:eval -- gemma4|claude|copilot

# Modèles
mise run model:list                  # modèles installés
mise run model:install -- <model>    # télécharger un modèle
mise run model:start -- <model>      # précharger en RAM

# Voir tout
mise task ls
```
