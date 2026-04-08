# Mode opératoire : MCP Agent Harness dans Copilot Chat IntelliJ

> Guide pas-à-pas pour connecter notre agent harness (squelette + outils)
> au cerveau Copilot (GPT-4.1, Claude, Gemini, etc.) dans IntelliJ IDEA Ultimate.

---

## Principe : squelette vs cerveau

```
┌─────────────────────────────────────┐
│  Copilot Chat (IntelliJ)            │
│  Cerveau : GPT-4.1, Claude, Gemini │  ← modèle choisi par l'utilisateur
│                                     │
│  ↕ appels d'outils via MCP ↕       │
│                                     │
│  Agent Harness (notre MCP server)   │
│  Squelette : filesystem, bash,      │  ← lancé automatiquement par le plugin
│  skills RAG, Dynatrace, K8s, etc.  │
└─────────────────────────────────────┘
```

**Le cerveau** (le modèle LLM) raisonne et décide quels outils appeler.
**Le squelette** (notre harness) exécute les outils dans un sandbox sécurisé.

L'utilisateur choisit le cerveau dans le chat Copilot. Le squelette est toujours le même.

---

## Prérequis

| Prérequis | Comment vérifier |
|---|---|
| IntelliJ IDEA Ultimate | `Help > About` |
| Plugin GitHub Copilot **≥ 1.5.57** | `Settings > Plugins > Installed > GitHub Copilot` |
| Compte Copilot Enterprise (ou Business/Pro) | github.com > Settings > Copilot |
| Agent harness installé | `mise run agent:setup` |
| **MCP activé par l'admin org** | Voir section "Activation admin" ci-dessous |

### Activation admin (obligatoire pour Enterprise/Business)

L'admin de l'organisation GitHub doit activer MCP :

1. Aller sur **github.com** → **Organization Settings**
2. **Code, planning, and automation** → **Copilot** → **Policies**
3. **Features** → **MCP servers in Copilot** → **Enabled**

Sans cette activation, les outils MCP ne seront pas disponibles dans le chat.

---

## Étape 1 — Installer le harness (une seule fois)

```bash
cd ~/IdeaProjects/mon-projet/copilot-gemma4
mise trust
mise run agent:setup
```

Vérifier que ça fonctionne :
```bash
mise run skills:reindex    # doit afficher 18/18 domaines vérifiés
```

---

## Étape 2 — Vérifier la config MCP dans le projet

Le repo contient déjà les fichiers de config MCP :

```
copilot-gemma4/
├── .vscode/mcp.json                          ← lu par IntelliJ ET VS Code
└── agent-harness/
    └── .github/
        ├── mcp/servers.json                  ← config MCP détaillée
        └── chatmodes/
            ├── gemma-agent.chatmode.md       ← mode coding
            └── ops-investigation.chatmode.md ← mode ops
```

Le fichier `.vscode/mcp.json` est le plus fiable pour IntelliJ :

```json
{
  "servers": {
    "agent-harness": {
      "command": "harness",
      "args": [
        "mcp-serve",
        "--profile", "config/profiles/dev.yaml",
        "--workspace", "${workspaceFolder}"
      ]
    }
  }
}
```

> **Si IntelliJ ne détecte pas automatiquement le fichier**, voir Étape 2b.

### Étape 2b — Configuration manuelle (si auto-discovery ne marche pas)

1. **Settings** (Ctrl+Alt+S) → **Tools** → **GitHub Copilot**
2. Chercher la section **Model Context Protocol (MCP)**
3. Cliquer **Configure** pour ouvrir le `mcp.json` de l'IDE
4. Ajouter la config du harness :

