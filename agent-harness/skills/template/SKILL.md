# Skill — template (Cookiecutter Python Streamlit)

## Vue d'ensemble

Template Cookiecutter Python pour applications Streamlit connectées à S3, déployables sur Kubernetes via Concourse CI.

**Langage** : Python 3.12.6
**Framework** : Streamlit (port 8501)
**Package manager** : `uv` (Astral, Rust-based)

---

## Structure

```
<repo-template>/
├── cookiecutter.json                    ← Variables template (equipe, code_composant…)
├── Makefile                             ← Commandes haut-niveau
├── README.md / CONTRIBUTING.md
└── {{cookiecutter.code_composant + "-" + cookiecutter.nom_composant}}/
    ├── pyproject.toml                   ← Deps (streamlit, ruff, pytest, boto3…)
    ├── Dockerfile                       ← Multi-stage : uv → python slim
    ├── Makefile                         ← 252 lignes (setup, build, test, lint, deploy, pipeline)
    ├── .pre-commit-config.yaml          ← ruff + pytest automatiques
    ├── ci/
    │   ├── pipeline.yaml                ← Pipeline Concourse master (6 jobs)
    │   ├── pipeline_current_branch.yaml ← Pipeline feature branch (3 jobs)
    │   ├── vars.yaml
    │   └── tasks/                       ← 12 tasks (build, test, deploy, tag…)
    └── deployments/
        ├── base/                        ← K8s manifests (deployment, cronjob, ingress, secrets…)
        └── overlays/                    ← z6-dev, z6-dev-individuel, z6-preprod, z6-prod-mop
```

---

## Stack technique

| Composant | Technologie |
|-----------|------------|
| App | Streamlit (web UI data) |
| Package manager | `uv` (Rust-based, ultra-fast) |
| Qualité | `ruff` (lint+format), `bandit` (sécurité), `pip-audit` |
| Tests | `pytest` + `pytest-cov`, `moto` (mock AWS), `freezegun` |
| Pre-commit | ruff check + format + pytest avant chaque commit |
| CI/CD | Concourse (pipeline master + feature branch) |
| Container | Docker multi-stage (uv build → python slim runtime) |
| Déploiement | K8s/Kustomize (4 envs) |
| Secrets | Conjur → ExternalSecrets K8s → env vars pod |
| Stockage | S3 (buckets FAB/PROD) |

---

## Architecture applicative

```
main.py → dispatch selon JOB_NAME
  └→ AFFICHAGE → streamlit run streamlit_display.py
       └→ S3Connector → load parquet → st.dataframe()
```

- **Config** : env vars (S3 name, secret, endpoint)
- **Logging** : JSON sur stdout + Parquet sur S3 (double persistance)

---

## Environnements K8s

| Overlay | Usage |
|---------|-------|
| `z6-dev` | Développement |
| `z6-dev-individuel` | Namespace dédié par développeur |
| `z6-preprod` | Pré-production |
| `z6-prod-mop` | Production |

---

## Pipeline Concourse

```
git push master → [install-pipeline] → [construction-livrable] (pytest + tag RC + Docker)
  → [deploy-preprod] (manuel) → [creation-version-prod] (tag V + Docker)
    → [deploy-prod] (manuel)
```

---

## Commandes développeur

```bash
# Générer un nouveau projet
uvx cookiecutter ssh://git@<gitlab>/template.git

# Dans le projet généré
make setup          # venv + deps + pre-commit
make lint           # ruff check + format
make test           # pytest
make build && run   # Docker local
make deploy         # kubectl apply (namespace individuel)
```
