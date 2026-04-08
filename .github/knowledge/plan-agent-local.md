# Plan : Agents locaux — pseudo-copilot

## Objectif

Avoir un harness agentique multi-provider (Gemma local, Claude, Copilot)
capable d'exécuter des tâches dans n'importe quel repo, avec tool calling,
sandboxing, audit, et intégration IDE — le tout pilotable depuis un seul
repo (`copilot-gemma4/`).

## Fait

### Infrastructure (2026-04-07)

- [x] Ollama installé et opérationnel sur 2 machines
- [x] Modèles Gemma 4 installés (26b-a4b-it-q8_0, 26b, e4b)
- [x] gemma:7b-instruct installé (profils dev/ci/ops)
- [x] 31b-it-q8_0 testé et **abandonné** (trop lent en CPU-only)
- [x] Benchmarks réalisés sur 4 modèles
- [x] 26+ tasks mise créées
- [x] Repo GitHub : jddellac-hue/copilot-gemma4

### Harness agentique (2026-04-07 → 08)

- [x] Boucle ReAct (agent.py) avec budget tokens, timeout, détection répétition
- [x] Tool calling Gemma 4 validé (natif + fallback regex `<tool_call>`)
- [x] Sandbox bubblewrap avec fallback subprocess automatique (AppArmor)
- [x] Permissions 3 états (allow/ask/deny) + audit JSON-Lines
- [x] Mémoire 2 tiers (working + compaction)
- [x] Observabilité OpenTelemetry (optionnel)
- [x] Serveur MCP (expose les outils aux IDE)

### Multi-provider (2026-04-08)

- [x] Protocol `ModelClient` : interface commune pour tous les providers
- [x] `OllamaClient` : Gemma local (CPU-only, offline, gratuit)
- [x] `AnthropicClient` : Claude Sonnet (en ligne, rapide)
- [x] `OpenAIClient` : GitHub Copilot / Models API, OpenAI, Azure (en ligne)
- [x] 11 profils YAML (dev, ci, gemma4-coding, gemma4-doc, claude, copilot, ops, prod-ro + CI variants)
- [x] `budget_multiplier` dans l'eval runner pour les gros modèles

### Outils intégrés (savoirs-faire de l'agent)

L'agent ne fait pas que "lire et écrire des fichiers". Il embarque des
outils spécialisés qui lui donnent des compétences métier :

| Outil | Savoir-faire | Profils |
|-------|-------------|---------|
| `read_file` / `write_file` / `edit_file` | Lire, écrire, modifier du code | Tous |
| `list_dir` / `search_files` | Explorer un projet | Tous |
| `bash` (sandboxé) | Exécuter des commandes, lancer des tests | coding, dev, ops |
| `dynatrace_dql` | Requêtes DQL sur Grail (métriques, logs, traces) | ops |
| `dynatrace_problems` | Lister les problèmes ouverts/récents | ops |
| `dynatrace_entity_search` | Chercher des entités monitorées | ops |
| `kubectl_get` / `describe` / `logs` | Investigation Kubernetes (read-only, contexte verrouillé) | ops |
| `search_runbooks` | Recherche sémantique RAG dans les runbooks markdown | ops |
| `concourse_pipelines` / `builds` / `build_logs` | Suivi CI Concourse (pipelines, builds, logs SSE) | ops |

> Les outils ops sont opt-in (activés par `ops_tools.<nom>.enabled: true`
> dans le profil YAML). Les tokens viennent de variables d'environnement,
> jamais du code.

### Intégration IDE (2026-04-08)

- [x] `openai-serve` : endpoint HTTP OpenAI-compatible wrappant la boucle agent
- [x] IntelliJ AI Assistant : Gemma local comme cerveau dans le chat IDE
- [x] Copilot + MCP : outils du harness dans le chat Copilot (GPT-4o comme cerveau)
- [x] Chatmodes : coding-agent, ops-investigation
- [x] `.github/mcp/servers.json` + `.vscode/mcp.json` à la racine du repo
- [x] Config auto-discovery pour IntelliJ et VS Code

### Tests et qualité (2026-04-08)

- [x] 54 tests pytest (unit + intégration)
- [x] 117 tests mise tasks (existence, permissions, descriptions, usage, cohérence)
- [x] 38 tests système (imports, sandbox, permissions, filesystem, eval tasks)
- [x] 7 tâches d'eval (fundamentals, coding, ops, security) — 7/7 avec Gemma 4
- [x] Task `verify` : vérification complète en une commande
- [x] Proxy corporate géré (no_proxy dans mise.toml)
- [x] ensure-model.sh : téléchargement automatique des modèles manquants

### Documentation (2026-04-08)