```json
{
  "servers": {
    "agent-harness": {
      "type": "stdio",
      "command": "/chemin/complet/vers/copilot-gemma4/agent-harness/.venv/bin/harness",
      "args": [
        "mcp-serve",
        "--profile", "/chemin/complet/vers/copilot-gemma4/agent-harness/config/profiles/dev.yaml",
        "--workspace", "/chemin/complet/vers/mon-projet"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

5. **Sauvegarder** (Ctrl+S)
6. **Redémarrer IntelliJ** si les outils n'apparaissent pas

---

## Étape 3 — Activer le mode Agent dans le chat

1. Cliquer sur l'icône **GitHub Copilot** (barre de statut en bas à droite)
2. Cliquer **Open Chat**
3. En haut du panneau chat, cliquer sur le **menu déroulant du mode**
4. Sélectionner **"Agent"** (ou "Agent (Preview)")

Le mode Agent donne accès à Copilot pour :
- Chercher dans le workspace
- Lire/écrire des fichiers
- Exécuter des commandes terminal
- **Appeler les outils MCP** de notre harness

---

## Étape 4 — Choisir le modèle (cerveau)

1. Dans le panneau Copilot Chat, regarder en **bas à droite** du chat
2. Cliquer sur le **menu déroulant du modèle**
3. Choisir le modèle souhaité

### Modèles recommandés

| Modèle | Forces | Coût (premium requests) | Recommandation |
|---|---|---|---|
| **GPT-4.1** | Bon généraliste, rapide | 1x | Usage quotidien |
| **Claude Sonnet 4.5/4.6** | Excellent pour le code, raisonnement | 1x | Tâches de code complexes |
| **Claude Opus 4.5/4.6** | Le plus capable, analyse profonde | ~5x | Architecture, refactoring majeur |
| **Gemini 2.5 Pro** | Contexte long, multimodal | 1x | Analyse de gros fichiers |
| **GPT-5 mini** | Rapide, économique | 0.25x | Questions simples |
| **Auto** | Choix automatique | Variable | Évite le rate limiting |

> **Conseil** : utiliser **Auto** par défaut. Switcher sur **Claude Opus** pour les tâches
> d'architecture ou de refactoring complexe.

### Modèles disponibles par plan

| Plan | Modèles |
|---|---|
| **Enterprise** (39$/seat) | Tous, y compris Opus, 1000 premium/mois |
| **Business** (19$/seat) | Tous sauf Opus fast, 300 premium/mois |
| **Pro** (10$/mois) | Tous sauf Opus fast, 300 premium/mois |

---

## Étape 5 — Utiliser les outils du harness dans le chat

Une fois en mode Agent avec le MCP connecté, poser des questions qui utilisent les outils :

### Exemples de prompts

**Exploration de code :**
```
Lis le fichier src/main/java/fr/pe/rind/service/dd017/dsn/DsnService.java
et explique ce qu'il fait
```

**Recherche dans les skills (RAG) :**
```
Cherche dans les skills comment configurer un consumer Kafka dans Quarkus
avec une stratégie d'acknowledgment at-least-once
```

**Exécution sandbox :**
```
Lance les tests unitaires et dis-moi lesquels échouent
```

**Ops (si profil ops configuré) :**
```
Quels sont les pods en CrashLoopBackOff dans le namespace app-backend ?
Montre-moi les problèmes Dynatrace ouverts sur la dernière heure
```

### Vérifier que les outils sont connectés

Taper dans le chat :
```
Quels outils MCP as-tu à disposition ?
```

Copilot doit lister : `read_file`, `list_dir`, `search_files`, `write_file`, `edit_file`, `bash`, `search_skills`, etc.

---

## Limitations connues

### Fonctionnelles

| Limitation | Détail |
|---|---|
| **Pas de complétion inline** | MCP fonctionne uniquement dans le **chat Agent**, pas dans l'auto-complétion de code |
| **Confirmation double** | Copilot demande confirmation avant chaque appel d'outil (sécurité, pas contournable) |
| **OAuth non supporté dans JetBrains** | Pour les MCP distants, utiliser un PAT au lieu d'OAuth |
| **Chatmodes partiels** | Les fichiers `.chatmode.md` sont reconnus mais le UI de switch est limité vs VS Code |
| **Claude Sonnet 4.6 non dispo** | Ce modèle est exclusif VS Code / github.com pour l'instant |

### Performance

| Limitation | Impact |
|---|---|
| Le serveur MCP se relance à chaque session chat | Premier appel d'outil ~5-10s (chargement Chroma) |
| Premium requests limités par plan | Opus consomme ~5x plus que GPT-4.1 |
| Latence réseau | Le modèle tourne chez GitHub, pas en local |

### Sécurité

- L'admin org peut **restreindre les MCP** au registre uniquement (pas de serveurs arbitraires)
- Le harness tourne en local — les **données ne quittent pas la machine** (seules les requêtes au modèle vont dans le cloud)
- Le sandbox empêche les opérations dangereuses (rm -rf, sudo, .ssh, etc.)
- Chaque appel d'outil est confirmé par l'utilisateur

---

## Troubleshooting

### Les outils MCP n'apparaissent pas

1. Vérifier la version du plugin : **≥ 1.5.57** (Settings > Plugins)
2. Vérifier que le mode **Agent** est sélectionné (pas "Ask" ni "Edit")
3. Vérifier que `.vscode/mcp.json` existe dans le projet ouvert
4. **Redémarrer IntelliJ** (les changements de config MCP nécessitent parfois un restart)
5. Vérifier les logs : Help > Show Log in Finder/Explorer, chercher "MCP" ou "copilot"

### Le serveur MCP ne démarre pas

```bash
# Tester manuellement
cd copilot-gemma4/agent-harness
.venv/bin/harness mcp-serve --profile config/profiles/dev.yaml --workspace .
# Doit afficher les logs du serveur MCP (pas d'erreur)
# Ctrl+C pour arrêter
```

Si erreur Python :
```bash
mise run agent:setup -- --force   # réinstaller le harness
```

### Le modèle ne voit pas les outils

- Vérifier le chat est en mode **Agent** (pas "Ask")
- Cliquer sur l'icône **outils** (puzzle/plug) en bas du chat pour voir les outils détectés
- Si vide : la config MCP n'est pas chargée → étape 2b (config manuelle)

### L'admin org n'a pas activé MCP

Message type : "MCP tools are not available for your organization"

→ Demander à l'admin : **Organization Settings > Copilot > Policies > Features > MCP servers in Copilot = Enabled**

---

## Résumé des chemins dans l'IDE

| Quoi | Où |
|---|---|
| Config MCP projet | `.vscode/mcp.json` dans la racine du projet |
| Config MCP IDE | Settings > Tools > GitHub Copilot > MCP > Configure |
| Mode Agent | Dropdown en haut du panneau Copilot Chat |
| Choix du modèle | Dropdown en bas à droite du panneau Copilot Chat |
| Chatmodes | `.github/chatmodes/*.chatmode.md` |
| Instructions | `.github/copilot-instructions.md` |
| Logs | Help > Show Log in Finder/Explorer |
| Feedback/bugs | https://github.com/microsoft/copilot-intellij-feedback/issues |
