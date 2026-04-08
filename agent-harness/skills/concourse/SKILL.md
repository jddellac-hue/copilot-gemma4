# Skill — Concourse CI

## Architecture locale (pseudo)

### Infrastructure (concourse-infra)

Tout dans Kind K8s 1.31.6 sauf le worker Concourse :

| Service | Namespace | Port/NodePort | Notes |
|---------|-----------|---------------|-------|
| Concourse 7.14.3 web | concourse | ingress concourse.localhost:8088 | Chart Helm officiel |
| Concourse worker (containerd) | Docker host | TSA via NodePort 30222 | Hors Kind (sysfs mount impossible), `--cgroupns=host` |
| Gitea 1.23 rootless | concourse | NodePort 30300 | Remplace GitLab CE (30x plus léger) |
| registry:2 | concourse | NodePort 30500 | HTTP, pas d'auth |
| SonarQube 25.6 | concourse | NodePort 30900 | |
| S3Mock | concourse | NodePort 30090 | 3 buckets |
| Kafka 3.8.1 KRaft | dd281-dev | NodePort 30092 | |
| Redis 7.2 | dd281-dev | ClusterIP | |
| bouchon-peam | dd281-dev | ClusterIP | |

Accès browser via ingress : `*.localhost:8088`
Accès CI (worker) via NodePorts : `172.19.0.2:<port>`

### Pipelines (concourse-pipelines)

3 pipelines portables (seront portés en entreprise via reverse) :

| Pipeline | Jobs | Flow |
|----------|------|------|
| Quarkus | 13 | build → image → E2E → tag-rc → TIS (Behave) → VA (Behave) → changement (SNOW) → PROD (+tag-v) → VACPP → PRI + rollback |
| Angular | 12 | build → image → E2E (full stack) → tag-rc → TIS (Behave) → VA (Behave) → PROD (+tag-v) → VACPP → PRI + rollback |
| Oracle | 10 | build-image → E2E (full stack) → tag-rc → flyway-tis → flyway-va → dryrun-prod → changement → flyway-prod (+tag-v) |

Ressources fil conducteur :
- `version-rc` (tag_filter: RC-*) : TIS → VA → changement → PROD
- `version-v` (tag_filter: V-*) : VACPP → PRI
- `tag-v` intégré dans deploy-prod / flyway-prod (pas un job séparé)

Helm values alignés infra-as-code entreprise :
- 26 secrets Conjur par env (pattern `supervision/dd281/{env}.{key}`)
- 2 S3 : `s3_client` (acquittement) + `s3_bucket` (ret_ae/bs/request_xml)
- Probes, resources, labels identiques à l'entreprise

### Leçons apprises

**Worker** :
- Worker Concourse ne peut PAS tourner dans Kind (sysfs mount impossible en triple nesting host→Kind→containerd)
- Worker en runtime containerd (`CONCOURSE_RUNTIME=containerd`), pas Garden
- `--cgroupns=host` obligatoire sur le container worker (fix buildkitd cgroupsv2)
- `--network kind` pour que le worker joigne le cluster Kind
- DNS containerd : `CONCOURSE_CONTAINERD_DNS_PROXY_ENABLE=true` (env var, pas CLI arg)
- Worker se connecte au TSA via NodePort 30222 (service `concourse-web-tsa` type NodePort)

