# copilot-gemma4

Déploiement local de modèles [Gemma 4](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/) (Google DeepMind) via [mise](https://mise.jdx.dev/) tasks, avec chat interactif et agents autonomes.

**26 tasks mise** : gestion de modèles, benchmarks, chat streaming, agents avec tool calling et RAG skills (via [agent-harness](agent-harness/)), TUI de suivi.

## Installation

```bash
# Cloner le repo (avec token PAT GitHub)
git clone https://<USER>:<TOKEN>@github.com/jddellac-hue/copilot-gemma4.git
# Exemple :
# git clone https://jddellac-hue:ghp_xxxxxxxxxxxxxxxxxxxx@github.com/jddellac-hue/copilot-gemma4.git

cd copilot-gemma4

# Mettre à jour (rebase depuis GitHub)
git pull --rebase origin main
```

## Setup complet (nouvelle machine)

```bash
# 1. Installer mise
curl https://mise.jdx.dev/install.sh | sh

# 2. Faire confiance au projet
cd copilot-gemma4
mise trust

# 3. Installer les prérequis (ollama, paquets système, venv Python)
mise run prereqs:install

# 4. Voir les modèles disponibles et la compatibilité de la machine
mise run model:evaluate

# 5. Installer le modèle recommandé
mise run model:install -- gemma4:26b-a4b-it-q8_0

# 6. Installer le harness agent (une fois par machine)
mise run agent:setup

# 7. Tester
mise run chat -- general
```

## Tasks disponibles

```bash
mise tasks   # lister toutes les tasks
```

---

### prereqs:install — Installer les prérequis

Installe ollama, détecte le GPU (NVIDIA/AMD), crée un virtualenv Python avec torch/transformers.

```bash
mise run prereqs:install
```

Ce qu'il fait :
- Installe les paquets système (build-essential, python3-venv, curl, git...)
- Détecte GPU NVIDIA → installe les drivers si besoin
- Installe ollama + démarre le service
- Crée un virtualenv Python (`~/venvs/gemma4`) avec torch, transformers, llama-cpp-python

### prereqs:uninstall — Désinstaller les outils

Supprime ollama et le virtualenv Python. Les données des modèles dans `~/.ollama` sont conservées.

```bash
mise run prereqs:uninstall
```

---

### model:evaluate — Évaluer les modèles disponibles

Liste tous les modèles Gemma 4 disponibles en ligne (ollama), indique ceux installés localement, et calcule un score de compatibilité selon la config machine (CPU, RAM, disque).

```bash
mise run model:evaluate
```

Exemple de sortie :
```
gemma4:26b             18GB   18 Go   100%   OUI   Sweet spot MoE, qualité proche du 31B
gemma4:31b             20GB   22 Go   100%   OUI   Plus capable, dense, lent en CPU
gemma4:31b-it-bf16     63GB   64 Go   0%     -     31B pleine précision
```

### model:install — Installer un modèle

Télécharge un modèle via ollama. Accepte n'importe quel tag disponible.

```bash
# Installer un modèle spécifique
mise run model:install -- gemma4:26b
mise run model:install -- gemma4:31b-it-q8_0
mise run model:install -- gemma4:e2b

# Le préfixe gemma4: est optionnel
mise run model:install -- 26b
```

### model:uninstall — Désinstaller un modèle

Décharge le modèle de la mémoire puis le supprime.

```bash
mise run model:uninstall -- gemma4:26b
mise run model:uninstall -- 31b
```

### model:list — Lister les modèles installés

Affiche les modèles installés et leur statut.

```bash
mise run model:list
```

### model:start — Démarrer un modèle

Démarre le service ollama si nécessaire, décharge les autres modèles de la RAM, et précharge le modèle demandé. Utile avant de lancer un chat, un agent ou un eval (évite le cold start de ~25s).

```bash
# Démarrer le modèle coding/doc
mise run model:start -- gemma4:26b-a4b-it-q8_0

# Démarrer le modèle général (rapide)
mise run model:start -- 26b

# Voir ce qui tourne sans rien changer
mise run model:start
```

### model:stop — Décharger un modèle

Libère la RAM en déchargeant un modèle (ou tous) de la mémoire.

```bash
# Décharger un modèle spécifique
mise run model:stop -- gemma4:26b

# Tout décharger
mise run model:stop -- all

# Idem (all est le défaut)
mise run model:stop
```

---

### chat — Chat interactif

Conversation multi-turn en streaming avec Gemma 4. Un seul point d'entrée avec rôle en paramètre.

```bash
# Chat agent de code (26B MoE Q8, temp 0.2, orienté code)
mise run chat -- coding

# Chat agent de documentation (26B MoE Q8, temp 0.3, orienté rédaction)
mise run chat -- doc

# Chat général (26B Q4, rapide, polyvalent)
mise run chat -- general
```

Commandes disponibles dans le chat :
```
/help       Afficher l'aide
/clear      Effacer l'historique de conversation
/system     Voir le prompt système
/model      Voir le modèle utilisé
/stats      Stats de la dernière réponse (tokens, vitesse)
/save       Sauvegarder la conversation en Markdown
/quit       Quitter (ou Ctrl+D)
```

Changer le modèle ponctuellement :
```bash
GEMMA4_CODING_MODEL=gemma4:26b mise run chat -- coding
```

Changer le modèle par défaut : éditer `mise.toml` → `GEMMA4_CODING_MODEL`.

---

### agent:coding / agent:doc — Agent avec outils (harness)

Agents autonomes avec tool calling (lecture/écriture fichiers, bash sandboxé), permissions, et audit. Basés sur [agent-harness](agent-harness/).

```bash
# Agent coding : exécute une tâche de code dans le workspace courant
mise run agent:coding -- "Écris une fonction de tri rapide dans src/sort.py"
mise run agent:coding -- "Trouve et corrige les bugs dans main.py"
mise run agent:coding -- "Ajoute des tests unitaires pour utils.py"

# Agent doc : exécute une tâche de documentation
mise run agent:doc -- "Écris un README.md pour ce projet"
mise run agent:doc -- "Documente toutes les fonctions de scripts/chat.py"
mise run agent:doc -- "Génère un CHANGELOG à partir des commits git"

# Travailler sur un autre dossier
mise run agent:coding -- "Refactorise le code" /chemin/vers/projet
```

Différence chat vs agent :

| | `chat` | `agent:*` |
|---|---|---|
| Mode | Conversation interactive | Tâche one-shot |
| Outils | Aucun (texte pur) | Fichiers, bash, recherche |
| Permissions | - | allow/ask/deny + audit |
| Sandbox | - | bubblewrap |
| Multi-turn | Oui | Non (une tâche = une exécution) |

### agent:mcp — Serveur MCP pour IDE

Expose les outils du harness comme serveur MCP, connectable depuis VS Code, Copilot, Claude Desktop.

```bash
# Démarrer le serveur MCP (mode coding)
mise run agent:mcp -- coding

# Mode documentation
mise run agent:mcp -- doc
```

### agent:eval — Évaluation du harness

Lance les 7 tâches d'évaluation du harness (read, search, edit, test, fix, ops, redteam).

```bash
mise run agent:eval -- gemma4          # Gemma 4 26B MoE (~8 min)
mise run agent:eval -- gemma4-light    # Gemma 4 E4B (~10 min)
mise run agent:eval -- claude          # Claude Sonnet (~2 min, ANTHROPIC_API_KEY)
mise run agent:eval -- copilot         # GitHub Copilot (~2 min, GITHUB_TOKEN)
```

> **Astuce** : préchauffer le modèle avant l'eval réduit le cold start (~25s) :
> `mise run model:start -- gemma4:26b-a4b-it-q8_0` puis `mise run agent:eval -- gemma4`

---

### agent:setup — Installer le harness (une fois par machine)

Crée le virtualenv Python et installe les dépendances de agent-harness. À faire une fois après le clone sur chaque machine.

```bash
mise run agent:setup

# Réinstaller
mise run agent:setup -- --force
```

---

### test:verify — Vérifier qu'un modèle fonctionne

Envoie un prompt de test, mesure le temps de réponse, puis décharge le modèle de la mémoire.

```bash
mise run test:verify -- gemma4:26b
```

### test:bench — Benchmarker un modèle

Lance 10 prompts (5 coding + 5 doc) avec timeouts (300s coding, 180s doc), calcule un score UX, et sauvegarde les résultats dans `.mise/benchmarks/`. Demande confirmation si un bench existe déjà.

```bash
mise run test:bench -- gemma4:26b all        # 10 prompts coding+doc
mise run test:bench -- gemma4:26b coding     # 5 prompts coding
mise run test:bench -- gemma4:26b doc        # 5 prompts doc
```

---

### tui:bench — Suivre un benchmark en direct

TUI graphique à lancer dans une **autre console** pendant qu'un bench tourne.

```bash
# Console 1 : lancer le bench
mise run test:bench -- gemma4:26b all

# Console 2 : suivre en direct
mise run tui:bench
```

### tui:install — Suivre les modèles et téléchargements

TUI montrant les modèles installés, chargés en mémoire, et l'espace disque.

```bash
mise run tui:install
```

---

### clean — Nettoyage profond

Supprime **tout** : modèles, données ollama, binaire, service, virtualenvs Python, cache HuggingFace. Calcule l'espace récupéré.

```bash
mise run clean
```

> **Attention** : irréversible. Tout devra être retéléchargé.

Différence avec `prereqs:uninstall` :

| | `prereqs:uninstall` | `clean` |
|---|---|---|
| Supprime ollama | oui | oui |
| Supprime le venv Python | oui | oui |
| Supprime les modèles (`~/.ollama`) | non | **oui** |
| Supprime le cache HuggingFace | non | **oui** |
| Supprime l'utilisateur système | non | **oui** |

---

## Choix du modèle

Les modèles par défaut sont configurés dans `mise.toml` :

```toml
GEMMA4_CODING_MODEL = "gemma4:26b-a4b-it-q8_0"
GEMMA4_DOC_MODEL = "gemma4:26b-a4b-it-q8_0"
GEMMA4_GENERAL_MODEL = "gemma4:26b-a4b-it-q8_0"
```

Pour changer ponctuellement :
```bash
GEMMA4_CODING_MODEL=gemma4:e4b mise run chat -- coding
```

Pour changer durablement : éditer `mise.toml`.

### Modèles recommandés (AMD Ryzen 9 5900HX, 62 Go RAM, CPU-only)

| Usage | Modèle | RAM | Vitesse | Score UX |
|-------|--------|-----|---------|----------|
| **Agent coding** | `gemma4:26b-a4b-it-q8_0` | ~30 Go | ~30 tok/s | 95/100 Excellent |
| **Agent doc** | `gemma4:26b-a4b-it-q8_0` | ~30 Go | ~34 tok/s | 95/100 Excellent |
| **Usage général** | `gemma4:26b` | ~18 Go | ~33 tok/s | 95/100 Excellent |
| **Ultra léger** | `gemma4:e4b` | ~12 Go | ~34 tok/s | 95/100 Excellent |

> **Le 31B Dense est inutilisable en CPU-only** (100% timeout sur les benchmarks).
> L'architecture MoE du 26B (3.8B params actifs sur 25.2B total) est idéale pour le CPU :
> qualité proche du 31B, vitesse 10x supérieure.

### Pourquoi le même modèle pour coding et doc ?

Le `gemma4:26b-a4b-it-q8_0` est le seul modèle qui combine qualité Q8 et vitesse utilisable en CPU. La différence se fait par la **configuration** :
- **Coding** : temperature 0.2, bash autorisé, write en mode ask
- **Doc** : temperature 0.3, write auto-allow, bash interdit

## Benchmarks

Les résultats sont dans `benchmarks/`. Lancez un bench avec :
```bash
mise run test:bench -- gemma4:26b all        # 10 prompts coding+doc
mise run test:bench -- gemma4:26b coding     # 5 prompts coding
mise run test:bench -- gemma4:26b doc        # 5 prompts doc
```

Suivez en direct depuis une autre console :
```bash
mise run tui:bench
```

## Structure du projet

```
copilot-gemma4/
├── mise.toml                          # Config (modèles par défaut, env vars)
├── README.md
├── scripts/
│   ├── chat.py                        # Chat interactif streaming
│   ├── ensure-model.sh                # Vérif auto ollama + modèle + preload
│   └── harness-run.sh                 # Helper commun pour les tasks agent
├── .mise/
│   ├── benchmarks/                    # Résultats sauvegardés
│   └── tasks/
│       ├── prereqs/install|uninstall  # Prérequis système
│       ├── model/                     # evaluate|install|uninstall|list|start|stop
│       ├── test/                      # bench|verify|tasks|system
│       ├── tui/bench|install          # Interfaces TUI
│       ├── chat                       # Chat interactif (coding|doc|general)
│       ├── agent/                     # coding|doc|claude|copilot|mcp|serve|eval|setup
│       ├── verify                     # Vérification complète
│       └── clean                      # Nettoyage profond
├── skills/                            # 18 skills RAG (angular, java, oracle, quarkus, k8s...)
└── agent-harness/                     # Harness agentique
    ├── config/profiles/               # 11 profils (dev, ci, coding, ops, claude, copilot...)
    ├── src/harness/                   # Agent ReAct, tools, permissions, sandbox, skills RAG
    ├── eval/tasks/                    # 7 tâches d'évaluation
    └── .venv/                         # (gitignored, créé via agent:setup)
```

## Toutes les tasks

```
prereqs:install    Installer les prérequis (ollama, GPU drivers, Python venv)
prereqs:uninstall  Désinstaller les prérequis
model:evaluate     Lister les modèles disponibles et évaluer la compatibilité
model:install      Installer un modèle
model:uninstall    Désinstaller un modèle
model:list         Lister les modèles installés
model:start        Démarrer/précharger un modèle en mémoire
model:stop         Décharger un modèle de la mémoire
chat               Chat interactif (coding|doc|general)
agent:coding       Agent coding avec tools + skills RAG (Gemma 4 local)
agent:doc          Agent documentation avec tools + skills RAG (Gemma 4 local)
agent:claude       Agent coding (Claude Sonnet, en ligne)
agent:copilot      Agent coding (GitHub Copilot, en ligne)
agent:mcp          Serveur MCP pour IDE
agent:serve        Serveur OpenAI-compatible pour IntelliJ/Continue.dev
agent:eval         Suite d'évaluation du harness (7 tâches)
agent:setup        Installer le venv agent-harness
test:bench         Benchmarker un modèle (coding/doc/all)
test:verify        Vérifier qu'un modèle fonctionne
test:system        Tests système end-to-end
test:tasks         Tests unitaires des tasks mise
tui:bench          TUI suivi benchmark en direct
tui:install        TUI suivi modèles et téléchargements
skills:reindex     Reconstruire la base vectorielle Chroma (après ajout de skills)
verify             Vérification complète (prérequis, install, tests, eval)
clean              Nettoyage profond (tout supprimer)
```
