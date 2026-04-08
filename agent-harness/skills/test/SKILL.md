# Skill — test (Docker Compose + Behave + Playwright)

## Vue d'ensemble

Orchestration Docker Compose pour l'environnement de test local (Quarkus + Oracle + Kafka + S3 + Redis + bouchon-peam).
Tests automatisés Behave (Playwright sync API integre pour le frontend).

**Repo** : `pollinisationnalistements-test`

---

## Services actifs (7)

| Service | Image | Port | Rôle |
|---------|-------|------|------|
| `<app>-base` | Build `../base` | 1521 | Oracle 19c + Flyway schemas |
| `<app>` | `<app>:latest` | 8077 | App Quarkus principale |
| `zp576-angular` | Build `../angular` | 4200 | Frontend Angular 15 / Apache httpd |
| `s3-mock` | `adobe/s3mock:latest` | 9090 | Mock S3 |
| `kafka` | `apache/kafka:latest` | 9092 | Broker Kafka (single-node) |
| `redis` | `redis:7-alpine` | 6379 | Cache |
| `bouchon-peam` | `automateam/bouchon-peam:latest` | 9012 | Mock OpenAM (OAuth implicit via iframe) |

Tous en `network_mode: host`.

## Services désactivés (commentés)

| Service | Raison |
|---------|--------|
| `rabbitmq` | Remplacé par Kafka |
| `crem` | Non requis pour les tests locaux |
| `magateway` | API Gateway non requise |

---

## Images bouchon

Les images bouchon (npm-configuration, pe-maven, maven-configuration, pe-apache-httpd) sont pré-construites et disponibles dans le registry:2 K8s local. `mise stack` utilise les défauts entreprise. `bouchon-artifactory` a été supprimé de la stack : pe-maven est fat (embarque ~/.m2) et l'authent npm est servie en tarball.

---

## Oracle healthcheck

Le healthcheck Docker vérifie que la table de la dernière migration Flyway (V23) est accessible :

```yaml
healthcheck:
  test: ["CMD-SHELL", "echo 'SELECT 1 FROM DD281_INIT_FCT WHERE ROWNUM=1;' | sqlplus -s ... | grep -q ORA- && exit 1 || exit 0"]
  interval: 10s
  retries: 60
  start_period: 30s
```

Cela garantit que le listener Oracle connaît le service ET que Flyway a terminé les migrations avant que Quarkus ne démarre.

---

## Authentification dans les tests

La vraie `@pe-commons/authent` charge bouchon-peam dans une **iframe** :
1. Playwright/Behave navigue vers `/login`
2. `PeAuthComponent` ouvre une iframe vers `http://localhost:9012/connexion/oauth2/authorize`
3. bouchon-peam affiche une page avec 4 users clickables (Alice, Bob, Kira, Mock)
4. Les tests cliquent "Mock" (agent PEAMA, uid=TNAN1234) **dans l'iframe**
5. bouchon-peam redirige avec `#id_token=...&access_token=...`
6. `onConnect` décode le JWT → `sessionStorage['user'] = "TNAN1234"`
7. `PeAuthService.isConnected()` retourne `true` → guard laisse passer

**Important** : la navigation entre pages protégées doit se faire via **clic sur les liens Angular** (`routerLink`), pas via `page.goto()` qui ferait un reload et perdrait l'état auth en mémoire.

---

## Séquence de démarrage

```
base (healthy: DD281_INIT_FCT accessible) ──┐
s3-mock (healthy: wget localhost:9090) ─────┤
redis (healthy: redis-cli ping) ────────────┼──→ app Quarkus
kafka (healthy: topics créés) ──────────────┘
bouchon-peam (started) ────────────────────────→ Angular (depends_on)
```

---

## Polling Kafka (timeout)

Après un restart (quarkus:dev ↔ container), les consumers Kafka ont besoin de temps pour le rebalance du consumer group :

```python
POLL_RETRIES = 60   # 60 × 2s = 120s
POLL_INTERVAL = 2
```

120s est suffisant même pour le dernier consumer (ret_ae) après un restart.

---

## Commandes mise

### Build et démarrage

```bash
mise stack              # Build et démarrage de la stack complète
```

### Tests

```bash
mise test             # Behave (30 scénarios)
```

### Setup auto

```bash
mise setup-behave      # venv + pip install + playwright install chromium
mise check-prereqs     # Vérifie docker, compose v2, curl, git (python/node gérés par mise)
```

`test` appelle automatiquement `setup-behave`.

### Fresh (nettoyage complet)

```bash
mise fresh              # Supprime tout : containers + volumes + images + process dev
```

### Nuke (from scratch)

```bash
mise nuke               # fresh + stack + test + onboarding
```

### Dev replacement

```bash
mise dev-dd281              # Remplace container par mvn quarkus:dev
mise dev-zp576              # Remplace container par ng serve (extrait node_modules depuis Docker si absent)
mise box-dd281              # Rebuild + retour au container Quarkus
mise box-zp576              # Rebuild + retour au container Angular
```

### Aide

```bash
mise aide               # Affiche l'aide complète
```

### Onboarding (4 phases)

```bash
mise onboarding   # Phase 1: Full Docker → Phase 2: Dev Quarkus → Phase 3: Dev Angular → Phase 4: Retour Docker
```

---

## Choix techniques

- **Oracle healthcheck custom** : `SELECT 1 FROM DD281_INIT_FCT` (vérifie Flyway V23 complet, pas juste le listener)
- **Bouchon-peam iframe** : la vraie lib auth charge OpenAM dans une iframe. Les tests cliquent dans l'iframe pour compléter le flow OAuth
- **`mise nuke`** : from scratch to onboarding en une commande
- **check-prereqs** : vérifie toutes les dépendances avec versions minimales avant de lancer quoi que ce soit
- **Polling BDD 60s** : requête directe en base (pas de log Docker) — fiable en container et en dev
- **Navigation router links** : tests E2E naviguent via clic sur `routerLink` (pas `page.goto`) pour préserver l'état auth en mémoire
- **Profil Quarkus `%dev`** : même config Docker Compose et `mvn quarkus:dev`, zéro duplication
- **Datasets par environnement** : `environments.yaml` définit les URLs pour chaque env (compose, e2e, tis, va). Sélection via `behave -D env=compose`. Hiérarchie : `-D key=value` individuel > dataset > défauts compose. Les steps utilisent des fonctions context-aware (`_backend(context)`, `_s3_url(context)`, `_frontend(context)`)
- **`.feature` agnostiques** : les steps infra/Kafka/frontend lisent les URLs depuis context, jamais depuis les paramètres Gherkin. Les `.feature` restent lisibles sans détail technique d'URL
- **before_scenario docker logs** : `try/except` autour de `docker logs` pour compatibilité K8s Job (pas de Docker disponible dans un Job K8s)
- **E2E Concourse** : Behave s'exécute en tant que K8s Job dans le namespace E2E (git clone depuis Gitea, `-D env=e2e`, polling du status Job). Tous les tiers (Kafka, S3Mock, Redis, bouchon-peam) sont déployés dans le même namespace éphémère via `deploy-tiers-e2e.yml` (ClusterIP intra-namespace, pas de NodePort)

---

## Ressources

| Service | CPU (limit) | RAM (limit) |
|---------|-------------|-------------|
| base | 2 | 3G |
| app | 2 | 2G |
| kafka | 1 | 1G |
| s3-mock | 0.5 | 256M |
| angular | 0.5 | 256M |
| **Total** | **~6** | **~6.5G** |