**Clés SSH** :
- Générées localement par `mise keygen` (ssh-keygen -m PEM), pas dans un pod K8s (ImagePullBackOff) ni via le chart Helm
- Format PEM (PKCS#1) obligatoire (`ssh-keygen -m PEM`), pas OpenSSH moderne — Concourse refuse le format OpenSSH avec `asn1: structure error`
- Stockées dans le Secret K8s `concourse-keys` (namespace concourse)

**Kind / K8s** :
- Gitea 1.23 rootless démarre en 30s vs 5 min pour GitLab CE
- Ingress-nginx doit être installé séparément (`mise ingress-setup`) — pas inclus par défaut dans Kind
- NodePorts obligatoires pour TOUS les services accédés depuis le worker ou le host (Gitea 30300, Registry 30500, SonarQube 30900, S3 30090, Kafka 30092, Artifactory 30081, TSA 30222)
- Le kubeconfig Kind change à chaque recréation du cluster → `mise kubeconfig-update` avec `kind get kubeconfig --internal` (server = `concourse-ci-control-plane:6443`)
- Bouchon-peam (2.1 GB) chargé dans Kind containerd via `kind load docker-image` (imagePullPolicy: Never)
- User Gitea admin créé via CLI dans le pod (`gitea admin user create`), pas via signup

**Mise / TOML** :
- Mise utilise sh (pas bash) : pas de pipefail, pas d'arrays bash, pas de `[[ ]]`
- Tera (template engine mise) interprète `{{}}` → ne JAMAIS utiliser `docker --format '{{.Names}}'` ou `{{}}` dans les commentaires. Utiliser `docker -q --filter` ou `-f json | python3`
- TOML `"""` interprète `\n` (newline), `\"` (quote) → casse les `python3 -c "..."` avec des quotes internes. Utiliser `python3 << 'HEREDOC'` ou `python3 -c '...'` (single quotes)
- Les background processes (`nohup ... &`, `pkill`) provoquent des exit codes signaux (144) dans mise → externaliser en scripts bash (`scripts/nuke.sh`, `scripts/stop.sh`, etc.)
- Toujours `|| true` après `mise run registry-portforward` dans stack/start (exit 144 inévitable)

---

Deux dépôts contenant du code Concourse sur la plateforme :

---

## Repo 1 : repo-concourse (ex-jade)

**Repo** : `repo-concourse`
**Path local** : `<repo-concourse>/`
**Concourse** : `https://dub.concourse.craftspace.app.cloud.intra` — team `<equipe>`
**Fly target** : `<equipe>`

---

## Structure du repo repo-concourse

```
repo-concourse/
├── ci/
│   ├── <code>-pipeline-main.yaml   ← pipeline PROPRE à <code> (un seul composant)
│   ├── quarkus-pipeline.yml       ← pipeline GÉNÉRIQUE (instancié par composant)
│   └── oracle-pipeline.yml        ← pipeline Oracle
├── pipeline-vars/
│   └── <app>.yml  ← vars du pipeline <code> (pour quarkus-pipeline.yml)
├── tasks/
│   ├── build/
│   │   ├── build-analyze-quarkus-jdk17.yml  ← build Maven + TU + sonar
│   │   ├── prepare-build-docker-jdk21.yml   ← prépare le JAR pour docker build
│   │   ├── conventional-commits.yaml        ← calcul semver + génération changelog
│   │   ├── dependency-check.yml             ← OWASP dependency check
│   │   ├── execute-sonar-jdk17.yml          ← analyse SonarQube
│   │   ├── allure-report.yml                ← rapport de tests Allure
│   │   ├── changelog-tag-git.yaml           ← tag Git après build
│   │   └── report-to-s3.yml                 ← sauvegarde rapports sur S3
│   ├── db/flyway/
│   │   ├── flyway.yml                       ← migration Flyway (Flyway 5.1.4)
│   │   └── flyway-dryrun.yaml               ← dry-run migration
│   ├── git/
│   │   └── fetch-tag.yml                    ← checkout d'un tag Git spécifique
│   ├── iams/
│   │   └── ajoute-tests-realises-et-perimetre-livre.yaml ← payload ServiceNow
│   └── test/
│       ├── tests-popete.yaml                ← tests de recette (Popete/Karate)
│       └── sauvegarde-rapport-sur-s3.yaml   ← upload rapport sur S3
├── infra-as-code/
│   ├── overlays/
│   │   ├── DEPLOYMENT/Z4-{env}/
│   │   │   ├── <code>-values.yaml    ← values Helm + configs applicatives par env
│   │   │   ├── <code>-version.yaml   ← version image + version Flyway par env
│   │   │   ├── namespace.yaml       ← namespace K8s
│   │   │   └── namespace-vf.yaml    ← namespace VF (second namespace)
│   │   └── TI/<code>/
│   │       ├── values.yaml          ← values Helm pour l'env TI (CI)
│   │       └── namespace.yaml
│   └── bouchons/                    ← déploiement de bouchons par env
├── init-quarkus-pipeline.sh         ← script fly set-pipeline (instancié)
├── <code>-init-main.sh               ← script fly set-pipeline (<code> main)
├── destroy-pipeline.sh              ← suppression pipeline
├── pause-job.sh / unpause-job.sh    ← pause/unpause d'un job
└── pause-complicite.sh / unpause-complicite.sh  ← pause/unpause ressource ServiceNow
```

---

## Deux pipelines pour <code>

### `<code>-pipeline-main.yaml` — Pipeline dédié <code>

Pipeline **propre à <code>**, non générique. Workflow complet de CI/CD :

```
build-docker → deploy-and-run-ti → publish-image-and-tag-repo
                                          ↓
                          deploy-env-dev / deploy-env-va / deploy-env-agate
                                          ↓
                                   deploy-env-prod
```

**Groups** :
- `build` : build-docker, deploy-and-run-ti, publish-image-and-tag-repo
- `deployment` : deploy-env-dev, deploy-env-va, deploy-env-agate
- `ci` : install-pipeline
- `prod` : deploy-env-prod

**Déclencheur** : webhook GitLab (`check_every: never` + `webhook_token: token-du-webhook`)

### `quarkus-pipeline.yml` — Pipeline générique instancié

Pipeline **template** utilisable pour tous les composants Quarkus du périmètre.
Instancié via `--instance-var quarkus=<nom-composant>`.

```
release → image → tis → va → complicite → prod → pms
```

**Groups** :
- `pipeline` : tous les jobs

---

## Syntaxe Concourse — rappels clés

### Variables et credentials

```yaml
# Variable simple (définie en pipeline-var, env var, ou dummy var_sources)
((variable))

# Credential Vault/Conjur (notation double-guillemet)
(("vault-path.clé"))

# Variable chargée dynamiquement dans un step
((.:variable-chargée))  # dot prefix = variable locale au build plan
```

**Exemples du projet** :
```yaml
# Credentials Conjur
(("docker_galanterie.registre"))       # registre Docker interne
(("gitlab.cle_privee"))                # clé SSH GitLab
(("<code>/dev.kafka_url"))              # URL Kafka pour l'env dev
(("kubernetes_z4-dev.value"))          # kubeconfig Z4-dev
(("snow_prod.url"))                    # URL ServiceNow prod

# Variables de pipeline
((quarkus))                            # nom du composant (instance var)
((git-app-uri))                        # URI du repo GitLab de l'app
```

### `var_sources` — variables statiques

```yaml
var_sources:
  - name: global-vars
    type: dummy
    config:
      vars:
        chart-helm:
          virtual_repo_name: helm-dev-virtual
          name: sld-ng
          version: 2.58.0
```

Référencées via `((global-vars:chart-helm.version))`.

### `load_var` — chargement dynamique

```yaml
- load_var: version
  file: versionning/number        # lit le fichier et charge dans la variable
  reveal: true                    # affiche la valeur dans les logs

- load_var: conf-namespace
  format: yml                     # parse YAML → accès aux champs
  file: repo-<equipe>-ci/infra-as-code/overlays/DEPLOYMENT/Z4-dev/namespace.yaml

# Utilisation
namespace: ((.:conf-namespace.metadata.name))
```

### `in_parallel` — parallélisation

```yaml
- in_parallel:
    - get: source-code
      trigger: true
    - get: pipeline-code
    - task: values-override
      file: ...
      params: { ... }
```

### `serial_groups` — mutex entre jobs

```yaml
- name: build-docker
  serial_groups: [ build ]   # partage le verrou "build" avec d'autres jobs

- name: deploy-and-run-ti
  serial_groups: [ build ]   # ne peut pas tourner en même temps que build-docker
```

### Hooks

```yaml
on_success:
  task: alerting-teams-deploiement
  file: tasks-all-in-one/secret/teams/teams-deploiement.yaml
  params:
    STATUT: OK

on_failure:
  task: alerting-teams-deploiement
  params:
    STATUT: KO

ensure:
  try:                       # try = ne pas faire échouer le job si le hook échoue
    task: save-report-ti
    file: ...
```

---

## Ressources principales

### Git

```yaml
- name: repo-<code>-quarkus
  type: git
  source:
    uri: ssh://git@git-scm.soie-charme.intra:2222/<equipe>/<app>-sldng-quarkus.git
    private_key: (("gitlab.cle_privee"))
    branch: master
    ignore_paths: [infra-as-code, README.md]  # trigger seulement sur le code source
  check_every: never
  webhook_token: token-du-webhook

- name: versionning
  type: concourse-git-semver-tag  # resource type custom — tag semver sur git
  source:
    <<: *uri_git
```

### Docker Image

```yaml
- name: image-docker
  type: docker-image
  source:
    repository: (("docker_galanterie.registre"))/<equipe>/<app>
    insecure_registries: [(("docker_galanterie.registre"))]
    username: (("docker_galanterie.fascination"))
    password: (("docker_galanterie.mot_de_passe"))
    registry_mirror: http://(("docker_galanterie.registre"))
```

### Kubernetes

```yaml
- name: cluster-kubernetes-dev
  type: kubernetes-resource
  source:
    kubeconfig: (("kubernetes_z4-dev.value"))
    context: z4-dev
```

### Helm

```yaml
- name: helm-deployment
  type: helm-resource-deploiement
  source:
    stable_repo: "false"
    repos:
      - name: helm-dev-virtual
        url: (("helm_galanterie.repo"))
```

### ServiceNow (complicite)

```yaml
- name: complicite-snow
  type: concourse-snow-resource
  source:
    SNOW_URL: (("snow_prod.url"))
    SNOW_USER: (("snow_prod.fascination"))
    SNOW_PASSWORD: (("snow_prod.mot_de_passe"))
    S3_ENDPOINT_URL: (("s3_sauvegarde-concourse-m.endpoint"))
    FOLDER_PATH: <equipe>/complicite-iams/((quarkus))/reference-complicite
    WORKFLOW: default_s3
  check_every: ((snow_check_interval))
```

---

## Workflow <code> — détail des jobs

### `build-docker`

1. `get versionning` avec `bump: patch` (pré-incrément semver)
2. `load_var: version` depuis `versionning/number`
3. `task: package-composant` → `mvn package` dans une image Maven JDK17
4. `task: run-dependency-check-maven` → OWASP check
5. `task: run-tu-and-check-sonar` → TU + sonar
6. `put: image-docker` → build Dockerfile + push avec tag `short_ref` (SHA court)
7. `on_failure` → alerte Teams

### `deploy-and-run-ti`

1. Récupère l'image buildée (passée via `build-docker`)
2. `task: values-override` → substitution variables Helm (Conjur → values.yaml)
3. `task: specify-target-cluster` → sélectionne le kubeconfig selon `blocPos`
4. `try: delete-namespace` → supprime le namespace TI existant
5. `try: create-namespace` → recrée le namespace
6. `put: deploy-component` via Helm (chart `sld-ng`)
7. `task: run-ti` → exécute les tests d'intégration
8. `ensure: try: save-report-ti` → sauvegarde rapport sur S3 (même si TI KO)
9. `on_failure` → alerte Teams

### `publish-image-and-tag-repo`

1. Retag de l'image Docker (SHA → semver)
2. `put: tag-repo` → tag Git semver sur le repo source
3. `try: delete-tmp-image` → supprime l'image temporaire (tag SHA) via API Artifactory

### `deploy-env-dev` / `deploy-env-va` / `deploy-env-agate` / `deploy-env-prod`

Pattern commun pour chaque env :
1. Charge la version depuis `<code>-version.yaml` (fichier dans jade, versionné séparément du code)
2. `task: values-override` → substitution variables Conjur dans values.yaml Helm
3. `task: specify-target-cluster` → résolution du cluster K8s via `blocPos`
4. `task: flyway_migrate` → migration BDD (en parallèle avec le cluster lookup)
5. `try: create-namespace`
6. `put: deploy-component` via Helm (`atomic: true`)
7. `on_success/on_failure` → alerte Teams

**Différence PROD** : la version est lue depuis `<code>-version.yaml` (champ `mep`), pas depuis `versionning` — deploy manuel après complicite.

### `complicite` (quarkus-pipeline uniquement)

Crée une demande de mise en production dans ServiceNow :
1. `load_var: iams` depuis `iams.yml` du repo source
2. `task: ajoute-périmètre-livré-dans-payload-iams` → construit le payload JSON
3. `put: création-complicite` → POST vers ServiceNow
4. Le job `prod` attend le déclenchement par la ressource `complicite-snow` (check_every)

---

## Tasks réutilisables — détail

### `build-analyze-quarkus-jdk17.yml`

```bash
cd source-code
mvn -f pom.xml -P !ti -Pjacoco -Drevision=${revision} verify
cp -r impl/target/surefire-reports/* ../out-surefire
```

- Image : `maven/pe-maven-3.8.6-jdk-17-owasp`
- Cache Maven : symlink `~/.m2/repository → ./maven` (volume Concourse)
- Profil `-P !ti` : exclut les tests d'intégration
- Profil `-Pjacoco` : active la couverture Jacoco
- Output : `out-surefire` (rapports XML surefire)

### `prepare-build-docker-jdk21.yml`

Prépare le dossier pour le build Docker avec JDK 21 (quand le build s'est fait en JDK 17) :
- Copie le JAR depuis `out-jar/` vers `source-build/target/`
- Copie le `Dockerfile`

### `conventional-commits.yaml`

Calcul semver automatique basé sur les messages de commit (Conventional Commits) :

| Préfixe commit | Incrément |
|----------------|-----------|
| `BREAKING CHANGE` ou `!:` | major |
| `feat:`, `style:` | minor |
| `fix:`, `build:`, `perf:`, `refactor:`, `revert:` | patch |
| Autres | none (`x.y.z-sha`) |

Génère :
- `tags/tag` — nouvelle version semver
- `changelog/CHANGELOG.md` — changelog structuré

### `flyway.yml`

- Image : `boxfuse/flyway:5.1.4-alpine`
- Commandes : `'info; -X migrate; info'` (info avant/après, migrate en mode debug)
- Sécurité : `FLYWAY_CLEAN_DISABLED=true` forcé sur les URL `*.eclat.*` (prod)
- Substitution SQL : `%%oracle_schema%%` → `$FLYWAY_USER`

### `tests-popete.yaml`

Tests de recette fonctionnelle (Popete = outil de test REST maison/Karate).
Params : `CADRE` (environment), `TAGS` (filtres de tags de tests).

---

## Helm Chart `sld-ng` — values.yaml

Structure des `<code>-values.yaml` par env :

```yaml
createServicesCommuns: false
exclureAnnuaireAaeCommun: true    # bouchonne l'annuaire LDAP
monitoring: "none"
composant: "<code>"
equipe: "<equipe>"
blocPos: "stra"                    # sélection du cluster K8s
trustedCertificat: true           # charge les AC Pôle Charme

image:
  repository: "<equipe>/<app>"

contextRoot: "<app>"  # readiness probe path

resources:
  limits:   { cpu: "2500m", memory: "4096Mi" }
  requests: { cpu: "1000m", memory: "2048Mi" }

configs:                           # → ConfigMap K8s → env vars du pod Quarkus
  QUARKUS_DATASOURCE_USERNAME: ${QUARKUS_DATASOURCE_USERNAME}  # injecté par values-override
  QUARKUS_KAFKA_BROKER_URL: ${QUARKUS_KAFKA_BROKER_URL}
  ...

ingress:
  hosts:
    - host: <code>-dev.z4-dev.k8s.soie-charme.intra
```

**`blocPos: "stra"`** → utilisé par `get-kubeconfig/task.yaml` pour résoudre le bon kubeconfig.

---

## Version management

### `<code>-version.yaml` (par env, dans jade/infra-as-code)

```yaml
flyway:
  version_1: "9"    # version Flyway bundle (bundle = jeu de migrations)
mep:
  "1.2.3"           # version image pour déploiement PROD (mis à jour manuellement)
```

La version image est :
- En CI : lue depuis `versionning/number` (auto-incrémentée par conventional-commits)
- En PROD : lue depuis `<code>-version.yaml` (champ `mep`, mis à jour par l'équipe)

---

## Fly CLI — commandes courantes

```bash
# Login
fly -t <equipe> login -c https://dub.concourse.craftspace.app.cloud.intra --team-name <equipe>

# Installer le pipeline <code> (pipeline propre)
./<code>-init-main.sh

# Installer un pipeline générique Quarkus instancié
./init-quarkus-pipeline.sh <app>

# Exposer un pipeline (le rendre public)
fly -t <equipe> expose-pipeline -p "support-data-solution"/quarkus:<app>

# Lister les pipelines
fly -t <equipe> pipelines

# Déclencher un job manuellement
fly -t <equipe> trigger-job -j <app>-master/build-docker

# Consulter les builds
fly -t <equipe> builds -j <app>-master/build-docker

# Suivre un build en temps réel
fly -t <equipe> watch -j <app>-master/deploy-and-run-ti

# Pauser/dépauser un job
./pause-job.sh <job-name>
./unpause-job.sh <job-name>

# Pauser la vérification ServiceNow
./pause-complicite.sh
./unpause-complicite.sh

# Détruire un pipeline
./destroy-pipeline.sh
```

---

## Alerting Teams

Toutes les failures → webhook Microsoft Teams :
```
https://galanterie.webhook.office.com/webhookb2/...
```

Hook pattern sur chaque job :
```yaml
on_failure:
  task: alerting-teams-build-ko
  file: tasks-all-in-one/secret/teams/teams-build-ko.yaml
  params:
    WEBHOOK_TEAMS: ((global-vars:webhook-teams))
    NOM_COMPOSANT: OI277
    LIEN_JOB: ((global-vars:pipeline))build-docker
```

---

## Resource types custom utilisés

| Type | Image | Rôle |
|------|-------|------|
| `kubernetes-resource` | `incubateur/concourse-kubernetes-resource:1.23.7-1.0.6` | kubectl apply |
| `metadata` | `olhtbr/metadata-resource:2.0.1` | métadonnées build (date, SHA, …) |
| `helm-resource-deploiement` | `typositoire/concourse-helm3-resource:v1.36.0` | helm upgrade/install |
| `concourse-snow-resource` | `rose-docker/concourse-snow-resource:3.1.8` | ServiceNow ITSM |
| `concourse-git-semver-tag` | `laurentverbruggen/concourse-git-semver-tag-resource` | tag semver sur git |

---

## Points d'attention

- `check_every: never` sur toutes les ressources git → **déclenchement exclusivement par webhook GitLab**. Si le webhook est cassé, rien ne se déclenche automatiquement.
- `atomic: true` sur Helm en DEV/VA/AGATE/PROD → rollback automatique si le deploy échoue (readiness probe).
- `atomic: false` sur Helm en TI → le pod reste même si KO (pour inspecter les logs).
- `try:` sur `delete-namespace` et `create-namespace` → ne fait pas échouer le pipeline si le namespace n'existe pas encore.
- Images docker internes toutes sur `(("docker_galanterie.registre"))` — pas de Docker Hub.
- Tous les secrets passent par Conjur (`(("path.clé"))`) — jamais en clair dans les fichiers versionnés.

---

## Repo 2 : cg926-onyx (Concourse plus riche)

**Repo** : `cg926-onyx`
**Path local** : `/home/jd/pseudo/cg926-onyx/`
**Contexte** : Pipelines CI/CD pour un projet plus large (plusieurs microservices Spring + Quarkus + WebLogic)

Plus riche que repo-concourse : gère plusieurs types de technos (Spring, Quarkus, CF, K8s), plusieurs environnements, et inclut des tests de benchmark.

### Types de pipelines

| Pipeline | Fichier | Description |
|----------|---------|-------------|
| Quarkus K8s | `pipeline/quarkus-pipeline.yml` | ~995 lignes — instancié par composant Quarkus |
| Spring CF | `pipeline/spring-pipeline.yml` | ~754 lignes — Cloud Foundry rolling deployment |
| Config CF | `pipeline/config-pipeline.yml` | ~474 lignes — création des services CF (RabbitMQ, Config Server, Conjur) |
| Monolithe | (dans tasks) | Build EAR WebLogic |

### Environments

| Env | Cluster/Plateforme | Rôle |
|-----|-------------------|------|
| TIS | K8s (local cluster) | Dev / CI continu |
| VA | K8s | Recette |
| VABP | K8s (backup) | Recette backup |
| BENCH | K8s | Tests de performance |
| CAMEE | K8s | Preprod-like |
| PROD | K8s | Production |
| PRODBP | K8s | Production backup |
| PMS | K8s | Pré-mise-en-service |

### Jobs pipeline Quarkus (cg926-onyx)

```
release → image → tis → va → vabp → bench → sensualite → prod → prodbp → camee → pms
```

- **release** : conventional-commits (semver), SonarQube, OWASP Dependency Check
- **image** : build Docker + push registry
- **tis/va/...** : Helm deploy sur K8s
- **sensualite** : ServiceNow change management (approbation avant PROD)

### Tasks référencées dans pipeline (via `git-galanterie-onyx`)

```yaml
# Référence external task depuis un repo git (pattern classique)
task: build
file: git-galanterie-onyx/tasks/build/build-analyze-quarkus-jdk17.yml
```

Le repo `git-galanterie-onyx` est le repo de tasks partagées (équivalent de `tasks-all-in-one`).

### Multi-composant — Helm values multi-images

```yaml
# tasks/tic/valorise_images.yaml — mise à jour simultanée de 9 images
yq -i '.images.dd017_base.tag = env(TAG)' values.yaml
yq -i '.images.dd017_velours.tag = env(TAG)' values.yaml
# ... 9 composants valorisés simultanément
```

### Spring pipeline — Cloud Foundry specifics

```yaml
# Stratégie rolling sur CF
cf push --strategy rolling
# Health checks via route
cf check-route app.domain.intra
# Dynatrace APM intégré
DYNATRACE_TENANT: ((dynatrace.tenant))
```

### Config pipeline — création des services CF

```yaml
# Création services CF (RabbitMQ, Config Server, Conjur, Dynatrace)
cf create-service p.rabbitmq on-demand-plan rabbitmq-service
cf create-service cyberark-conjur community conjur-service
cf create-service p-config-server standard config-server -c '{"git": ...}'
```

---

## Repo tasks-all-in-one

**Repo** : `tasks-all-in-one`
**Path local** : `/home/jd/pseudo/tasks-all-in-one/`
**Remote GitLab** : `git-scm.emoi-baiser.intra` (branche `master`)
**Remote GitHub** : `https://github.com/jddellac-hue/tasks-all-in-one.git`
**Intégration** : `fly set-pipeline -l pipeline-vars/... -l tasks-all-in-one/...`
**Usage** : Référencé dans `repo-concourse`, `cg926-soie`, `<code>-*`

### Structure du repo

```
tasks-all-in-one/
├── README.md
└── custom/
    ├── build-projet-angular.yaml
    ├── dependency-check-angular.yaml
    ├── deploy.yaml
    ├── execute-angular-sonar.yaml
    ├── execute-angular-ti.yaml
    ├── execute-angular-tu.yaml
    ├── execute-dependency-check-back.yaml
    ├── execute-enf-tester.yaml
    ├── execute-ti.yaml
    ├── execute-tu.yaml
    ├── flyway-reset.yaml
    ├── flyway-scripts-execute.yaml
    ├── init-mock-server.yaml
    ├── sauvegarde-rapports-sur-s3.yaml
    ├── upload-capi.yaml
    ├── docker/
    │   ├── build-image.yaml           # Build OCI (image.tar)
    │   └── construit-image.yaml       # Build Docker classique
    ├── maven/
    │   └── package-composant.yaml
    └── teams/
        ├── teams-build-ko.yaml
        ├── teams-deploiement.yaml
        ├── teams-deploiement-gw.yaml
        ├── teams-pipeline-ko.yaml
        ├── teams-publish-image-ko.yaml
        └── teams-test-ko.yaml
```

---

### Angular / Frontend

#### `build-projet-angular.yaml`
- **Image** : `node:20.9.0-alpine3.18`
- **Inputs** : `source`, `version`, `coverage` — **Outputs** : `source` — **Cache** : `/root/.npm`
- **Commandes** :
  ```bash
  npm config set registry http://artefact-repo.*.intra/artifactory/api/npm/npm-public
  npm install --legacy-peer-deps
  npm version ${versionapp} --no-git-tag-version --allow-same-version
  ```

#### `execute-angular-tu.yaml`
- **Image** : `node:20.9.0-alpine3.18`
- **Inputs** : `source`, `version` — **Outputs** : `coverage` — **Cache** : `/root/.npm`
- **Commandes** : `npm run test:ci`

#### `execute-angular-ti.yaml`
- **Image** : `cypress/included:12.17.4`
- **Inputs** : `source` — **Outputs** : `rapports` — **Cache** : `/root/.npm`
- **Commandes** :
  ```bash
  npm run cypress:run:ti
  node cucumber-html-report.js
  ```

#### `dependency-check-angular.yaml`
- **Image** : `owasp/dependency-check-action:latest`
- **Params** : `nom_composant`
- **Commandes** :
  ```bash
  dependency-check.sh --project "$nom_composant" --scan source -n \
    --format ALL --out source/owasp \
    --disableOssIndex --disableNodeAudit --noupdate
  ```

#### `execute-angular-sonar.yaml`
- **Image** : `sonarsource/sonar-scanner-cli:latest`
- **Rôle** : Scan SonarQube (lit `sonar-project.properties`, remplace `%%version%%`)

---

### Java / Backend

#### `execute-tu.yaml`
- **Image** : `odt/maven-java-node:3.8.6-17-18.14.2-R1`
- **Params** : `PROJECT_KEY`, `PROJECT_NAME`, `VERSION`, `ROOT_IMPL`
- **Cache** : `maven`
- **Commandes** :
  ```bash
  M2_LOCAL_REPO="${HOME}/.m2/repository"
  M2_CACHE="$(pwd)/maven"
  rm -rf ${M2_LOCAL_REPO}
  ln -s "${M2_CACHE}" "${M2_LOCAL_REPO}"

  mvn verify sonar:sonar -f ${ROOT_IMPL} \
    -Dsonar.host.url=http://sonar.fab-outils.k8s.soie-baiser.intra \
    -Dsonar.projectKey=${PROJECT_KEY}:${PROJECT_NAME} \
    -Dsonar.projectVersion=${VERSION}
  ```

#### `execute-ti.yaml`
- **Image** : `odt/maven-java-node:3.8.6-17-18.14.2-R1`
- **Outputs** : `rapports-de-tests` — **Cache** : `maven`
- **Commandes** :
  ```bash
  mvn -f source/ti/pom.xml verify -Denvironment=tic
  cp -R source/ti/target/site/serenity/* rapports-de-tests
  exit ${result}  # propagation du code retour même si rapport copié
  ```

#### `execute-dependency-check-back.yaml`
- **Image** : `owasp/dependency-check-action:latest`
- **Params** : `NOM_COMPOSANT` — **Outputs** : `rapport-dependency-check`
- **Commandes** :
  ```bash
  dependency-check.sh --project "$NOM_COMPOSANT" --scan source -n \
    --format "ALL" --out rapport-dependency-check \
    --disableRetireJS --disableOssIndex --disableCentral \
    --disableNodeAudit --noupdate \
    --suppression http://git-scm.*/equipe-SLD/quarkus/raw/master/cve/project-suppression-*.xml \
    --suppression source/cve/project-suppression.xml
  ```
- Auto-création du fichier de suppression vide si absent

#### `execute-enf-tester.yaml`
- **Image** : `odt/maven-java-node:3.8.6-17-18.14.2-R1`
- **Outputs** : `rapport` — **Cache** : `maven`
- **Commandes** : `mvn -f source/impl/pom.xml enf-tester:enf-tester -PenfTester`
- Copie `source/impl/target/rapport-ENF/*` → `rapport/`

---

### Docker / Build image

#### `docker/build-image.yaml`
- **Image** : `concourse/oci-build-task-pe:0.10.0` (rootless OCI)
- **Params** : `REGISTRY_MIRRORS`, `CONTEXT`, `BUILD_ARG_VERSION`, `DOCKERFILE`
- **Outputs** : `image` (image.tar format OCI)

#### `docker/construit-image.yaml`
- **Image** : `incubateur/concourse-docker-image-build-task:1.3.1`
- **Params** : `REGISTRY_MIRROR`, `CONTEXT`, `TARGET=image/image.tar`
- **Cache** : `cache`

---

### Maven / Packaging

#### `maven/package-composant.yaml`
- **Image** : `maven-pe/jdk-17:1.0.0` — **Cache** : `maven`, `sonar`
- **Commandes** : `mvn clean package -ntp -DskipTests`

#### `deploy.yaml`
- **Image** : `mvn-openjdk-17:0.0.2` — **Params** : `VERSION` — **Cache** : `maven`
- **Commandes** :
  ```bash
  mvn versions:set -DnewVersion=((.:version)) -f ./source/pom.xml
  mvn deploy -f ./source/pom.xml
  mvn versions:revert -f ./source/pom.xml
  ```

---

### Database / Flyway

#### `flyway-reset.yaml`
- **Image** : `flyway/flyway:7.10-alpine`
- **Params** : `FLYWAY_URL`, `FLYWAY_USER`, `FLYWAY_PASSWORD`, `FLYWAY_CLEAN_DISABLED=false`
- **Commandes** : `flyway clean`

#### `flyway-scripts-execute.yaml`
- **Image** : `flyway/flyway:latest`
- **Params** : `FLYWAY_URL`, `FLYWAY_USER`, `FLYWAY_PASSWORD`, `SEED_PATH`
- **Commandes** :
  ```bash
  for file in $(ls ${SEED_PATH}/*.sql | sort); do
    flyway -executeSqlFile=$file
  done
  ```

---

### Tests / Reporting

#### `sauvegarde-rapports-sur-s3.yaml`
- **Image** : `incubateur/concourse-s3-task:1.16.248`
- **Params** : `NOM_DU_PROJET`, `BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ENDPOINT_URL`
- **Commandes** :
  ```bash
  aws --endpoint-url ${ENDPOINT_URL} s3 rm s3://${BUCKET}/${REPERTOIRE_RACINE}/${NOM_DU_PROJET} --recursive
  aws --endpoint-url ${ENDPOINT_URL} s3 sync rapports-de-tests s3://${BUCKET}/...
  ```
- URL consultation : `http://s3-web.onyx.k8s.soie-baiser.intra/api/conteneurs/...`

---

### API / Catalogue

#### `upload-capi.yaml`
- **Image** : `pe/catalogue-api-sync:1.1.0`
- **Params** : `api_spec_path`, `CODE_COMPOSANT`, `CODE_MFP`, `TYPE_API`, `ETAT_API`, `URL_COMPOSANT`, `CONTEXT_ROOT`, `BUILD_VERSION`, `ENVIRONNEMENT`
- Supporte 3 formats : URL live (`q/openapi?format=json`), fichier JSON (`jq`), fichier YAML (`yq`)

---

### Notifications / Teams

Toutes basées sur `alpine-curl:0.0.3`. **Proxy** : `http://proxyaws.*.intra:8080`

| Task | Déclencheur | Message |
|------|-------------|---------|
| `teams-build-ko` | Build échoué | "Le build de **$NOM** à la version **$VERSION** est en échec !" |
| `teams-publish-image-ko` | Image non publiée | "La publication de l'image ... est en échec !" |
| `teams-test-ko` | Tests échoués | "Le déploiement et/ou les tests ... sont en échecs !" |
| `teams-deploiement` | Déploiement OK/KO | "Le déploiment de **$NOM** est livré sur **$PARME**." / "...est en échec !" |
| `teams-deploiement-gw` | Déploiement GW | Idem + version dans le message |
| `teams-pipeline-ko` | Pipeline échoué | "L'installation du pipeline **$NOM** est en échec !" |

**Couleurs** : `#ff4d4d` (rouge = KO), `#2eb82e` (vert = OK)

---

### Patterns récurrents

**Cache Maven** :
```bash
M2_LOCAL_REPO="${HOME}/.m2/repository"
M2_CACHE="$(pwd)/maven"
rm -rf ${M2_LOCAL_REPO}
ln -s "${M2_CACHE}" "${M2_LOCAL_REPO}"
```

**Registry Docker privée** : `(("docker_complicite.registre"))` (cg926) / `(("docker_galanterie.registre"))` (<equipe>)

**Registry NPM corporate** :
```
http://artefact-repo.*.intra/artifactory/api/npm/npm-public
NG_CLI_ANALYTICS=false
CYPRESS_INSTALL_BINARY=0
```

**SonarQube** : `http://sonar.fab-outils.k8s.soie-baiser.intra`

**S3** : endpoint `http://s3-web.onyx.k8s.soie-baiser.intra`, bucket `s3_sauvegarde-concourse-m`

**OWASP** : formats ALL (JSON, HTML, XML, CSV), suppression CVE auto-créée si absente

---

### Chaînes de dépendances

```
Backend (Java)
  execute-dependency-check-back → execute-tu (SonarQube)
  execute-tu + execute-ti → sauvegarde-rapports-sur-s3

Frontend (Angular)
  dependency-check-angular → execute-angular-sonar
  execute-angular-ti → sauvegarde-rapports-sur-s3

Docker
  build-image / construit-image (après maven/package-composant optionnel)

API Catalog
  upload-capi (post-build)

Teams (erreurs)
  teams-build-ko / teams-test-ko / teams-publish-image-ko
  teams-deploiement / teams-deploiement-gw / teams-pipeline-ko
```

Paramètres clés : `CODE_COMPOSANT`, `CODE_MFP`, `TYPE_API` (ARDEUR|INTERNE), `ETAT_API` (STABLE|…)

### Identifiants Docker

Toutes les images dans `(("docker_complicite.registre"))` (pas `docker_galanterie`) — notation différente de repo-concourse.

### Inventaire complet des pipelines cg926-onyx

| Pipeline | Fichier | Branche | Jobs clés |
|----------|---------|---------|-----------|
| Quarkus release | `quarkus-pipeline.yml` | `master` | release → image → tis → va → vabp → bench → sensualite → prod → prodbp → camee → pms |
| Quarkus hotfix | `quarkus-pipeline-hotfix.yml` | `prod` | installation-pipeline → release → image → camee → sensualite → prod → prodbp → pms |
| Spring release | `spring-pipeline.yml` | `master` | release → image → tis → va → vabp → bench → sensualite → prod → prodbp → camee → pms |
| Spring hotfix | `spring-pipeline-hotfix.yml` | `prod` | installation-pipeline → release → image → camee → sensualite → prod → prodbp → pms |
| Oracle release | `oracle-pipeline.yml` | `master` | release → image → tis → bench → va → camee → dryrun_prod → sensualite → prod |
| Oracle hotfix | `oracle-pipeline-hotfix.yml` | `prod` | installation-pipeline → release → image → camee → dryrun_prod → sensualite → prod |
| WebLogic | `weblogic-pipeline.yml` | `master` | release → image (3) → swagger → tis → va → sensualite → prod |
| Config CF | `config-pipeline.yml` | `master` | création/màj services CF (RabbitMQ, Config Server, Conjur, Dynatrace) |
| Popete tests | `popete-test-pipeline.yml` | `master` | déclenché par timer (every-130m TIS, every-720m VA) |

**Hotfix** : tag regex `hotfix\.[[:digit:]]+\.[[:digit:]]+\.[[:digit:]]+` — branche `prod` directement.

### Applis couvertes par cg926-onyx

```
Quarkus JDK17 : cg926-emoi, cg926-cotisation, cg926-velours, cg926-dsn, cg926-omi,
                cg926-gateway, jg483-gestionpasseprofessionnel
Spring Boot   : cg926-hunter, cg926-identification
Oracle DB     : cg926-base (Flyway migrations uniquement, pas de microservice)
WebLogic EAR  : cg926-monolithe (3 images: app, bp, bridge + swagger)
```

### Vars par env — format `env/{env}/cg926-{app}.yml`

```yaml
# env/tis/cg926-hunter.yml
parme: tis
suffix: tis
instance: 4
memory: 2G
environment: tis
cadre-popete: TIS
tags-popete: "@VNR and not @QUARTZ and not @xFIX and not @NO-QL and @EXPO_TEST"
delice-check-http-endpoint: /cg926-<app>/actuator/delice

# env/va/cg926-hunter.yml
parme: va
cadre-popete: RE7
tags-popete: "@VNR and not @QUARTZ and not @xFIX and @EXPO_TEST and not @REPRISE"
```

### Paths Conjur — pattern par composant

```
Vault/galanterie/appli/cg926/{APP}/{ENV}

# Exemples
appli/cg926/hunter/{tis,va,camee,bench,prod,prodbp}
appli/cg926/emoi/{tis,va,vabp,camee,bench,prod,prodbp}   → QUARKUS_DATASOURCE_EMOI_PASSWORD, QUARKUS_DATASOURCE_QUARTZ_PASSWORD
appli/cg926/omi/{tis,va,vabp,camee,bench,prod,prodbp}
appli/cg926/base/{tis,bench,va,camee,prod}                → DD017_DS_PASSWORD, DD017_BP_DS_PASSWORD
```

### Bridge Conjur → Credhub (Spring CF)

```bash
# task: get-conjur-secrets.yml → secrets/secrets.json
secretops login -u ${CONJUR_URL} -i ${CONJUR_USER} -k ${CONJUR_PASS}
secretops export -o json -p Vault/galanterie/appli/cg926/${APP}/${ENV} > secrets/secrets.json

# task: synchronize-credhub-with-conjur.yml
# 1. Login CF
cf login -a "$API" -u "$USERNAME" -p "$PASSWORD" -o "$ORGANIZATION" -s "$PARME" --skip-ssl-validation

# 2. Récupère URL Config Server depuis service instance
URL_CONFIGSERVER=$(cf service config-server | grep https | sed 's/^.*\(https.*intra\).*$/\1/')

# 3. PUT secrets dans Credhub via Config Server API
curl -k $URL_CONFIGSERVER/secrets/$NOM_APPLICATION/$PARME/main/vault \
  -H "Authorization: $(cf oauth-token)" -X PUT \
  --data $CREDENTIALS -H "Content-Type: application/json"
```

### Dynatrace — intégration K8s et CF

**K8s (Quarkus/Oracle)** : tâche `apply-dynatrace-role.yml` après déploiement Helm sur camee/prod/prodbp/pms :
```yaml
# Fichier : dynatrace-oneagent-metadata-viewer.yaml
# Crée ClusterRole + RoleBinding pour permettre à l'agent Dynatrace de lire les métadonnées du pod
```

**Cloud Foundry (Spring)** : Service CF `dynatrace` (plan `standard`) créé par `config-pipeline.yml` sur va/camee/prod/pms. Bindé automatiquement au CF push.

### Popete tests — détail tags

| Job | Env (CADRE) | Tags Cucumber |
|-----|------------|---------------|
| `tis-tags-vnr-cremmetier` | TIS | `@VNR not @xFIX and @EXPO_TEST and @CREMMETIER and not @NO-QL` |
| `tis-tags-vnr-pajemploi` | TIS | `@VNR not @xFIX and @EXPO_TEST and @PAJEMPLOI and not @NO-QL` |
| `va-tag-recevabilite-re7` | RE7 | `@RECEVABILITE @RE7 @EXPO_TEST` |
| `va-tags-vnr-fctu` | RE7 | `@VNR not @xFIX and @EXPO_TEST and @FCTU` — `TEMPO: 90000` |
| `va-beta-prod-re7-bp` | RE7_BP | `@RECEVABILITE @RE7-BP @EXPO_TEST` |

Rapports sauvegardés sur S3 : `s3://cg926-test/{job-name}/popete`

### WebLogic — spécificités

```yaml
# 3 images Docker construites en parallèle
image-((weblogic)):        Dockerfile      # application principale
image-((weblogic))-bp:     DockerfileBP   # backup passif
image-((weblogic))-bridge: DockerfileBridge  # bridge réseau

# Swagger déployé via Helm dédié
helm chart: ((weblogic))-swagger:2.0.0
ingress: cg926-swagger.dev.k8s.soie-baiser.intra

# Notifications via Slack (PAS Teams — différent des autres pipelines)
resource_types:
  - name: slack-notification
    type: registry-image
    source:
      repository: cfcommunity/slack-notification-resource:v1.6.0
```

### Flyway Oracle — détail cg926-base

```
Flyway URLs par env : ((flyway.url.tis)), ((flyway.url.va)), ..., ((flyway.url.prod))
Image : boxfuse/flyway:5.1.4-alpine
Dryrun SQL report → sauvegardé sur S3 pour audit avant PROD
CLEAN_DISABLED=true pour les URLs prod *.lapis.*
```

---

### Scripts fly (cg926-soie — 26 fichiers)

#### Init pipelines
```bash
init-quarkus-pipeline.sh <app>         # quarkus=$1 → cg926-<app>
init-quarkus-pipeline-hotfix.sh <app>  # quarkus=$1 → cg926-prod
init-spring-pipeline.sh <app>          # spring=$1 + tas-spaces.yml
init-spring-pipeline-jdk21.sh <app>    # spring=$1 JDK21 variant
init-spring-pipeline-hotfix.sh <app>   # spring=$1 → cg926-prod
init-oracle-pipeline.sh                # oracle=cg926-base → cg926-<app>
init-oracle-pipeline-hotfix.sh         # oracle=cg926-base → cg926-prod
init-weblogic-pipeline.sh              # weblogic=cg926-monolithe
init-feature-pipeline.sh <feat>        # feat=$1, crée feat-$1.yml + namespace-$1.yml
init-popete-test-pipeline.sh           # popete=cg926-test
init-popete-a-corriger-pipeline.sh     # popete=cg926-xtest-va
init-popete-a-corriger-pipeline-tis.sh # popete=cg926-tis-m12
init-popete-a-corriger-pipeline-calin.sh # popete=cg926-xtest-calin
init-popete-calin-hotfix-pipeline.sh   # popete=cg926-test → cg926-prod
init-spaces-pipeline.sh                # configuration=tas-spaces
init-all-pipelines.sh                  # Orchestrateur (appelle tous)
```

**Modèle standard** :
```bash
fly -t galanterie set-pipeline \
  -c "$REPERTOIRE_PROJET/pipeline/quarkus-pipeline.yml" \
  -p "cg926-<app>" \
  -l "$REPERTOIRE_PROJET/pipeline-vars/$1.yml" \
  -v snow_check_interval=5m \
  --instance-var quarkus=$1
```

#### Destroy
```bash
destroy-pipeline.sh <type> <instance>     # destroy -p "cg926-*/$type:$instance"
destroy-feature-pipeline.sh <feat>        # destroy feat + supprime vars + delete-namespace
destroy-all-pipelines.sh                  # Orchestrateur
```

#### Pause / Unpause
```bash
pause-job.sh <type> <instance> <job>      # NOM_PIPELINE=cg926-<app>
unpause-job.sh ...
pause-changement.sh <type> <instance>     # pause spécifique job "changement"
unpause-changement.sh ...
pause-prod-job.sh ...                     # NOM_PIPELINE=cg926-prod (hotfix)
unpause-prod-job.sh ...
unpause-prod-changement.sh ...
pause-changement-az418.sh                 # Script spécifique az418-cachetransverse
```

### Variables globales cg926-soie

#### `pipeline-vars/cg926-base.yml` — Flyway Oracle
```yaml
flyway:
  user:
    tis: BDD01700 / va: RDD01700 / calin: TDD01700 / bench: NDD01700 / prod: PDD01700
  url:
    tis:  jdbc:oracle:thin:@(DESCRIPTION=...) hosts: xob60000 (CAMEE)
    va:   jdbc:oracle:thin:@(DESCRIPTION=...) hosts: rob60000 (CAMEE)
    prod: jdbc:oracle:thin:@(DESCRIPTION=...) hosts: pob60000 (ECLAT)
```

#### `pipeline-vars/tas-spaces.yml` — Cloud Foundry / TAS
```yaml
cf-organization-fab: galanterie / cf-organization-prod: galanterie
domain-fab:  apps.tas-fab.emoi-baiser.intra
domain-prod: apps.tas-prod.emoi-baiser.intra
cf-space-{tis,va,lune,calin,bench,prod,delice}: <nom-espace>
```

### Features branches (cg926-soie)

```
pipeline-vars/features/
├── feat-default.yml          # Template (branche master, tag latest pour toutes les apps)
├── feat-teexpos2443.yml      # TEEXPOS-2443
├── feat-teexpos2635.yml
├── feat-teexpos2709.yml
├── feat-te-expos-2727.yml
└── namespace-*.yml           # Namespaces K8s dédiés
```

```yaml
# feat-default.yml
popete-cg926-tags-a-la-demande: "@a_renseigner_si_besoin"
cg926-crem:
  branche: master
  tag: latest
# ... toutes les apps
```

---

## Bonnes pratiques avancées

### `inputs: detect` sur les `put` steps

Par défaut, un `put` envoie **tous** les outputs du job au worker (source-code + tasks + versionning + ...). Utiliser `inputs: detect` (ou spécifier explicitement) pour limiter :

```yaml
- put: image-docker
  inputs: detect       # auto-détecte uniquement les inputs référencés dans params
  params:
    build: source-build
    tag_file: versionning/number
```

**Impact** : moins de données transférées au worker → moins d'attente avant le `put`.

### `across` + `set_pipeline` — gestion dynamique de flotte

Remplace les scripts `init-quarkus-pipeline.sh` manuels. Un job gère tous les pipelines :

```yaml
jobs:
  - name: set-all-quarkus-pipelines
    plan:
      - get: repo-<equipe>-ci
        trigger: true
      - load_var: components
        file: repo-<equipe>-ci/pipeline-vars/components-list.json
        format: json
        # components-list.json: ["<app>", "autre-composant"]
      - across:
          - var: component
            values: ((.:components))
        set_pipeline: quarkus
        file: repo-<equipe>-ci/ci/quarkus-pipeline.yml
        instance_vars:
          quarkus: ((.:component))
        var_files:
          - repo-<equipe>-ci/pipeline-vars/((.:component)).yml
```

**Avantages** :
- Ajouter un composant : ajouter son vars file + mettre à jour `components-list.json` → push → pipeline créé
- Supprimer un composant : retirer de la liste → pipeline archivé automatiquement
- Mettre à jour le template : modifier `quarkus-pipeline.yml` → tous les pipelines mis à jour

### Flyway — `validate` avant `migrate`

```bash
# Ordre recommandé (détecte les migrations modifiées après application)
flyway \
  -url=jdbc:oracle:thin:@${DB_HOST}:${DB_PORT}/${DB_SID} \
  -user=${FLYWAY_USER} -password=${FLYWAY_PASSWORD} \
  -cleanDisabled=true \
  -outOfOrder=false \
  validate migrate info
```

**`validate`** : vérifie les checksums des migrations déjà appliquées — détecte si un fichier SQL a été modifié après avoir été joué (erreur courante en dev). Coût : quasi nul. Ne jamais faire `migrate` sans `validate` en prod.

### Pinning de `tasks-all-in-one` sur semver tags

**Problème actuel** : si `branch: main` de `tasks-all-in-one` reçoit un changement cassant, tous les pipelines qui font un `get: tasks-all-in-one` au prochain run vont être brisés.

**Solution** : utiliser `concourse-git-semver-tag` (déjà dans votre stack) pour pinning :
```yaml
- name: tasks-all-in-one
  type: concourse-git-semver-tag
  source:
    uri: ssh://...tasks-all-in-one.git
    private_key: (("gitlab.cle_privee"))
    tag_filter: "v*"
```
Ou utiliser `tag: v1.2.3` dans un resource `type: git` pour pin manuel.

### `in_parallel` avec `fail_fast` et `limit`

```yaml
- in_parallel:
    fail_fast: true     # annule les steps en cours si l'un échoue
    limit: 3            # max 3 steps concurrent (évite de saturer l'API K8s)
    steps:
      - put: deploy-va
      - put: deploy-bench
      - put: deploy-camee
```

---

## Idées d'amélioration CI/CD

| Priorité | Action | Effort | Impact |
|----------|--------|--------|--------|
| **Haute** | Ajouter `inputs: detect` sur tous les `put: image-docker` | Faible (5 min/pipeline) | Moins de transfert réseau |
| **Haute** | Ajouter `flyway validate` avant `flyway migrate` dans flyway.yml | Faible | Détecte les migrations modifiées post-apply |
| **Haute** | `set_pipeline` dans un job `ci` déclenché sur changement du template | Moyen | Élimine les `init-quarkus-pipeline.sh` manuels |
| **Moyenne** | Upgrader Flyway de 5.1.4 → 9.x (meilleur support Oracle, `flyway check`) | Moyen (tester migrations) | Support Oracle amélioré + dry-run natif JSON |
| **Moyenne** | Ajouter `helm diff` avant les deploys non-prod | Moyen | Visibilité des changements K8s avant apply |
| **Moyenne** | Déplacer OWASP Dependency Check dans un job parallèle non-bloquant | Moyen | Build chain principale plus rapide |
| **Moyenne** | Pinner `tasks-all-in-one` et `galanterie-onyx` sur semver tags | Faible | Évite les régressions par mise à jour involontaire |
| **Basse** | Feature branch pipelines instanciés (CI par PR) avec archivage auto | Fort | CI avant merge, meilleure qualité |
| **Basse** | Quarkus native image (build Mandrel) pour TIS | Fort | Startup <15ms, empreinte mémoire réduite |
| **Basse** | Migration <code> Quarkus 2.16 → 3.x (`quarkus update` tool) | Fort | jakarta.*, Hibernate ORM 6.x, extensions renommées |

### Détails : migration Quarkus 2.16 → 3.x

Quand la décision sera prise, utiliser :
```bash
# CLI Quarkus (outil officiel de migration automatisée)
quarkus update --stream=3.x
# Puis : git diff pour vérifier les transformations
```

Changements majeurs à vérifier :
- `javax.*` → `jakarta.*` (tous les packages Jakarta EE)
- `@AlternativePriority` → `@Alternative + @Priority`
- `@Transactional` sur méthodes `private` : ignoré silencieusement en 2.16, **erreur de build** en 3.x
- Hibernate ORM 5.6 → 6.2 (changements API significatifs)
- RESTEasy extension : `quarkus-resteasy` → `quarkus-rest` (renommé en 3.9)
- Extension health : reste `quarkus-smallrye-health` (inchangé)

### Détails : Concourse v10 — ce qui arrive (roadmap, pas encore livré)

- **Projects** : namespace pipeline+resource+task bootstrappé depuis un git — remplacerait les scripts `init-*.sh`
- **Resources v2** : interface plus propre, `get` retourne un objet structuré (breaking change pour resource types existants)

**Pratique** : ne pas attendre v10. Les patterns `across` + `set_pipeline` + `load_var` disponibles en v7 couvrent 95% des besoins de pipelines dynamiques.

---

## <equipe>-soie — Nouveautés vs repo-concourse

**Repo** : `<equipe>-soie` (pseudonymisé) — version enrichie de repo-concourse

### Nouvelles tasks (`tasks/build/`)

#### `allure-soupir.yml`
- **Image** : `frankescobar/allure-docker-service:2.19.0`
- **Input** : `out-surefire` (résultats Surefire XML)
- **Output** : `out-allure` (rapport Allure HTML)
- **Rôle** : Génère rapports Allure depuis les résultats Surefire
- **Commande** : `allure generate ../out-surefire`

#### `soupir-to-s3.yml`
- **Image** : `polygone/concourse/maven-jdk17:0.0.1`
- **Input** : `out-allure`
- **Output** : `out-reports`
- **Rôle** : Upload rapports Allure sur S3 + génère un `index.html` agrégé avec liens vers :
  - ENF Tester (URL S3 web)
  - Dashboard SonarQube
  - Rapports Allure
- **Pattern** : `aws s3 sync --delete` (écrase les anciennes versions)

#### `changelog-tag-git.yaml`
- **Image** : `galanterie/node:alpine-21.5.0`
- **Inputs** : `source-code`, `changelog`
- **Output** : `source-code`
- **Rôle** : Crée un tag Git sémantique + valide le CHANGELOG
- **Logique** :
  - Ne tague que les versions stables (pas de `-` dans `revision`)
  - Copie `CHANGELOG.md` si présent
  - Commit message : `"soie(version): montée en version ${revision}"`
  - Tag annoté : `"Tag valued by Semantic-Release and Concourse"`

---

### Pipeline <code> monolithique (`ci/<code>-pipeline-main.yaml`)

Pipeline **propre à <code>** (non générique). Différent du `quarkus-pipeline.yml` instancié :

```
build-docker → deploy-and-run-ti → publish-image-and-tag-repo
                    ↓ (ensure)
              sauvegarde Allure S3
                                  ↓
              deploy-env-dev / deploy-env-va / deploy-env-calin / deploy-env-prod
```

**Groups** : `build`, `deployment`, `ci`, `prod`

**Resource types spécialisés** :
- `kubernetes-resource` : kubectl
- `concourse-git-semver-tag` : versioning sémantique
- `metadata` : métadonnées pipeline
- `helm-resource-deploiement` : Helm (`v1.29.1`)

**Job `deploy-and-run-ti`** — spécificités :
1. Déploie sur cluster TI (Z4-dev)
2. Valorise les values Helm (templating)
3. Crée namespace dynamiquement
4. Exécute tests d'intégration
5. `ensure`: sauvegarde rapports **Allure** sur S3 (via `allure-soupir` + `soupir-to-s3`)

**Variables chart Helm** :
```yaml
chart-helm:
  frisson_repo_name: helm-dev-frisson
  name: sld-ng
  version: 2.58.0    # vs 2.51.0 pour quarkus-pipeline
```

---

### `quarkus-pipeline.yml` — comparaison <code>-pipeline-main vs quarkus-pipeline

| Aspect | <code>-pipeline-main.yaml | quarkus-pipeline.yml |
|--------|--------------------------|----------------------|
| Structure | Monolithique (1 composant) | Instance (`--instance-var quarkus=<name>`) |
| Versioning | Automatique (patch bump) | Sémantique (conventional-commits) |
| Release | Implicite dans build-docker | Job `release` séparé |
| Changements SNOW | Non présent | Job `changement` (IAMS payload) |
| TI | `deploy-and-run-ti` | Job `tis` puis `va` |
| Déploiement prod | Direct | Via changement SNOW |
| Post-prod | N/A | Job `pms` (monitoring) |
| Rapports S3 | `ensure` block | Via `allure-soupir` + `soupir-to-s3` |
| Helm chart version | 2.58.0 | 2.51.0 |

---

### Configuration `pipeline-vars/<app>.yml`

Secrets Conjur par environnement (4 envs : dev, va, calin, prod) :

```yaml
# Pattern : (("<code>/ENV_NAME.secret_name"))
quarkus-datasource-*      : Connexion DB principale (JDBC URL, username, password)
quarkus-datasource-<code>-*: Connexion DB secondaire OI277 (3 secrets)
quarkus-schema_registry-url
quarkus-kafka-broker-url
quarkus-kafka-topic / quarkus-kafka-topic-de
kafka-topic-pli-transmis / kafka-topic-pli-transmis-dlq
kafka-wave-server-url / kafka-wave-username / kafka-wave-password
stockageclient-url / stockageclient-accesskey / stockage-client-secretkey / stockage-client-bucket
```

---

### Overlays TI (Tests d'Intégration)

**Dossier** : `infra-as-code/overlays/TI/<code>/`

```yaml
# values.yaml
createServicesCommuns: false
exclureAnnuaireAaeCommun: true
monitoring: "none"
composant: <code> / equipe: <equipe> / blocPos: stra
image.repository: <equipe>/<app>
contextRoot: <app>
resources: CPU 1000m-2500m / Memory 2048-4096Mi
SLDNG_ENVIRONNEMENT: ENV_TI_OI277
```

**Overlays DEPLOYMENT** (4 envs : Z4-dev, Z4-va, Z4-calin, Z4-prod) :

| Env | `SLDNG_ENVIRONNEMENT` | Replicas |
|-----|----------------------|---------|
| dev | `ENV_TIS_OI277` | défaut |
| va | `ENV_VA_OI277` | défaut |
| calin | `ENV_IQRFT_OI277` (VA-CPP) | 4 |
| prod | `ENV_PROD_OI277` | défaut |

---

### Scripts d'administration spécifiques

```bash
<code>-init-main.sh               # Init pipeline <app>-master
init-quarkus-pipeline.sh <app>   # Init support-data-solution --instance-var quarkus=$1
pause-changement.sh <type> <instance>    # Pause job changement
unpause-changement.sh <type> <instance>
pause-job.sh / unpause-job.sh    # Pause job générique
destroy-pipeline.sh              # Supprime une instance de pipeline
```

---

### Bouchons Kubernetes (`infra-as-code/bouchons/`)

Dossiers par env : `{dev,ti,va,calin}/api-du-modele/`

Composants déployés (MockServer `jamesdbloom/mockserver:5.9.0`) :
- Port : 8081
- Labels : `code-composant=jp270`, `sous-composant=frontend`, `bloc-pos=stra`
- Resources : memory 50-250Mi, CPU 50-500m

---

### ServiceNow — détail SNOW resource

```yaml
- name: changement-snow
  type: concourse-snow-resource  # tag: 3.1.8
  source:
    SNOW_URL: (("snow_prod.url"))
    S3_ENDPOINT_URL: (("s3_sauvegarde-concourse-m.endpoint"))
    FOLDER_PATH: <equipe>/complicite-iams/((quarkus))/reference-complicite
    WORKFLOW: default_s3
  check_every: ((snow_check_interval))
```

**Flux** : payload IAMS buildé (`iams.yml` du repo source) → stocké S3 → changement créé SNOW → job `prod` attend déclenchement.

---

### SonarQube — URLs par périmètre

| Périmètre | URL SonarQube | Clé projet |
|-----------|--------------|------------|
| <code> | `https://sonar.fab-outils.k8s.emoi-baiser.intra/` | `fr.pe.stra.tech.<code>` |
| cg926 Quarkus | `https://sonar.fab-outils.k8s.emoi-baiser.intra/` | `fr.pe.rind.service:{{quarkus}}` |

---

## Repo 3 : lilastemplateapplication (Template Cookiecutter Python)

**Repo** : `lilastemplateapplication`
**Path local** : `/home/jd/pseudo/lilastemplateapplication/`
**Type** : Template Cookiecutter pour apps Python (Streamlit)
**Concourse** : `https://mad.concourse.craftspace.app.cloud.intra` — team `dops-mps-lilas`
**Intérêt** : Patterns CI/CD modernes et propres, réutilisables pour tout type de projet.

### Structure générée

```
{code}-{nom}/
├── ci/
│   ├── pipeline.yaml                    ← pipeline master (RC → preprod → V → prod)
│   ├── pipeline_current_branch.yaml     ← pipeline feature branch (build → preprod)
│   ├── vars.yaml                        ← variables pipeline (cookiecutter-templated)
│   ├── initialisation.sh               ← script interactif fly set-pipeline
│   └── tasks/
│       ├── python_task_lancement_test.yaml
│       ├── docker-build-task-fabrique-image.yaml
│       ├── curl_task_check_streamlit_is_up.yaml
│       ├── curl_task_webhook-git-app.yaml
│       ├── git_task_tag_current_commit_to_rc.yaml
│       ├── git_task_tag_current_commit_to_v.yaml
│       ├── git_task_get_current_commit_rc_tag.yaml
│       ├── git_task_get_last_v_tag.yaml
│       ├── git_task_get_before_last_v_tag.yaml
│       ├── k8s-task-renseigne-la-version-a-deployer.yaml
│       ├── k8s-task-creation-secrets-fab.yaml
│       └── k8s-task-creation-secrets-prod.yaml
├── deployments/
│   ├── base/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   ├── cronjob.yaml
│   │   ├── externalsecret.yaml
│   │   └── secretstore.yaml
│   └── overlays/
│       ├── z6-dev/
│       ├── z6-dev-individuel/           ← namespace par développeur
│       ├── z6-preprod/
│       └── z6-prod-mop/
├── Dockerfile
├── Makefile                             ← interface unifiée développeur
└── .pre-commit-config.yaml
```

---

### Pattern RC/V — Versioning sémantique à deux étages

**Principe** : Chaque commit sur master produit un tag **RC-x.y.z** (Release Candidate). Après validation en preprod, le RC est promu en **V-x.y.z** (Version prod).

```
commit → RC-1.2.3 → deploy preprod → validation → V-1.2.3 → deploy prod
```

#### Calcul automatique de la version (task `git_task_tag_current_commit_to_rc.yaml`)

```bash
# Lecture du dernier RC tag
LAST_RC=$(git tag -l 'RC-*' --sort=-creatordate | head -1)
# Extraction major.minor.patch
MAJOR=$(echo $LAST_RC | cut -d'-' -f2 | cut -d'.' -f1)
MINOR=$(echo $LAST_RC | cut -d'-' -f2 | cut -d'.' -f2)
PATCH=$(echo $LAST_RC | cut -d'-' -f2 | cut -d'.' -f3)

# Incrément basé sur le message de commit
COMMIT_MSG=$(git log -1 --pretty=%B)
case "$COMMIT_MSG" in
  *\[BREAKING-*\]*|*\[MAJOR-*\]*)  MAJOR=$((MAJOR+1)); MINOR=0; PATCH=0 ;;
  *\[FEAT-*\]*)                     MINOR=$((MINOR+1)); PATCH=0 ;;
  *\[FIX-*\]*|*\[BUG-*\]*|*\[REFACTOR-*\]*|*\[STYLE-*\]*|*\[PERF-*\]*)
                                    PATCH=$((PATCH+1)) ;;
  *)                                PATCH=$((PATCH+1)) ;;  # fallback = patch
esac

git tag "RC-${MAJOR}.${MINOR}.${PATCH}"
git push origin "RC-${MAJOR}.${MINOR}.${PATCH}"
```

| Préfixe commit | Incrément | Exemple |
|----------------|-----------|---------|
| `[BREAKING-*]`, `[MAJOR-*]` | major (+x) | `[BREAKING-API] remove /v1 endpoints` |
| `[FEAT-*]` | minor (+y) | `[FEAT-KAFKA] add DLQ support` |
| `[FIX-*]`, `[BUG-*]`, `[REFACTOR-*]`, `[STYLE-*]`, `[PERF-*]` | patch (+z) | `[FIX-DB] correct Flyway checksum` |
| Autres | patch (+z) | `update README` |

#### Promotion RC → V (task `git_task_tag_current_commit_to_v.yaml`)

```bash
# Récupère le RC tag sur le commit courant
RC_TAG=$(git tag --points-at HEAD | grep '^RC-')
if [ -z "$RC_TAG" ]; then
  echo "ERROR: no RC tag on current commit"
  exit 1
fi
# Crée le V tag correspondant
VERSION=$(echo $RC_TAG | sed 's/RC-//')
git tag "V-${VERSION}"
git push origin "V-${VERSION}"
```

#### Rollback (récupère l'avant-dernier V tag)

```bash
# task: git_task_get_before_last_v_tag.yaml
BEFORE_LAST_V=$(git tag -l 'V-*' --sort=-creatordate | sed -n '2p')
echo "$BEFORE_LAST_V" | sed 's/V-//' > version/version
```

**Comparaison avec repo-concourse** :

| Aspect | repo-concourse | lilastemplateapplication |
|--------|---------------|--------------------------|
| Versioning | `concourse-git-semver-tag` (resource type) | Tags Git natifs RC/V (scripts bash) |
| Convention | Conventional Commits (`feat:`, `fix:`) | Préfixes entre crochets (`[FEAT-*]`) |
| Promotion | Retag image Docker (SHA → semver) | Tag Git V-x.y.z depuis RC-x.y.z |
| Rollback | Manuel (redeploy ancienne version) | Job dédié (avant-dernier V tag) |

---

### Dual pipeline : master + feature branch

#### `pipeline.yaml` — Master (6 jobs)

```
installation-du-pipeline-master
    ↓
construction-du-livrable         ← test + tag RC + build image
    ↓
deploy-z6-preprod                ← deploy RC + health check
    ↓
creation-version-prod            ← tag V + rebuild image
    ↓
deploy-z6-prod-mop               ← deploy V en prod
    ↓
deploiment-avant-begoniae-version-prod   ← rollback (avant-dernier V)
```

#### `pipeline_current_branch.yaml` — Feature branch (3 jobs)

```
installation-du-pipeline
    ↓
construction-du-livrable         ← test + build image (tag = short_ref)
    ↓
deploy-z6-preprod                ← deploy feature + health check
```

**Différences clés** :
- Feature branch utilise `.git/short_ref` comme tag image (pas de semver)
- Pas de déploiement prod
- Pipeline détruit après merge (via `fly destroy-pipeline`)

#### Script `initialisation.sh` — interactif

```bash
#!/bin/bash
read -p "Pipeline pour la branche master (m) ou la branche courante (f) ? " choice
case "$choice" in
  m) fly -t lilas set-pipeline \
       -c ci/pipeline.yaml \
       -l ci/vars.yaml \
       -p "$PROJECT_NAME" ;;
  f) BRANCH=$(git branch --show-current)
     # Crée un fichier vars temporaire avec le nom de la branche
     cat ci/vars.yaml > ci/vars_current_branch.yaml
     echo "branch:" >> ci/vars_current_branch.yaml
     echo "  name: $BRANCH" >> ci/vars_current_branch.yaml
     fly -t lilas set-pipeline \
       -c ci/pipeline_current_branch.yaml \
       -l ci/vars_current_branch.yaml \
       -p "$PROJECT_NAME-$BRANCH" ;;
esac
```

---

### Health check post-déploiement

Task `curl_task_check_streamlit_is_up.yaml` :

```yaml
platform: linux
image_resource:
  type: registry-image
  source:
    repository: curlimages/curl
    tag: "7.67.0"
params:
  PROJECT_NAME: ""
  ENV: ""
run:
  path: sh
  args:
    - -ec
    - |
      STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        "http://${PROJECT_NAME}.${ENV}.k8s.yuca-ecorce.intra/")
      echo "HTTP status: $STATUS"
      if [ "$STATUS" != "200" ]; then
        echo "FAIL: expected 200, got $STATUS"
        exit 1
      fi
```

**Pattern applicable à tout projet** : après chaque `put: deploy`, ajouter une task curl qui vérifie le health endpoint. Adapter l'URL selon la techno :
- Quarkus : `http://{app}.{env}.k8s.intra/{contextRoot}/q/health`
- Angular : `http://{app}.{env}.k8s.intra/ihm-{app}/`
- Python/Streamlit : `http://{app}.{env}.k8s.intra/`

---

### Namespace individuel développeur

Overlay `z6-dev-individuel/` avec patches dynamiques générés par le Makefile :

```yaml
# namespace-patch-individuel.yaml (généré par make deploy)
apiVersion: v1
kind: Namespace
metadata:
  name: {code}-{nom}-{user}      # ex: ua304-lilastemplate-jdellac
  annotations:
    equipe: dops-mps-lilas
    environnement: developpement

# deployment-patch-individuel.yaml
- op: replace
  path: /spec/template/spec/containers/0/image
  value: docker-dev-virtual/{equipe}/{code}-{nom}:dev-{user}

# ingress-patch-individuel.yaml
- op: replace
  path: /spec/rules/0/host
  value: {code}-{nom}-{user}.z6-dev.k8s.yuca-ecorce.intra
```

**Avantages** :
- Chaque développeur a son propre namespace, ingress, et image tag
- Pas de collision entre les développeurs sur l'env dev
- Le Makefile génère les patches automatiquement depuis `$USER`

---

### ExternalSecrets + Conjur (SecretStore)

Pattern Kubernetes natif pour injecter les secrets depuis Conjur sans les mettre en clair :

```yaml
# secretstore.yaml — une fois par namespace
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: dops-mps-lilas
spec:
  provider:
    conjur:
      url: https://gsa.yuca-ecorce.intra
      auth:
        apikey:
          account: yucaecorce
          userRef:
            name: conjur-creds
            key: hostid
          apiKeyRef:
            name: conjur-creds
            key: apikey

# externalsecret.yaml — un par application
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {code}-secret
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: dops-mps-lilas
    kind: SecretStore
  target:
    name: {code}-secret
  data:
    - secretKey: S3_ACCESS_KEY
      remoteRef:
        key: dops-mps-lilas/{code}/fab/S3_ACCESS_KEY    # patché par overlay (fab→prod)
    - secretKey: S3_SECRET_KEY
      remoteRef:
        key: dops-mps-lilas/{code}/fab/S3_SECRET_KEY
```

**Comparaison avec repo-concourse/cg926** :

| Aspect | repo-concourse / cg926 | lilastemplateapplication |
|--------|----------------------|--------------------------|
| Injection secrets | Conjur `(("path.key"))` dans pipeline → ConfigMap | ExternalSecrets Operator → Secret K8s natif |
| Refresh | À chaque déploiement | Automatique (`refreshInterval: 1h`) |
| Visibilité | Secrets transitent par Concourse vars | Secrets jamais dans Concourse, directement K8s ↔ Conjur |
| Setup | Rien à installer | ExternalSecrets Operator + SecretStore par namespace |

**Recommandation** : ExternalSecrets est plus sécurisé (les secrets ne passent jamais par Concourse). Utiliser ce pattern pour les nouveaux projets.

---

### Kustomize vs Helm

| Aspect | repo-concourse / cg926 (Helm) | lilastemplateapplication (Kustomize) |
|--------|------------------------------|--------------------------------------|
| Chart | `sld-ng` (chart PE mutualisé) | Pas de chart, manifestes YAML directs |
| Overlays | Values YAML par env | Kustomize overlays + patches JSON |
| Versioning image | Dans values.yaml (champ `image.tag`) | `kustomize edit set image` (task) |
| Deploy | `helm upgrade --install --atomic` | `kubectl apply -k overlays/{env}/` |
| Complexité | Chart PE avec 100+ paramètres | Manifestes simples, patches ciblés |
| Flexibilité | Limité par le chart | Totale (tout YAML K8s possible) |

**Choix** : Helm quand le chart PE `sld-ng` couvre le besoin (Quarkus standard). Kustomize quand le projet sort du moule (Python, stacks custom, CronJobs).

---

### Makefile comme interface développeur

Pattern de lilastemplateapplication : le Makefile expose **toutes** les opérations du projet.

```makefile
# Développement
setup:          ## Crée venv, installe deps, pre-commit hooks
lint:           ## Ruff check + format
test:           ## Pytest avec coverage

# Docker
build:          ## Build image locale (tag: dev-$USER)
run:            ## Run image locale avec .env
publish:        ## Push dev image sur Artifactory

# Kubernetes
deploy:         ## Deploy sur z6-dev (namespace individuel)
.env:           ## Génère .env depuis Clematite (Conjur CLI)
once-secretstore: ## Crée SecretStore K8s (one-time)

# Pipeline
pipeline:       ## Interactif : master ou feature branch
pipeline-master:
pipeline-feature-branch:

# Qualité
check-packages-vulnerabilities: ## pip-audit
check-code-vulnerabilities:     ## bandit
```

**Pattern réutilisable** : même interface pour les projets Java/Angular, en adaptant les targets :

```makefile
# Pour un projet Quarkus
setup:    ## mvn dependency:resolve
test:     ## mvn verify -P !ti
build:    ## docker build
dev:      ## mvn quarkus:dev
deploy:   ## kubectl apply -k deployments/overlays/z6-dev/
pipeline: ## fly set-pipeline
```

---

### Docker build OCI (pattern commun)

Task `docker-build-task-fabrique-image.yaml` (identique entre les repos) :

```yaml
platform: linux
image_resource:
  type: registry-image
  source:
    repository: concourse/oci-build-task-pe
    tag: "0.10.0"
inputs:
  - name: git-repo
outputs:
  - name: image
caches:
  - path: cache
params:
  CONTEXT: git-repo
  DOCKERFILE: git-repo/Dockerfile
  REGISTRY_MIRRORS: http://((docker-registry))
run:
  path: build
```

**Points clés** :
- `concourse/oci-build-task-pe:0.10.0` — build OCI rootless (pas besoin de Docker socket)
- Output : `image/image.tar` (format OCI standard)
- Cache : layers Docker réutilisés entre builds
- `REGISTRY_MIRRORS` : accélère les pulls depuis le registry interne

---

### Pre-commit hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: no-commit-to-master
        name: Interdit commit direct sur master
        entry: bash -c 'test "$(git branch --show-current)" != "master"'
        language: system
        stages: [commit]
      - id: ruff-check
        name: Ruff lint
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: Ruff format
        entry: uv run ruff format
        language: system
        types: [python]
      - id: pytest
        name: Tests
        entry: uv run pytest
        language: system
        stages: [commit]
```

**Équivalent Java** (à implémenter) :
```yaml
hooks:
  - id: no-commit-to-master
    entry: bash -c 'test "$(git branch --show-current)" != "master"'
  - id: checkstyle
    entry: mvn checkstyle:check -q
  - id: unit-tests
    entry: mvn test -q -P !ti
```

---

## Synthèse — Patterns à adopter par type de projet

### Pour un nouveau projet Quarkus (comme <code>)

| Étape pipeline | Pattern source | Implémentation |
|---------------|----------------|----------------|
| Build + TU | repo-concourse | `build-analyze-quarkus-jdk17.yml` |
| Versioning | lilas (RC/V) | Tags RC/V natifs sur Git |
| OWASP | repo-concourse | `dependency-check.yml` |
| SonarQube | repo-concourse | `execute-sonar-jdk17.yml` |
| Image Docker | commun | `concourse/oci-build-task-pe:0.10.0` |
| Deploy TI | repo-concourse | Helm `sld-ng` + run TI |
| Deploy dev/va/prod | repo-concourse | Helm `sld-ng` + Flyway |
| Flyway | repo-concourse | `flyway.yml` + `flyway-dryrun.yaml` avant prod |
| Health check | lilas | curl sur `/q/health` post-deploy |
| Rollback | lilas | Job dédié (avant-dernier V tag) |
| Secrets | lilas | ExternalSecrets + Conjur (si disponible) |
| Reports | repo-concourse | Allure + S3 |
| Change mgmt | repo-concourse | SNOW/IAMS (prod) |
| Feature branch | lilas | Pipeline séparé, destroy après merge |
| Alerting | repo-concourse | Webhook Teams on_failure |

### Pour un nouveau projet Angular

| Étape pipeline | Pattern source | Implémentation |
|---------------|----------------|----------------|
| Build + TU | tasks-all-in-one | `build-projet-angular.yaml` + `execute-angular-tu.yaml` |
| TI (E2E) | tasks-all-in-one | `execute-angular-ti.yaml` (Cypress) |
| OWASP | tasks-all-in-one | `dependency-check-angular.yaml` |
| SonarQube | tasks-all-in-one | `execute-angular-sonar.yaml` |
| Image Docker | commun | `oci-build-task-pe` (3-stage : npm → node → httpd) |
| Deploy | Kustomize ou Helm | Selon infra cible |
| Health check | lilas | curl sur `/ihm-{app}/` post-deploy |

### Pour un nouveau projet Python

| Étape pipeline | Pattern source | Implémentation |
|---------------|----------------|----------------|
| Build + TU | lilas | `python_task_lancement_test.yaml` (uv + pytest) |
| Versioning | lilas | RC/V tags |
| Image Docker | lilas | `docker-build-task-fabrique-image.yaml` |
| Deploy | lilas | Kustomize overlays + ExternalSecrets |
| Health check | lilas | `curl_task_check_streamlit_is_up.yaml` |
| Rollback | lilas | Avant-dernier V tag |
| Dev individuel | lilas | Overlay `z6-dev-individuel/` |

---

## Convention de nommage des pipelines

| Type | Nom pipeline | Exemple |
|------|-------------|---------|
| Master dédié | `{app}-master` | `dd281-pollinisationnalistements-master` |
| Générique instancié | `{project}/{type}:{app}` | `support-data-solution/quarkus:dd281` |
| Feature branch | `{app}-{branch}` | `dd281-feat-kafka-dlq` |
| Oracle DB | `{project}/oracle:{db}` | `support-data-solution/oracle:dd281-base` |

---

## Checklist nouveau pipeline Concourse

- [ ] **Pipeline self-update** : job `installation-du-pipeline` avec `set_pipeline: self`
- [ ] **Webhook** : `check_every: never` + `webhook_token` (GitLab → Concourse)
- [ ] **Versioning** : RC/V tags ou `concourse-git-semver-tag`
- [ ] **Build** : Maven/Node/uv + TU dans la même task
- [ ] **Qualité** : SonarQube + OWASP Dependency Check
- [ ] **Image** : `oci-build-task-pe` (rootless, cache layers)
- [ ] **Deploy TI** : namespace éphémère + tests d'intégration + `ensure: save-reports`
- [ ] **Deploy env** : Helm ou Kustomize + Flyway si Oracle
- [ ] **Health check** : curl post-deploy sur chaque env
- [ ] **Rollback** : job dédié (avant-dernière version)
- [ ] **Secrets** : ExternalSecrets (préféré) ou Conjur vars `(("path.key"))`
- [ ] **Alerting** : webhook Teams `on_failure` sur chaque job
- [ ] **Reports** : Allure/Serenity/HTML sur S3
- [ ] **Feature branch** : pipeline séparé si besoin CI pre-merge
- [ ] **Change mgmt** : SNOW/IAMS pour prod (si requis)
- [ ] **`inputs: detect`** : sur tous les `put` (optimisation transfert)
- [ ] **`atomic: true`** : sur Helm deploy env non-TI (rollback auto si KO)
- [ ] **`try:`** : sur namespace create/delete et save-reports (non-bloquant)

---

## Repos locaux — concourse-infra + concourse-pipelines

### concourse-infra (local uniquement, PAS porté en entreprise)

**Path** : `/home/jd/pseudo/concourse-infra/`

Infrastructure CI locale Kind K8s répliquant l'environnement entreprise.

| Service | Namespace | Port/NodePort | Version entreprise |
|---------|-----------|---------------|-------------------|
| Concourse 7.14.3 web | concourse | ingress concourse.localhost:8088 | 7.14.3 (chart Helm officiel) |
| Concourse worker | Docker host | TSA via NodePort 30222 | Worker containerd hors Kind (sysfs mount impossible) |
| Gitea 1.23 rootless | concourse | NodePort 30300 | Remplace GitLab CE (30x plus léger) |
| registry:2 | concourse | NodePort 30500 | HTTP, pas d'auth |
| SonarQube 25.6 | concourse | NodePort 30900 | 25.9 Community |
| S3Mock | concourse | NodePort 30090 | 3 buckets |
| Kafka 3.8.1 KRaft | dd281-dev | NodePort 30092 | |
| Redis 7.2 | dd281-dev | ClusterIP | |
| bouchon-peam | dd281-dev | ClusterIP | |

**Composants supplémentaires** :
- Chart Helm `sld-ng-local` — compatible interface `sld-ng` 2.58.0
- Bouchon SNOW resource type — check/in/out auto-approve
- Images bouchon poussées dans registry:2 avec mêmes paths qu'Artifactory PE
- Ingress-nginx (installé par `mise ingress-setup`)

#### Commandes mise (concourse-infra)

| Commande | Description |
|----------|-------------|
| `mise stack` | Premier démarrage — 17 étapes + install pipelines (~10 min) |
| `mise start` | Redémarrage matin (après stop) |
| `mise stop` | Arrêt du soir (conserve tout) |
| `mise nuke` | Supprime tout (kind delete cluster + worker + Oracle) |
| `mise status` | État complet (pods, worker, fly, registry, Gitea) |
| `mise keygen` | Génère les clés SSH Concourse (Secret K8s, format PEM) |
| `mise ingress-setup` | Déploie ingress-nginx pour Kind |
| `mise bouchon-peam-load` | Charge bouchon-peam (2.1 GB) dans Kind containerd |
| `mise kubeconfig-update` | Met à jour kubeconfig dans credentials-local.yml (--internal) |
| `mise gitea-create-admin` | Crée l'utilisateur admin Gitea dans le pod |
| `mise worker-start/stop/restart/logs` | Gestion du worker Docker host |
| `mise registry-portforward` | Port-forward localhost:8082 → registry:5000 |

Scripts externalisés (éviter signaux dans mise sh) :
- `scripts/nuke.sh`, `scripts/stop.sh` — pkill port-forwards sans crash mise
- `scripts/registry-portforward.sh` — nohup/setsid port-forward
- `scripts/gitea-push.sh` — création repos + push vers Gitea

#### Credential manager K8s

```
CONCOURSE_KUBERNETES_IN_CLUSTER=true
CONCOURSE_KUBERNETES_NAMESPACE_PREFIX=concourse-
```

Le web Concourse lit les secrets K8s dans le namespace `concourse-main` (team `main`). Les variables `(())` dans les **task files** sont résolues par ce credential manager (pas par les `-l` files qui ne s'appliquent qu'aux YAML pipeline). Exemple : le secret `concourse-main/docker-mirror` expose `((docker-mirror))` dans toutes les tasks.

**RBAC** : le ServiceAccount `concourse` a besoin d'un ClusterRole pour lire les secrets dans les namespaces `concourse-*` et créer/supprimer des namespaces, Jobs, et autres resources K8s pour les déploiements E2E.

#### Registry mirrors pour buildkit

Les tasks OCI build (`concourse/oci-build-task-pe`) utilisent deux variables pour configurer buildkit :
- `REGISTRY_MIRRORS` — URL du registry mirror (ex: `http://172.19.0.2:30500`)
- `BUILDKIT_EXTRA_CONFIG` — configuration buildkit supplémentaire (insecure registries, etc.)

Ces variables sont résolues via le credential manager K8s, pas via `-l`.

#### E2E local — architecture

L'environnement E2E déploie **tout** dans un namespace éphémère `dd281-e2e` :
1. `deploy-tiers-e2e.yml` : Kafka 3.8.1, S3Mock 3.12.0, Redis 7.2, bouchon-peam (ClusterIP intra-namespace, pas de NodePort)
2. `deploy-oracle-e2e.yml` : Oracle 19c + Flyway V1-V23 (migrations au démarrage)
3. Helm deploy app (Quarkus + Angular) — les tiers sont joignables par nom DNS simple (`kafka:9092`, `s3mock:9090`, `oracle:1521`)
4. Le namespace entier est détruit après les tests

Les tests Behave s'exécutent en tant que **K8s Job** dans le même namespace (`-D env=e2e` charge le dataset `environments.yaml`). Les containers containerd du worker Concourse ne peuvent pas atteindre le réseau Kind → Job K8s obligatoire. L'app est exposée via ingress path-based.

**Env vars Quarkus named datasource** : les variables d'environnement pour une datasource nommée utilisent le double underscore (`QUARKUS_DATASOURCE__DB_DD281__JDBC_URL`, `QUARKUS_DATASOURCE__DB_DD281__USERNAME`, etc.) — le double underscore encode le point dans le nom `db-dd281`.

---

### concourse-pipelines (SERA porté en entreprise)

**Path** : `/home/jd/pseudo/concourse-pipelines/`

#### 3 Pipelines

| Pipeline | Jobs | Flow |
|----------|:----:|------|
| **Quarkus** | 13 | build → image → **E2E** → tag-rc → TIS → VA → **changement** → PROD → tag-v → VACPP → PRI |
| **Angular** | 12 | build → image → **E2E** → tag-rc → TIS → VA → PROD → tag-v → VACPP → PRI |
| **Oracle** | 10 | build → **E2E** → tag-rc → flyway-tis → flyway-va → **dryrun** → **changement** → flyway-prod → tag-v |

#### 6 Environnements (namespaces Kind)

| Env | Namespace | Scope | Spécificité |
|-----|-----------|-------|-------------|
| E2E | `dd281-e2e` | Full stack | Éphémère (détruit après tests) |
| TIS | `dd281-tis` | App only | Premier env stable |
| VA | `dd281-va` | App only | Validation/recette |
| PROD | `dd281-prod` | App only | Après approbation SNOW |
| VACPP | `dd281-vacpp` | App only | Post-prod validation |
| PRI | `dd281-pri` | App only | Monitoring post-déploiement |

#### Patterns clés

- **credentials-local.yml** — toutes les variables `(())` (credentials, URIs, paths) centralisées dans un fichier passé en `-l` au `fly set-pipeline`. En entreprise, supprimer le `-l` et le credential manager K8s Conjur résout nativement les mêmes `(())`. Les `-l` files ne servent qu'aux YAML pipeline ; les task files lisent les variables via le credential manager K8s (`CONCOURSE_KUBERNETES_IN_CLUSTER=true`, prefix `concourse-`, secrets dans le namespace `concourse-main`)
- **docker-mirror** — K8s secret `concourse-main/docker-mirror` (tiret, pas underscore), résout `((docker-mirror))` dans les task files (`""` en local, `docker_yucaecorce.registre/` en entreprise). Pas dans `-l` car les tasks n'ont pas accès aux `-l` files
- **teams_tasks_path** — variable `((teams_tasks_path))` pointe vers les tasks teams (`pipelines/tasks/teams` en local, `tasks-all-in-one/secret/teams` en entreprise)
- **chart_path** — variable `((chart_path))` pointe vers le chart Helm (`charts/sld-ng-local` en local, `helm-dev-virtual/sld-ng --version 2.58.0` en entreprise)
- **RC/V tags** — versioning sémantique via scripts bash (pas concourse-git-semver-tag)
- **SNOW** — iams.yml + payload builder + put: création + get: approbation + put: clôture
- **Teams** — format tasks-all-in-one (mêmes noms, mêmes params)
- **Reports S3** — Allure + OWASP + Behave, `ensure: try:` sur build/E2E/TIS
- **Helm** — base.yml + env-{e2e,tis,va,prod,vacpp,pri}.yml
- **GitLab SSH** — `check_every: never` + `webhook_token`

#### Portage entreprise

**0 modification pipeline** : supprimer `-l credentials-local.yml` du `fly set-pipeline`. Toutes les `(())` sont résolues par le credential manager K8s Conjur nativement. Les task files lisent `((docker-mirror))` et autres variables depuis les secrets K8s (namespace `concourse-main`, prefix `concourse-`).

**Manuel** (3 actions restantes, hors pipeline YAML) :

| # | Action | Détail |
|---|--------|--------|
| 1 | `helm-values/` URLs | Remplacer URLs locales (`172.19.0.2:*`, `*.svc.cluster.local`) par URLs PE internes. Fichiers lus par helm, pas interpolés par Concourse |
| 2 | `private_key` | Ajouter `private_key: ((gitlab.cle_privee))` dans la section `source:` de chaque resource git (passage HTTP → SSH) |
| 3 | Resource `tasks-all-in-one` | Ajouter une resource git `tasks-all-in-one` + `get:` dans les steps qui utilisent les tasks teams |

---

## Agent Harness — accès programmatique

L'agent harness (`copilot-gemma4/agent-harness`) expose 3 outils Concourse
activables via le profil `ops.yaml` (`ops_tools.concourse.enabled: true`) :

| Outil | Usage |
|-------|-------|
| `concourse_pipelines()` | Lister les pipelines du team |
| `concourse_builds(pipeline, job)` | Builds récents d'un pipeline/job |
| `concourse_build_logs(pipeline, job, build_id)` | Logs SSE d'un build |

Prérequis : `CONCOURSE_TOKEN` en variable d'environnement.

```bash
# Lancer l'agent ops avec Concourse
CONCOURSE_TOKEN=xxx mise run agent:coding -- "Quel est le dernier build du pipeline quarkus ?" ~/projet
```

Code source : `agent-harness/src/harness/tools/concourse.py`
