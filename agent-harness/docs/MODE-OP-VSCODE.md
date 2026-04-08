# Mode opératoire : Agent Harness dans VS Code

> Guide pas-à-pas pour connecter notre agent harness à VS Code via
> Copilot, Continue.dev ou Cline. Couvre MCP et OpenAI-compatible endpoint.

---

## Vue d'ensemble des options

| Option | Cerveau | Outils harness | Coût | Offline |
|---|---|---|---|---|
| **Copilot + MCP** | GPT-4.1, Claude, Gemini (cloud) | Via MCP | Licence Copilot | Non |
| **Continue.dev + harness** | Gemma local via `agent:serve` | Via MCP ou intégrés | Gratuit | Oui |
| **Cline + harness** | Gemma local ou cloud | Via MCP | Gratuit | Oui |
| **Copilot + BYOK** | Ollama local dans le chat Copilot | Pas de MCP tools | Licence Copilot | Partiellement |

---

## Option 1 : GitHub Copilot + MCP (recommandé si licence Copilot)

### Prérequis

- VS Code **≥ 1.102** (MCP GA depuis juillet 2025)
- Extension GitHub Copilot installée
- Licence Copilot (Free, Pro, Business, Enterprise)
- Agent harness installé (`mise run agent:setup`)

### Étape 1 — Config MCP

Le fichier `.vscode/mcp.json` est déjà dans le repo. Ouvrir le dossier `copilot-gemma4/` dans VS Code.

Si le fichier n'est pas détecté, le créer :

```json
{
  "servers": {
    "agent-harness": {
      "type": "stdio",
      "command": "harness",
      "args": [
        "mcp-serve",
        "--profile", "config/profiles/dev.yaml",
        "--workspace", "${workspaceFolder}"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

> **Attention** : la clé racine est `"servers"` (pas `"mcpServers"` — c'est le format Cline/Claude Desktop).

### Étape 2 — Activer le mode Agent

1. Ouvrir le chat Copilot : **Ctrl+Alt+I**
2. En haut du panneau, cliquer sur le **dropdown du mode**
3. Sélectionner **Agent**

Les 3 modes :
- **Ask** : questions, ne touche pas au code
- **Edit** : éditions multi-fichiers guidées (Tab pour accepter, Alt+Delete pour rejeter)
- **Agent** : autonome, lit/écrit/exécute/corrige en boucle + appelle les outils MCP

### Étape 3 — Vérifier les outils MCP

Dans le mode Agent, cliquer sur l'icône **outils** (puzzle) en bas du chat.
Les outils du harness doivent apparaître en vert :
`read_file`, `list_dir`, `search_files`, `write_file`, `edit_file`, `bash`, `search_rag`

### Étape 4 — Choisir le modèle

Cliquer sur le **nom du modèle** dans le champ de saisie du chat.

Modèles recommandés :

| Modèle | Forces | Quand l'utiliser |
|---|---|---|
| **Claude Sonnet 4.6** | Excellent pour le code | Tâches quotidiennes |
| **Claude Opus 4.6** | Le plus capable | Architecture, refactoring complexe |
| **GPT-4.1** | Bon généraliste, rapide | Usage courant |
| **GPT-5 mini** | Ultra rapide | Questions simples |
| **Auto** | Choix automatique | Défaut recommandé |

### Étape 5 — Utiliser

```
Lis le fichier src/main/java/.../DsnService.java et explique le flux de réception des fragments
```

```
Cherche dans les skills la procédure de rollback GitOps avec ArgoCD
```

```
Lance mvn test et corrige les tests qui échouent
```

### Custom agents (.agent.md)

Le repo contient déjà des chatmodes. **Renommer** les fichiers `.chatmode.md` en `.agent.md` pour VS Code récent :

```
.github/agents/
  gemma-agent.agent.md       ← mode coding
  ops-investigation.agent.md ← mode ops
```

Format :
```markdown
---
description: Agent coding avec outils harness
name: Coding Agent
tools: ['agent-harness']
---
# Instructions
Tu es un agent de développement avec accès aux outils du harness...
```

### Custom instructions

Le fichier `.github/copilot-instructions.md` est automatiquement lu par Copilot. Déjà en place dans le repo.

Fichiers supplémentaires reconnus :
- `AGENTS.md` (activer avec `chat.useAgentsMdFile`)
- `CLAUDE.md` (activer avec `chat.useClaudeMdFile`)

---

## Option 2 : Continue.dev (recommandé pour offline / gratuit)

Continue.dev est une extension open source qui supporte nativement Ollama, les endpoints OpenAI-compatible, et MCP.

### Installation

1. VS Code → Extensions → chercher **Continue** → Installer
2. Le panneau Continue apparaît dans la barre latérale

### Config : harness comme modèle (via agent:serve)

Créer `~/.continue/config.yaml` :

```yaml
name: Pseudo-Copilot
version: 0.0.1
schema: v1

models:
  - name: Gemma 4 Coding (Harness)
    provider: openai
    model: gemma4-coding
    apiBase: http://127.0.0.1:11500/v1
    apiKey: any-key-works
    roles:
      - chat
      - edit
```

Démarrer le serveur :
```bash
mise run agent:serve    # Gemma 4 coding, port 11500
```

### Config : harness comme serveur MCP

Créer `~/.continue/mcpServers/harness.yaml` :

```yaml
name: Agent Harness MCP
version: 0.0.1
schema: v1
mcpServers:
  - name: agent-harness
    type: stdio
    command: /chemin/complet/copilot-gemma4/agent-harness/.venv/bin/harness
    args:
      - mcp-serve
      - --profile
      - /chemin/complet/copilot-gemma4/agent-harness/config/profiles/dev.yaml
      - --workspace
      - /chemin/complet/mon-projet