- [x] README multi-provider avec quick start 3 options
- [x] Section workspace (agent sur n'importe quel repo)
- [x] Section IntelliJ (AI Assistant + openai-serve)
- [x] Section Copilot + MCP (outils via chatmodes)
- [x] Tableau comparatif des deux modes IDE
- [x] CLAUDE.md, copilot-instructions.md, eval README, design KB à jour
- [x] KB Gemma 4 dans le repo (.github/knowledge/)

## À faire

### Court terme

- [ ] Tester l'eval avec Claude (quand crédits rechargés)
- [ ] Tester l'eval avec Copilot (GITHUB_TOKEN avec scope models)
- [ ] Tester openai-serve + IntelliJ AI Assistant en session réelle
- [ ] Tester Copilot + MCP chatmodes dans IntelliJ en session réelle
- [ ] Explorer le GPU (RTX A500 sur ijde3720) pour accélérer l'inférence

### Moyen terme

- [ ] Chat interactif agentique (boucle multi-turn dans le terminal)
- [ ] Long-term memory complète (RAG sur les notes persistées)
- [ ] Observabilité branchée sur Dynatrace ou Jaeger
- [ ] Streaming des réponses dans openai-serve (SSE)
- [ ] Prompt tuning pour les quirks spécifiques de Gemma 4

### Décisions prises

1. **Modèle principal** : `gemma4:26b-a4b-it-q8_0` (MoE, 3.8B actifs, ~30 tok/s CPU)
2. **Modèle léger** : `gemma:7b-instruct` (profils dev/ci/ops)
3. **31B Dense abandonné** : 100% timeout en CPU-only
4. **Différenciation par la config** (temperature, permissions), pas par le modèle
5. **Multi-provider** : un seul harness, 3 backends (Ollama, Anthropic, OpenAI)
6. **Sandbox** : bubblewrap préféré, fallback subprocess automatique
7. **Outils ops opt-in** : activés par profil, pas globalement
8. **Deux modes IDE** : AI Assistant (Gemma cerveau) + Copilot MCP (outils)

### Architecture

```
copilot-gemma4/
├── .github/
│   ├── copilot-instructions.md       ← instructions projet
│   ├── mcp/servers.json              ← MCP auto-discovery (IntelliJ/VS Code)
│   ├── chatmodes/                    ← coding-agent, ops-investigation
│   └── knowledge/                    ← KB Gemma 4, plan projet
├── .vscode/mcp.json                  ← MCP auto-discovery (VS Code)
├── mise.toml                         ← env vars, no_proxy
├── scripts/
│   ├── chat.py                       ← chat interactif streaming
│   └── ensure-model.sh               ← auto-install modèles Ollama
├── .mise/tasks/
│   ├── agent/setup|coding|doc|claude|copilot|eval|mcp|serve
│   ├── chat/coding|doc|general
│   ├── model/install|uninstall|list|start|stop|evaluate
│   ├── test/tasks|system|verify|bench
│   ├── tui/bench|install
│   ├── prereqs/install|uninstall
│   ├── verify                        ← vérification complète
│   └── clean
└── agent-harness/
    ├── src/harness/
    │   ├── agent.py                  ← boucle ReAct
    │   ├── model.py                  ← Protocol ModelClient + OllamaClient
    │   ├── anthropic_client.py       ← AnthropicClient
    │   ├── openai_client.py          ← OpenAIClient (Copilot, OpenAI, Azure)
    │   ├── openai_server.py          ← endpoint HTTP /v1/chat/completions
    │   ├── mcp_server.py             ← serveur MCP (outils pour IDE)
    │   ├── memory.py                 ← working + compaction
    │   ├── permissions.py            ← allow/ask/deny + audit
    │   ├── sandbox.py                ← bubblewrap + fallback subprocess
    │   ├── observability.py          ← OpenTelemetry
    │   └── tools/                    ← filesystem, bash, dynatrace, k8s, runbooks, concourse
    ├── config/profiles/              ← 11 profils YAML
    ├── eval/tasks/                   ← 7 tâches d'évaluation
    ├── tests/                        ← 54 tests (unit + intégration)
    └── docs/kb/                      ← design KB (1000+ lignes)
```

### Machines connues

| Machine | CPU | RAM | GPU | Modèle recommandé | Status |
|---------|-----|-----|-----|--------------------|--------|
| jd (pseudo-copilot) | Ryzen 9 5900HX 16t | 62 Go | Vega iGPU | 26b-a4b-it-q8_0 (~30 tok/s) | ✓ Opérationnel |
| ijde3720 (entreprise) | ? | 62 Go | RTX A500 | 26b-a4b-it-q8_0 (GPU à explorer) | ✓ Opérationnel |

### Commandes clés

```bash
# Setup complet (première fois)
mise run agent:setup

# Vérification complète
mise run verify -- gemma4

# Agents terminal
mise run agent:coding -- "tâche" ~/projet
mise run agent:claude -- "tâche"

# Serveur pour IntelliJ
mise run agent:serve

# Évaluations
mise run agent:eval -- gemma4

# Toutes les commandes
mise task ls
```
