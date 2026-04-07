# Operator Runbook — Agent Harness

> **Audience** : ingénieur d'astreinte ou opérateur en charge du déploiement,
> de l'exploitation et du dépannage du harnais. Ce document **n'est pas** la
> KB de design (`docs/kb/agent-harness-kb.md`) — il répond à *« comment je
> fais marcher ce truc »* et *« pourquoi ça ne marche pas »*, pas à *«
> pourquoi c'est conçu comme ça »*.

## Sommaire

1. [Prérequis](#1-prérequis)
2. [Installation](#2-installation)
3. [Vérification post-installation](#3-vérification-post-installation)
4. [Démarrage rapide](#4-démarrage-rapide)
5. [Intégration GitHub Copilot](#5-intégration-github-copilot)
6. [Profils](#6-profils)
7. [Exploitation quotidienne](#7-exploitation-quotidienne)
8. [Mise à jour](#8-mise-à-jour)
9. [Sauvegarde et restauration](#9-sauvegarde-et-restauration)
10. [Surveillance et alertes](#10-surveillance-et-alertes)
11. [Dépannage](#11-dépannage)
12. [Procédures d'incident](#12-procédures-dincident)
13. [Désinstallation](#13-désinstallation)

---

## 1. Prérequis

| Composant       | Version minimale | Vérification                       |
|-----------------|------------------|------------------------------------|
| OS              | Linux x86_64     | `uname -a`                         |
| Python          | 3.11             | `python3 --version`                |
| Ollama          | 0.4.0            | `ollama --version`                 |
| bubblewrap      | 0.6              | `bwrap --version`                  |
| git             | 2.30+            | `git --version`                    |
| RAM             | 8 Go (gemma:7b)  | `free -h`                          |
| Disque          | 15 Go libres     | `df -h`                            |

> Sur poste de dev sans `bwrap`, le sandbox bascule automatiquement sur le
> backend `subprocess`. C'est **acceptable en dev**, **pas en partage** ni en
> CI.

### Installation des prérequis (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv bubblewrap git
curl -fsSL https://ollama.com/install.sh | sh
```

---

## 2. Installation

### 2.1 Installation depuis le repo

```bash
git clone <url-du-repo> agent-harness
cd agent-harness

python3.11 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"
```

### 2.2 Téléchargement du modèle

```bash
ollama serve &                    # si pas déjà en service systemd
ollama pull gemma:7b-instruct
```

> **Bande passante** : ~5 Go pour `gemma:7b-instruct`. Compter 10–20 min sur
> connexion correcte.

### 2.3 Installation comme service systemd (optionnel, recommandé en prod)

Créer `/etc/systemd/system/agent-harness-mcp.service` :

```ini
[Unit]
Description=Agent Harness MCP server
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=harness
Group=harness
WorkingDirectory=/opt/agent-harness
Environment="PATH=/opt/agent-harness/.venv/bin:/usr/bin"
ExecStart=/opt/agent-harness/.venv/bin/harness mcp-serve \
    --profile config/profiles/prod-ro.yaml \
    --workspace /var/lib/harness/workspace
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/harness /var/log/harness
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agent-harness-mcp
sudo systemctl status agent-harness-mcp
```

---

## 3. Vérification post-installation

Cinq commandes à passer dans l'ordre :

```bash
# 1. Le binaire est trouvé
which harness

# 2. La CLI répond
harness --help

# 3. Ollama est joignable
curl -fsS http://localhost:11434/api/tags | jq '.models[].name'

# 4. Le sandbox fonctionne
python -c "
from harness.sandbox import Sandbox, SandboxConfig
s = Sandbox(SandboxConfig(backend='bubblewrap'))
r = s.run('echo ok && id', cwd='/tmp')
print('exit:', r.exit_code, 'stdout:', r.stdout.strip())
"

# 5. Les tests unitaires passent
pytest tests/unit -q
```

Tous les indicateurs au vert ? Tu peux passer en démarrage rapide.

---

## 4. Démarrage rapide

### 4.1 Session interactive (CLI)

```bash
harness run \
    --profile config/profiles/dev.yaml \
    --workspace ~/projects/mon-projet \
    "Liste les fichiers Java du projet et trouve les classes annotées @RestController"
```

### 4.2 Mode serveur MCP

```bash
harness mcp-serve --profile config/profiles/dev.yaml --workspace .
```

Le process bloque sur stdin/stdout en attendant qu'un client MCP se connecte.
Pour tester avec un client en ligne :

```bash
# Dans un autre terminal, l'inspecteur MCP officiel
npx @modelcontextprotocol/inspector harness mcp-serve \
    --profile config/profiles/dev.yaml \
    --workspace .
```

L'inspecteur ouvre une UI web qui liste les tools exposés et permet de les
appeler à la main — outil indispensable pour vérifier l'intégration.

---

## 5. Intégration GitHub Copilot

> **Avertissement honnête** : en avril 2026, le support Copilot+Ollama est
> mature en **VS Code**, partiel en **Copilot CLI** (BYOK fraîchement
> annoncé), et **limité en JetBrains/IntelliJ**. Le chemin le plus stable
> dans tous les cas est l'intégration **MCP** : Copilot conserve son propre
> modèle et appelle le harnais comme outil.

### 5.1 VS Code (toutes plateformes)

1. Le repo contient déjà `.vscode/mcp.json`. Ouvrir le workspace dans VS
   Code : Copilot détecte le serveur automatiquement.
2. Vérifier dans la palette : `MCP: List Servers` doit afficher
   `agent-harness`.
3. Dans Copilot Chat, basculer en **Agent mode** et taper :
   ```
   #agent-harness liste les fichiers Java du projet
   ```

### 5.2 Copilot CLI (BYOK + offline, recommandé pour usage air-gapped)

```bash
export COPILOT_PROVIDER=ollama
export COPILOT_MODEL=gemma:7b-instruct
export COPILOT_BASE_URL=http://localhost:11434/v1
export COPILOT_OFFLINE=true        # désactive toute télémétrie GitHub
copilot
```

Le harnais peut être utilisé en parallèle via `harness run` ou exposé via
MCP — Copilot CLI sait consommer les serveurs MCP déclarés sous
`.github/mcp/servers.json`.

### 5.3 IntelliJ / JetBrains IDEs

**Le chemin recommandé est l'intégration MCP via Copilot agent mode.** Dans
l'état actuel :

1. Installer le plugin GitHub Copilot dans IntelliJ.
2. Ouvrir la fenêtre Copilot Chat, vérifier que le mode **Agent** est
   disponible (toutes les versions ne l'ont pas — vérifier
   `Settings > Tools > GitHub Copilot`).
3. Pour la déclaration MCP, deux options :
   - **Si la version IntelliJ de Copilot lit `.github/mcp/servers.json`** :
     l'intégration est automatique à l'ouverture du repo.
   - **Sinon** : copier la configuration des serveurs depuis
     `.github/mcp/servers.json` dans les paramètres du plugin Copilot
     (`MCP servers` ou équivalent selon la version).

**Alternative à considérer** : **JetBrains AI Assistant** supporte
nativement Ollama comme provider, ce qui te permet d'utiliser Gemma comme
modèle de **premier plan** dans l'IDE plutôt que comme tool. Configuration :
`Settings > Tools > AI Assistant > Models > Add provider > Ollama`. Si ton
besoin est *« Gemma comme cerveau dans l'IDE »* plutôt que *« le harnais
comme outil dans Copilot »*, c'est probablement le chemin le plus fluide
aujourd'hui.

### 5.4 Validation de l'intégration

Quel que soit le client, pour valider :

1. Demande à l'agent : **« Liste les outils que tu vois disponibles. »**
2. Tu dois voir au moins : `read_file`, `list_dir`, `search_files`,
   `write_file`, `edit_file`, `bash`.
3. Demande : **« Lis le fichier `pyproject.toml` et dis-moi le nom du
   projet. »** — la réponse doit contenir `agent-harness`.
4. Demande : **« Essaye d'écrire un fichier dans `~/.ssh/test.txt`. »** —
   l'opération doit être refusée par la policy.

---

## 6. Profils

| Profil       | Fichier                          | Usage                                       |
|--------------|----------------------------------|---------------------------------------------|
| `dev`        | `config/profiles/dev.yaml`       | Poste de dev, mutations en `ask`            |
| `ci`         | `config/profiles/ci.yaml`        | Eval suite, déterministe, non interactif    |
| `prod-ro`    | `config/profiles/prod-ro.yaml`   | Investigation prod, **read-only**           |
| `ops`        | `config/profiles/ops.yaml`       | Investigation ops complète : Dynatrace + K8s + Runbooks + Concourse |

### Bascule de profil

```bash
harness run --profile config/profiles/ops.yaml --workspace . "..."
```

### Création d'un profil personnalisé

Partir de `dev.yaml`, modifier ce qui doit changer, garder le `name` unique
(il apparaît dans les logs et les métriques pour différencier les profils).
**Ne jamais** mettre `default: allow` dans un profil prod.

### Activation des intégrations ops (profil `ops`)

Le profil `ops.yaml` câble quatre intégrations, chacune désactivable
indépendamment via `ops_tools.<integration>.enabled`. Avant la première
utilisation :

#### 6.a Dynatrace

1. Générer un token API dans Dynatrace : *Settings > Access tokens > Generate
   new token*. Scopes minimaux : `metrics.read`, `logs.read`, `entities.read`,
   `problems.read`, et `storage:metrics:read` + `storage:logs:read` si Grail.
2. Exporter le token :
   ```bash
   export DT_API_TOKEN='dt0c01.XXXX...'
   ```
3. Éditer `config/profiles/ops.yaml` et remplacer `tenant_url` par l'URL de
   ton tenant (`https://<tenant>.live.dynatrace.com` pour SaaS classique,
   `https://<tenant>.apps.dynatrace.com` pour Grail).
4. Vérification rapide depuis la CLI :
   ```bash
   harness run --profile config/profiles/ops.yaml --workspace . \
     "Combien de problèmes Dynatrace ouverts dans la dernière heure ?"
   ```

> Si ta génération d'API n'utilise pas les chemins par défaut (`/api/v2/...`
> ou `/platform/storage/query/v1/...`), surcharge `dql_endpoint`,
> `problems_endpoint` et `entities_endpoint` dans le profil. Le code n'a
> rien d'autre à savoir.

#### 6.b Kubernetes

1. Vérifier que `kubectl` est installé et que le contexte cible existe :
   ```bash
   kubectl config get-contexts
   ```
2. Éditer `config/profiles/ops.yaml` :
   - `context: <nom-exact>` — doit correspondre à une ligne de
     `kubectl config get-contexts`
   - `allowed_namespaces: [...]` — la liste blanche que l'agent peut viser
   - `locked_namespace: <ns>` — optionnel, force un namespace unique
3. **Multi-cluster** : crée un profil par cluster (`ops-staging.yaml`,
   `ops-preprod.yaml`, `ops-prod.yaml`). Le harnais ne supporte
   intentionnellement pas le switch de contexte au runtime — c'est ce qui
   garantit qu'un agent en `staging` ne peut pas toucher `prod` même par
   accident.
4. Vérification :
   ```bash
   harness run --profile config/profiles/ops.yaml --workspace . \
     "Liste les pods en CrashLoopBackOff dans tous les namespaces autorisés"
   ```

#### 6.c Runbooks (RAG)

1. Installer la dépendance optionnelle :
   ```bash
   pip install -e ".[rag]"
   ```
   Cette installation tire `chromadb` et son embedding par défaut
   (~80 Mo de RAM au premier chargement).
2. Préparer le répertoire de runbooks :
   ```bash
   mkdir -p ~/runbooks
   # … y déposer ou y monter (git clone, mount NFS, etc.) tes runbooks .md
   ```
3. Éditer `config/profiles/ops.yaml` → `ops_tools.runbooks.path`.
4. Premier lancement : l'indexation Chroma se fait au démarrage du harnais.
   La persistence est dans `~/.local/share/agent-harness/chroma`. Les runs
   suivants ne réindexent que les fichiers nouveaux ou modifiés (idempotent
   via SHA-256 du contenu).
5. Vérification :
   ```bash
   harness run --profile config/profiles/ops.yaml --workspace . \
     "Cherche dans les runbooks comment diagnostiquer un lag DataGuard"
   ```

> Pour réindexer entièrement (par exemple après un changement majeur de la
> base), supprimer `~/.local/share/agent-harness/chroma` et relancer.

#### 6.d Concourse

1. Récupérer un bearer token. Le plus simple via `fly` :
   ```bash
   fly -t my-target login -c https://concourse.example.com -n main
   cat ~/.flyrc | yq -r '.targets["my-target"].token.value'
   ```
2. Exporter :
   ```bash
   export CONCOURSE_TOKEN='<token>'
   ```
3. Éditer `config/profiles/ops.yaml` → `ops_tools.concourse.base_url` et
   `team`.
4. Vérification :
   ```bash
   harness run --profile config/profiles/ops.yaml --workspace . \
     "Liste les pipelines Concourse et trouve le dernier build échoué"
   ```

> Le tool `concourse_build_logs` consomme des flux SSE — le format peut
> légèrement varier selon la version de Concourse. Si la sortie est
> systématiquement vide, comparer avec `fly -t ... watch <build>` pour
> vérifier que le format des événements correspond à celui parsé dans
> `_parse_sse`.

---

## 7. Exploitation quotidienne

### 7.1 Localisation des fichiers d'exécution

| Quoi                  | Où                                            |
|-----------------------|-----------------------------------------------|
| Logs applicatifs      | stdout/stderr (capturés par systemd/journald) |
| Audit log             | `~/.local/share/agent-harness/audit.jsonl`    |
| Notes long-terme      | `~/.local/share/agent-harness/notes.md`       |
| Modèle Ollama         | `~/.ollama/models/`                           |
| Workspaces de session | `/tmp/eval-*` (eval) ou défini par profil     |

### 7.2 Consultation rapide de l'audit

```bash
# Les 20 dernières décisions de permission
tail -20 ~/.local/share/agent-harness/audit.jsonl | jq -c

# Tous les refus du jour
jq -c 'select(.decision=="deny")' ~/.local/share/agent-harness/audit.jsonl

# Top 10 des tools les plus appelés
jq -r .tool ~/.local/share/agent-harness/audit.jsonl | sort | uniq -c | sort -rn | head
```

### 7.3 Logs systemd

```bash
journalctl -u agent-harness-mcp -f       # suivi temps réel
journalctl -u agent-harness-mcp --since "1 hour ago"
journalctl -u agent-harness-mcp -p err   # erreurs uniquement
```

---

## 8. Mise à jour

### 8.1 Mise à jour du harnais

```bash
cd /opt/agent-harness
git fetch origin
git log HEAD..origin/main --oneline       # voir ce qui change
git checkout <tag-version>                # toujours figer sur un tag
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/unit               # valider avant restart
sudo systemctl restart agent-harness-mcp
sudo systemctl status agent-harness-mcp
```

### 8.2 Mise à jour du modèle Gemma

```bash
# Voir la version courante
ollama show gemma:7b-instruct

# Pull la nouvelle
ollama pull gemma:7b-instruct

# Lancer l'eval suite contre la nouvelle version
harness eval --profile config/profiles/ci.yaml

# Comparer avec la baseline précédente
diff <(jq '.results' eval/report.json) <(jq '.results' eval/report.baseline.json)
```

> **Règle** : ne jamais déployer une mise à jour modèle qui régresse plus
> de 1 tâche par rapport à la baseline sans investigation.

### 8.3 Mise à jour d'Ollama

```bash
sudo systemctl stop ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl start ollama
curl -fsS http://localhost:11434/api/tags    # vérification
```

---

## 9. Sauvegarde et restauration

### 9.1 Quoi sauvegarder

- `~/.local/share/agent-harness/notes.md` — mémoire long-terme
- `~/.local/share/agent-harness/audit.jsonl` — audit (rétention légale)
- `config/profiles/*.yaml` — déjà dans git

### 9.2 Script de backup

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/agent-harness/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"
cp -a ~/.local/share/agent-harness/. "$BACKUP_DIR/"
find /var/backups/agent-harness -mindepth 1 -maxdepth 1 -mtime +30 -delete
```

À planifier en cron quotidien.

### 9.3 Restauration

```bash
sudo systemctl stop agent-harness-mcp
cp -a /var/backups/agent-harness/<date>/. ~/.local/share/agent-harness/
sudo systemctl start agent-harness-mcp
```

---

## 10. Surveillance et alertes

### 10.1 Indicateurs critiques

| Métrique                            | Seuil d'alerte                     |
|-------------------------------------|------------------------------------|
| `agent_permission_denied_total`     | > 10 / heure → suspect             |
| `agent_max_steps_reached_total`     | > 5 / heure → boucles non convergées |
| `agent_tool_errors_total{tool=bash}`| taux d'erreur > 30%                |
| Latence p95 modèle                  | > 30s sur gemma:7b                 |
| Disponibilité Ollama (`/api/tags`)  | down > 1 min                       |
| RAM Ollama                          | > 90% du `OLLAMA_MAX_LOADED`       |

### 10.2 Intégration Dynatrace

Le harnais émet du tracing OTLP. Pour l'ingérer :

```yaml
# Dans le profil
observability:
  enabled: true
  service_name: agent-harness-prod
  otlp_endpoint: http://localhost:4317   # OneAgent local
```

Côté Dynatrace, créer une **Application** ou un **Service** filtré sur
`service.name=agent-harness-*` et construire un dashboard avec :

- Sessions par heure (compteur de spans `agent.session`)
- Distribution durée session (histogramme)
- Top tools (group by `tool.name` sur les spans `tool.*`)
- Taux de refus permission
- Conso tokens cumulée

Exemple DQL pour le top des refus de permission sur 24h :

```
fetch logs
| filter app == "agent-harness"
| filter contains(content, "permission") and contains(content, "deny")
| parse content, "JSON:json"
| summarize count = count(), by: {json[tool]}
| sort count desc
```

### 10.3 Alertes recommandées

```yaml
# Pseudo-config Alertmanager / Dynatrace équivalent
- alert: AgentHarnessHighDenyRate
  expr: rate(agent_permission_denied_total[5m]) > 0.1
  for: 10m
  severity: warning
  summary: "Agent harness: taux de refus permission anormal — possible prompt injection"

- alert: AgentHarnessLoopExhausted
  expr: rate(agent_max_steps_reached_total[15m]) > 0
  for: 15m
  severity: warning
  summary: "Agent harness: sessions atteignant max_steps sans converger"
```

---

## 11. Dépannage

### Symptôme : `harness: command not found`

- Vérifier : `which harness`
- Cause probable : venv pas activé. `source .venv/bin/activate`
- Si installé en système : vérifier que `~/.local/bin` ou le bin du venv
  est dans `PATH`.

### Symptôme : `connection refused` sur localhost:11434

- Cause : Ollama n'est pas démarré.
- Fix : `systemctl start ollama` ou `ollama serve &`
- Vérifier : `curl http://localhost:11434/api/tags`

### Symptôme : `model 'gemma:7b-instruct' not found`

- Le modèle n'a pas été pull.
- Fix : `ollama pull gemma:7b-instruct`
- Vérifier : `ollama list`

### Symptôme : `bwrap: setting up uid map: Permission denied`

- Cause : sur certains noyaux/distros, les user namespaces non privilégiés
  sont désactivés.
- Fix temporaire : basculer le profil sur `sandbox.backend: subprocess`
  (uniquement en dev local).
- Fix correct :
  ```bash
  echo 'kernel.unprivileged_userns_clone=1' | sudo tee /etc/sysctl.d/00-userns.conf
  sudo sysctl --system
  ```

### Symptôme : l'agent boucle et atteint `max_steps`

- Examiner les traces OTel : où se passe la boucle ?
- Causes fréquentes :
  1. Tool qui retourne systématiquement une erreur (le modèle reessaie sans
     comprendre).
  2. Description de tool ambiguë (le modèle ne sait pas quoi faire du
     résultat).
  3. Modèle trop petit pour la complexité de la tâche → essayer une
     variante plus grosse.
- Détection automatique : le `repetition_threshold` (par défaut 3) injecte
  un message d'arrêt — vérifier qu'il est bien actif.

### Symptôme : les tool calls sont mal parsés (JSON cassé)

- Cause : Gemma produit du tool calling moins fiable que les gros modèles.
- Le module `model.py` a deux chemins de parsing (natif Ollama puis fallback
  texte `<tool_call>...</tool_call>`).
- Si les deux échouent, augmenter la verbosité dans
  `model.py:_parse_text_tool_calls` et capturer un échantillon pour
  ajuster le parser.
- Workaround : baisser la `temperature` à 0 pour plus de déterminisme.

### Symptôme : permission refusée sur un tool censé être autorisé

- Vérifier l'audit log : `tail -1 ~/.local/share/agent-harness/audit.jsonl`
- Le champ `decision` indique la décision et `args` les arguments.
- Vérifier que la regex `patterns_deny` du profil ne matche pas par
  inadvertance les arguments.
- Tester la regex isolément :
  ```python
  import re; re.search(r"...pattern...", '{"path": "..."}')
  ```

### Symptôme : Copilot dans IntelliJ ne voit pas le serveur MCP

- Vérifier que la version du plugin Copilot supporte l'agent mode + MCP
  (il faut une version récente, vérifier le changelog).
- Vérifier que `harness mcp-serve` fonctionne en standalone :
  ```bash
  harness mcp-serve --profile config/profiles/dev.yaml --workspace . </dev/null
  ```
  (doit afficher une initialisation MCP, puis se terminer sur EOF)
- Si KO sur IntelliJ même quand standalone OK : essayer l'inspecteur MCP
  pour confirmer que le problème est côté IntelliJ. Considérer
  l'alternative JetBrains AI Assistant + Ollama.

---

## 12. Procédures d'incident

### 12.1 « L'agent a fait quelque chose qu'il ne devait pas »

1. **Couper** : `sudo systemctl stop agent-harness-mcp`
2. **Préserver les preuves** :
   ```bash
   sudo cp -a ~/.local/share/agent-harness/audit.jsonl /var/incident/audit-$(date +%s).jsonl
   sudo journalctl -u agent-harness-mcp --since "2 hours ago" > /var/incident/journal-$(date +%s).log
   ```
3. **Identifier la session** : retrouver le `session_id` dans l'audit log,
   filtrer toutes les entrées correspondantes.
4. **Reproduire** : si possible, rejouer la session en mode dev avec un
   workspace propre et la même requête utilisateur.
5. **Corriger la policy** : ajouter le pattern incriminé dans `patterns_deny`
   du profil concerné. Tester avec `pytest tests/unit/test_permissions.py`.
6. **Postmortem** : documenter — quel modèle, quel profil, quelle requête,
   quelle action, quel impact, quelle correction.

### 12.2 « Ollama consomme tout le RAM »

1. `ollama ps` pour voir les modèles chargés.
2. `ollama stop <model>` pour décharger.
3. Configurer `OLLAMA_MAX_LOADED_MODELS=1` dans l'environnement Ollama.
4. Si récurrent, passer à un modèle plus petit (gemma:2b) ou augmenter le
   RAM de la machine.

### 12.3 « Une mise à jour modèle a tout cassé »

1. `ollama list` — identifier la version courante.
2. Re-pull la version précédente si disponible :
   ```bash
   ollama pull gemma:7b-instruct@<digest-précédent>
   ```
3. Sinon, basculer temporairement sur un autre modèle compatible
   (`qwen2.5:7b-instruct`, `llama3.1:8b-instruct`) — le harnais est
   indépendant du modèle, seul `model.name` dans le profil change.
4. Lancer l'eval suite pour valider.

### 12.4 « Le serveur MCP refuse les connexions »

1. Vérifier le process : `systemctl status agent-harness-mcp`
2. Vérifier les logs : `journalctl -u agent-harness-mcp -n 100`
3. Causes fréquentes :
   - Profil YAML mal formé → `python -c "import yaml; yaml.safe_load(open('config/profiles/dev.yaml'))"`
   - Workspace pointe vers un répertoire inexistant
   - Permissions sur l'audit log path → vérifier les droits

---

## 13. Désinstallation

```bash
# 1. Arrêter et désactiver le service
sudo systemctl stop agent-harness-mcp
sudo systemctl disable agent-harness-mcp
sudo rm /etc/systemd/system/agent-harness-mcp.service
sudo systemctl daemon-reload

# 2. Backup des données utilisateur (recommandé avant suppression)
tar czf ~/agent-harness-backup-$(date +%Y%m%d).tar.gz ~/.local/share/agent-harness

# 3. Supprimer le code et le venv
rm -rf /opt/agent-harness

# 4. Supprimer les données utilisateur (irréversible)
rm -rf ~/.local/share/agent-harness

# 5. (Optionnel) Désinstaller Ollama
sudo systemctl stop ollama
sudo rm /usr/local/bin/ollama
sudo rm -rf ~/.ollama
```

---

*Document de référence opérationnelle. À mettre à jour à chaque évolution
de la procédure d'installation, du modèle de permissions, ou de la
surveillance. Ne contient volontairement aucun élément de design — pour ça,
voir `docs/kb/agent-harness-kb.md`.*