```

> Les outils MCP ne fonctionnent qu'en **mode agent** de Continue.

### Config : Ollama direct (sans harness)

```yaml
models:
  - name: Gemma 4 26B
    provider: ollama
    model: gemma4:26b-a4b-it-q8_0
    apiBase: http://localhost:11434
    defaultCompletionOptions:
      contextLength: 32768
```

> Avec Ollama direct, pas d'outils (pas de boucle agent). Utiliser `agent:serve`
> pour avoir les outils intégrés.

---

## Option 3 : Cline (agent autonome, gratuit)

Cline est un agent autonome qui peut créer des fichiers, éditer du code, exécuter des commandes.

### Installation

VS Code → Extensions → chercher **Cline** → Installer

### Config : harness comme modèle

Dans les settings Cline :
1. **API Provider** : OpenAI Compatible
2. **Base URL** : `http://127.0.0.1:11500/v1`
3. **API Key** : `any-key-works`
4. **Model ID** : `gemma4-coding`

### Config : harness comme serveur MCP

Cliquer sur l'icône MCP dans Cline → Configure → éditer `cline_mcp_settings.json` :

```json
{
  "mcpServers": {
    "agent-harness": {
      "command": "/chemin/complet/copilot-gemma4/agent-harness/.venv/bin/harness",
      "args": [
        "mcp-serve",
        "--profile", "/chemin/complet/copilot-gemma4/agent-harness/config/profiles/dev.yaml",
        "--workspace", "/chemin/complet/mon-projet"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      },
      "alwaysAllow": ["read_file", "list_dir", "search_files", "search_rag"],
      "disabled": false
    }
  }
}
```

> **Attention** : Cline utilise `"mcpServers"` comme clé racine (pas `"servers"`).

`alwaysAllow` évite la confirmation pour les outils read-only.

---

## Matrice de comparaison

| Fonctionnalité | Copilot | Continue.dev | Cline |
|---|---|---|---|
| **MCP** | Oui (GA v1.102+) | Oui (agent mode) | Oui |
| **Config MCP** | `.vscode/mcp.json` | `~/.continue/config.yaml` | `cline_mcp_settings.json` |
| **Clé racine JSON** | `"servers"` | `"mcpServers"` (YAML) | `"mcpServers"` |
| **Modèles cloud** | GPT, Claude, Gemini | Tout (BYOK) | Tout (BYOK) |
| **Ollama local** | Oui (BYOK) | Oui (natif) | Oui (OpenAI-compat) |
| **OpenAI-compat endpoint** | Preview (Insiders) | Oui (natif) | Oui (natif) |
| **Agent autonome** | Oui (mode Agent) | Oui (mode agent) | Oui (toujours) |
| **Multi-file edit** | Copilot Edits | Oui | Oui |
| **Custom agents** | `.agent.md` | Non | Non |
| **Custom instructions** | `.github/copilot-instructions.md` | System prompt | System prompt |
| **Sandbox MCP** | Oui (macOS/Linux) | Non | Non |
| **Open source** | Non | Oui | Oui |
| **Coût** | Licence Copilot | Gratuit | Gratuit |

---

## Quelle option choisir ?

| Situation | Recommandation |
|---|---|
| J'ai une licence Copilot Enterprise | **Copilot + MCP** (cerveau cloud + outils harness) |
| Je veux du offline / gratuit | **Continue.dev + agent:serve** (Gemma local + outils intégrés) |
| Je veux un agent autonome puissant | **Cline + agent:serve** (Gemma local, auto-correction) |
| Je veux combiner | Copilot pour la complétion inline + Continue.dev pour le chat local |

---

## Coexistence des extensions

Toutes ces extensions peuvent coexister dans VS Code :
- **Copilot** : complétion inline + chat cloud
- **Continue.dev** : chat local/cloud + MCP
- **Cline** : agent autonome + MCP

Pas de conflit de complétion (Copilot gère l'inline, Continue.dev et Cline gèrent le chat/agent).

---

## Troubleshooting

### Outils MCP non visibles (Copilot)

1. Vérifier VS Code **≥ 1.102**
2. Vérifier que le mode **Agent** est sélectionné (pas Ask/Edit)
3. Vérifier `.vscode/mcp.json` dans le workspace ouvert
4. Ctrl+Shift+P → **MCP: List Servers** → vérifier que le harness est listé
5. Ctrl+Shift+P → **MCP: Restart Server** → relancer le serveur

### agent:serve ne répond pas

```bash
# Vérifier que le serveur tourne
curl http://127.0.0.1:11500/v1/models

# Vérifier qu'Ollama tourne
curl http://localhost:11434/api/version

# Relancer
mise run agent:serve
```

### Continue.dev ne trouve pas Ollama

Vérifier `apiBase: http://localhost:11434` dans config.yaml.
Ollama doit être démarré : `ollama serve`

---

## Résumé des fichiers de config

| Quoi | Fichier |
|---|---|
| MCP Copilot (workspace) | `.vscode/mcp.json` |
| MCP Copilot (user) | Ctrl+Shift+P → MCP: Open User Configuration |
| MCP Continue.dev | `~/.continue/mcpServers/*.yaml` |
| MCP Cline | `cline_mcp_settings.json` (via UI Cline) |
| Modèles Continue.dev | `~/.continue/config.yaml` |
| Custom agents | `.github/agents/*.agent.md` |
| Instructions Copilot | `.github/copilot-instructions.md` |
| Settings VS Code | Ctrl+, → chercher "mcp" ou "copilot" |
