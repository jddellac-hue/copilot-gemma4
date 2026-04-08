# Mode opératoire : Agent Harness dans JetBrains AI Assistant

> Guide pas-à-pas pour connecter notre agent harness à JetBrains AI Assistant
> dans IntelliJ IDEA Ultimate. Couvre les 3 méthodes d'intégration : MCP,
> OpenAI-compatible endpoint, et coexistence avec Copilot.

---

## Les 3 modes d'intégration

| Mode | Comment ça marche | Cerveau | Outils harness |
|---|---|---|---|
| **MCP client** | AI Assistant appelle les outils du harness | JetBrains AI (Claude, GPT, Gemini) | Oui (via MCP) |
| **OpenAI-compatible** | AI Assistant utilise le harness comme LLM | Gemma local (ou Claude/Copilot via harness) | Intégrés dans la boucle agent |
| **Built-in MCP server** | Le harness (ou Claude Code) pilote l'IDE | Externe (Claude Code, Cursor, etc.) | L'IDE expose ses propres outils |

---

## Mode 1 : MCP client (recommandé)

AI Assistant appelle les outils du harness (filesystem, bash, skills RAG, etc.)
en utilisant un modèle cloud comme cerveau.

### Prérequis

- IntelliJ IDEA **2025.1+**
- Plugin **AI Assistant** installé (inclus avec All Products Pack)
- Agent harness installé (`mise run agent:setup`)

### Étape 1 — Configurer le serveur MCP

1. **Settings** (Ctrl+Alt+S) → **Tools** → **AI Assistant** → **Model Context Protocol (MCP)**
2. Cliquer **Add**
3. Choisir **STDIO** comme type de transport
4. Coller la configuration JSON :

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
      }
    }
  }
}
```

> Remplacer `/chemin/complet/` par les vrais chemins de votre machine.

5. Scope : **Global** (tous les projets) ou **Project** (ce projet seulement)
6. Cliquer **Apply**

### Étape 2 — Choisir le modèle (cerveau)

1. **Settings** → **Tools** → **AI Assistant** → **Models Assignment**
2. Pour **Core features**, choisir un modèle capable de tool calling :
   - **Claude Sonnet 4.6** (recommandé pour le code)
   - **GPT-4.1** (bon généraliste)
   - **Gemini 2.5 Pro** (contexte long)

> **Limitation importante** : les modèles locaux (Ollama) **ne supportent PAS**
> le tool calling MCP dans AI Assistant. Utiliser un modèle cloud.

### Étape 3 — Utiliser dans le chat

1. Ouvrir le panneau **AI Assistant** (barre latérale droite ou Alt+Entrée)
2. Poser des questions qui déclenchent les outils :

```
Lis le fichier pom.xml et dis-moi la version de Quarkus utilisée
```

```
Cherche dans les skills comment configurer un dead letter exchange RabbitMQ
```

```
Lance la commande "mvn test -pl impl" et dis-moi si les tests passent
```

AI Assistant appelle automatiquement les outils MCP quand c'est pertinent.

### Outils exposés par le harness

| Outil | Ce qu'il fait |
|---|---|
| `read_file` | Lire un fichier du workspace |
| `list_dir` | Lister un répertoire |
| `search_files` | Chercher des fichiers par glob |
| `write_file` | Écrire un fichier (avec confirmation) |
| `edit_file` | Modifier un fichier (avec confirmation) |
| `bash` | Exécuter une commande dans le sandbox |
| `search_skills` | Chercher dans les 18 skills RAG |

En profil ops, s'ajoutent : `dynatrace_dql`, `kubectl_get`, `search_runbooks`, `concourse_pipelines`, etc.

---

## Mode 2 : OpenAI-compatible endpoint (Gemma local dans AI Assistant)

Le harness expose un endpoint `/v1/chat/completions` qui fait tourner
une session agent complète (modèle + outils) pour chaque requête.

### Étape 1 — Démarrer le serveur

```bash
mise run agent:serve              # Gemma 4 coding (défaut)
mise run agent:serve -- doc       # Gemma 4 documentation
mise run agent:serve -- claude    # Claude (en ligne)
```

Le serveur écoute sur `http://127.0.0.1:11500/v1`.

