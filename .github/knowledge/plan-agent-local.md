# Plan : Agents locaux Gemma 4 avec agent-harness

## Objectif

Avoir deux agents locaux autonomes (coding + doc) capables d'exécuter des tâches dans un repo, avec tool calling, sandboxing, et audit — le tout offline sur notre machine.

## Fait (conversation du 2026-04-07)

- [x] Ollama installé et opérationnel
- [x] Modèles Gemma 4 installés (26b-a4b-it-q8_0, 26b, e4b, 31b)
- [x] 31b-it-q8_0 testé et **abandonné** (trop lent en CPU-only, 100% timeout)
- [x] Benchmarks réalisés sur 4 modèles (voir benchmarks/)
- [x] 20 tasks mise créées (prereqs, model, test, tui, chat, agent)
- [x] agent-harness installé, profils gemma4-coding et gemma4-doc créés
- [x] Tool calling validé (Gemma 4 26B appelle les outils nativement)
- [x] Chat interactif avec streaming (scripts/chat.py)
- [x] ensure-model.sh : vérif auto ollama + modèle + preload
- [x] Repo GitHub public : jddellac-hue/copilot-gemma4
- [x] KB Gemma 4 dans .github/knowledge/gemma4/

## Phase 1-4 : FAIT

Voir le README du repo pour la doc complète.

## Phase 5 : Chat amélioré avec tools (À FAIRE)

**Quoi :** Passer du chat basique (scripts/chat.py, texte pur) au chat agentique (harness).

Le chat actuel n'a pas d'outils. Pour avoir un chat qui peut lire/écrire des fichiers :
- Option A : ajouter un mode interactif à `harness run`
- Option B : wrapper le harness en boucle dans scripts/chat.py
- Option C : utiliser le serveur MCP + un client MCP interactif

## Phase 6 : Observabilité (À FAIRE)

**Quoi :** Brancher l'OpenTelemetry pour tracer les sessions agent.

Options :
- Jaeger local (`docker run jaegertracing/all-in-one`)
- Simple logs JSON (déjà en partie via l'audit log du harness)

## Phase 7 : Intégration MCP dans IDE (À FAIRE)

**Quoi :** Connecter l'agent comme MCP server dans VS Code / Copilot / Claude Code.

```bash
mise run agent:mcp -- coding
```

Config VS Code settings.json :
```json
{
  "mcp.servers": {
    "gemma4-coding": {
      "command": "<chemin>/agent-harness/.venv/bin/harness",
      "args": ["mcp-serve", "--profile", "<chemin>/gemma4-coding.yaml", "--workspace", "."]
    }
  }
}
```

## Phase 8 : Eval complète (À FAIRE)

Lancer les 7 tâches d'eval du harness avec Gemma 4 et documenter les résultats :
```bash
mise run agent:eval -- coding
```

Tâches d'eval : read-and-report, search-by-pattern, edit-file, run-tests, fix-failing-test, ops-log-investigation, redteam-prompt-injection.

## Décisions prises

1. **Modèle** : `gemma4:26b-a4b-it-q8_0` pour les deux agents (coding + doc). Le 31B est trop lent en CPU-only.
2. **Différenciation** : par la config (temperature, permissions), pas par le modèle.
3. **Venv séparé** : agent-harness a son propre .venv (dans .gitignore, à créer via `mise run agent:setup`)
4. **Thinking mode** : gardé (meilleure qualité), mais cause des timeouts sur les prompts complexes (300s coding, 180s doc)

## Décisions à prendre

1. **Faut-il merger** agent-harness dans copilot-gemma4 ou le garder comme sous-dossier ?
2. **Context window** : 32K suffit-il pour les tâches de code réelles ou faut-il monter ?
3. **Chat agentique** : quelle option pour Phase 5 (A, B, ou C) ?

## Architecture du projet

```
copilot-gemma4/
├── mise.toml                    # Config centrale (modèles par défaut, env vars)
├── .gitignore
├── README.md                    # Documentation complète
├── scripts/
│   ├── chat.py                  # Chat interactif streaming
│   └── ensure-model.sh          # Vérif auto ollama + modèle + preload
├── .mise/
│   ├── benchmarks/              # Résultats de benchmarks
│   └── tasks/
│       ├── prereqs/install|uninstall
│       ├── model/evaluate|install|uninstall|list|start|stop
│       ├── test/bench|verify
│       ├── tui/bench|install
│       ├── chat/coding|doc|general
│       ├── agent/coding|doc|mcp|eval|setup
│       └── clean
└── agent-harness/               # Harness agentique (sous-dossier)
    ├── .venv/                   # (gitignored, créé via agent:setup)
    ├── config/profiles/
    │   ├── gemma4-coding.yaml   # 26B MoE Q8, temp 0.2
    │   └── gemma4-doc.yaml      # 26B MoE Q8, temp 0.3
    ├── src/harness/             # Code source du harness
    ├── eval/tasks/              # 7 tâches d'évaluation
    └── tests/
```

## Machines connues

| Machine | CPU | RAM | GPU | Modèle recommandé |
|---------|-----|-----|-----|--------------------|
| jd (pseudo-copilot) | Ryzen 9 5900HX 16t | 62 Go | Vega iGPU | 26b-a4b-it-q8_0 (~30 tok/s) |
| ijde3720 | ? | ? | RTX A500 | 26b-a4b-it-q8_0 (+ GPU possible) |