### Étape 2 — Configurer AI Assistant

1. **Settings** → **Tools** → **AI Assistant** → **Providers & API keys**
2. Dans **Third-party AI providers**, cliquer sur le dropdown Provider
3. Sélectionner **OpenAI-compatible**
4. Remplir :
   - **API Key** : `any-key-works` (le serveur n'authentifie pas)
   - **URL** : `http://127.0.0.1:11500/v1`
5. Cliquer **Test Connection** → doit afficher succès
6. Cliquer **Apply**

### Étape 3 — Assigner le modèle

1. Dans **Models Assignment**, pour **Core features** :
   - Sélectionner le modèle du endpoint OpenAI-compatible
2. Optionnel : garder un modèle cloud pour **Instant helpers** (plus rapide)

### Étape 4 — Utiliser

Le chat AI Assistant utilise maintenant Gemma local comme cerveau.
Chaque message déclenche une session agent complète avec outils intégrés.

```
Explique l'architecture de ce projet
```

> **Avantage** : offline, gratuit, données restent en local.
> **Inconvénient** : plus lent que les modèles cloud (~5-30s par réponse),
> les outils MCP d'AI Assistant ne fonctionnent pas avec les modèles locaux.

---

## Mode 3 : Built-in MCP server (l'IDE expose ses outils)

Depuis IntelliJ 2025.2, l'IDE lui-même peut devenir un serveur MCP,
permettant à des agents externes (Claude Code, Cursor, etc.) de piloter l'IDE.

### Activer

1. **Settings** → **Tools** → **MCP Server**
2. Cocher **Enable MCP Server**
3. Dans **Clients Auto-Configuration**, cliquer **Auto-Configure** pour le client souhaité :
   - Claude Desktop
   - Claude Code
   - Cursor
   - VS Code

### 30+ outils IDE exposés

| Catégorie | Outils |
|---|---|
| **Code** | `get_file_text_by_path`, `create_new_file`, `replace_text_in_file`, `reformat_file` |
| **Analyse** | `get_file_problems`, `get_symbol_info`, `search_in_files_by_regex` |
| **Navigation** | `find_files_by_glob`, `list_directory_tree`, `get_project_modules` |
| **Exécution** | `execute_run_configuration`, `execute_terminal_command` |
| **Refactoring** | `rename_refactoring` |
| **Base de données** | `list_database_connections`, `execute_sql_query`, `preview_table_data` |

### Mode Brave

Dans Settings > MCP Server, activer **Brave Mode** pour exécuter les commandes
sans confirmation utilisateur à chaque fois. À utiliser en développement, pas en production.

---

## Coexistence AI Assistant + Copilot

Les deux plugins peuvent coexister, avec une **limitation** :

| Fonctionnalité | AI Assistant | Copilot | Conflit ? |
|---|---|---|---|
| Chat | Oui | Oui | Non (deux panneaux séparés) |
| Code completion inline | Oui | Oui | **OUI — un seul actif** |
| MCP client | Oui (2025.1+) | Oui (1.5.57+) | Non (configs séparées) |
| MCP server (IDE) | Oui (2025.2+) | Non | Non |
| Agent autonome | Junie (2026.1+) | Copilot Agent | Non (séparés) |

### Résoudre le conflit de complétion

Si les deux sont installés, un warning apparaît dans `Settings > Editor > General > Inline completion`.

**Option A** : Désactiver la complétion AI Assistant, garder Copilot pour la complétion :
- Settings → Tools → AI Assistant → décocher **Code completion**

**Option B** : Désactiver le plugin Copilot, tout faire avec AI Assistant :
- Settings → Plugins → GitHub Copilot → Disable

**Option C** : Utiliser les deux pour des rôles différents :
- Copilot : complétion inline (gratuit avec licence)
- AI Assistant : chat + MCP + Junie (BYOK avec propres clés API)

---

## Modèles locaux vs cloud — matrice de décision

| Besoin | Modèle recommandé | Via |
|---|---|---|
| Chat rapide, code review | Claude Sonnet 4.6 (cloud) | AI Assistant natif |
| Offline, données sensibles | Gemma 4 26B (local) | `agent:serve` → OpenAI-compatible |
| Outils MCP + raisonnement | Claude/GPT cloud | AI Assistant MCP client |
| Architecture complexe | Claude Opus 4.6 (cloud) | AI Assistant natif |
| Complétion inline | Copilot (cloud) | Plugin Copilot |
| Agent autonome | Junie (cloud) | AI Assistant 2026.1+ |
| Gratuit, pas de clé API | Gemma 4 local | `agent:serve` |

---

## Junie (agent autonome JetBrains)

Junie est l'agent autonome de JetBrains (depuis AI Assistant 2026.1).
Il peut planifier et exécuter des tâches multi-étapes : créer des fichiers,
éditer du code, lancer des commandes, exécuter des tests, vérifier les résultats.

### Utiliser Junie

1. Ouvrir le panneau AI Assistant
2. Cliquer sur le dropdown en haut du chat
3. Sélectionner le **logo Junie**
4. Donner une tâche complexe :

```
Ajoute des tests unitaires pour la classe DsnService.
Lance les tests, corrige les erreurs, et recommence jusqu'à ce que tout passe.
```

### Junie + MCP

Junie peut utiliser les serveurs MCP configurés dans AI Assistant.
Commande `/mcp` dans le chat pour gérer les serveurs.

### Junie CLI (standalone)

```bash
# Agent terminal autonome, indépendant de l'IDE
junie --provider anthropic --model claude-sonnet-4-6 "Refactorise le module auth"
```

---

## Tarification AI Assistant

| Plan | Prix | Crédits/mois | Clés API propres |
|---|---|---|---|
| **AI Free** | 0€ | 3 crédits | Oui (BYOK illimité) |
| **AI Pro** | 10€/mois | 10-20 crédits | Oui |
| **AI Ultimate** | 20-30€/mois | 35-70 crédits | Oui |
| **Inclus All Products Pack** | - | AI Pro inclus | Oui |

> **BYOK (Bring Your Own Key)** : utiliser ses propres clés API OpenAI/Anthropic
> ne consomme **aucun crédit JetBrains**. On paie directement le fournisseur.
> C'est la meilleure option avec un compte Anthropic ou OpenAI existant.

---

## Troubleshooting

### MCP tools non disponibles

1. Vérifier IntelliJ **≥ 2025.1**
2. Vérifier que le modèle assigné est un **modèle cloud** (pas local)
3. Vérifier la config MCP dans Settings → AI Assistant → MCP
4. Tester le serveur manuellement :
   ```bash
   .venv/bin/harness mcp-serve --profile config/profiles/dev.yaml --workspace .
   ```
5. Redémarrer IntelliJ

### OpenAI-compatible endpoint ne répond pas

1. Vérifier que `mise run agent:serve` tourne dans un terminal
2. Tester : `curl http://127.0.0.1:11500/v1/models`
3. Vérifier qu'Ollama tourne : `curl http://localhost:11434/api/version`

### Conflit complétion inline

Settings → Editor → General → Inline completion → voir le warning.
Désactiver la complétion de l'un des deux plugins.

---

## Résumé des chemins Settings

| Quoi | Où |
|---|---|
| Config MCP (client) | Settings → Tools → AI Assistant → Model Context Protocol (MCP) |
| Providers & API keys | Settings → Tools → AI Assistant → Providers & API keys |
| Models Assignment | Settings → Tools → AI Assistant → Models Assignment |
| MCP Server (IDE) | Settings → Tools → MCP Server |
| Code completion | Settings → Tools → AI Assistant → (décocher si conflit) |
| Inline completion | Settings → Editor → General → Inline completion |
| Plugin versions | Settings → Plugins → Installed |
