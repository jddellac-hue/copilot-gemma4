# Skill — base (Oracle Docker)

## Vue d'ensemble

Image Docker Oracle 19c EE avec migrations Flyway. Fournit la base de données locale pour le développement et les tests d'intégration.

**Image de base** : `pe/oracle/database:19.17.1-ee-we8`
**Connexion** : `jdbc:oracle:thin:@//localhost:1521/<schema>`

---

## Structure

```
<repo-base>/
├── Dockerfile                      ← multi-stage : copy scripts + Flyway driver (chmod +x oracle.docker.sh)
├── oracle.docker.sh                ← init scripts (organise sql, strip tablespace, copie PE procs) — doit être exécutable
├── sql/                            ← Flyway migrations projet (V1_1 → V1_9, V20 → V23 + afterMigrate.sql)
├── flyway/
│   ├── conf/flyway.conf            ← baselineOnMigrate=true, validateOnMigrate=true
│   └── drivers/ojdbc8.jar          ← driver Oracle JDBC 8
└── bouchons/
    ├── BDD-OPEN.sat-scripts/       ← ~240 scripts PE (delivery, install, refresh, security)
    ├── sldng-crem-ddl/             ← DDL CREM (30+ migrations)
    ├── sldng-jee-ddl/              ← DDL JEE batch (JOBINSTANCEDATA, CHECKPOINTDATA…)
    ├── sldng-quartz-ddl/           ← DDL Quartz scheduler (qrtz_* tables)
    └── modeles-k8s-oracledb/       ← 6 scripts init K8s (XA, rôles, schemas, Flyway, data)
```

---

## Schemas créés

| Schema | Rôle |
|--------|------|
| `l<code>00` | Schéma applicatif (tables projet, migrations Flyway) |
| `l<code>tc` | CREM technique (routage messages) |
| `l<code>te` | CREM technique (env test) |
| `l<code>tq` | Quartz scheduler |
| `l<code>tj` | JEE batch framework |

---

## Tables principales (schéma applicatif)

| Table | Rôle |
|-------|------|
| `DETAIL_EMISSION_VU_*` | Détail émission (vue FT / prestataire) |
| `DETAIL_RETOUR_VU_*` | Détail retour (vue prestataire) |
| `BINETTE_EMISSION` | Écarts émission |
| `BINETTE_RETOUR` | Écarts retour |
| `SUIVI_FACONNIER` | Suivi prestataire |
| `RETOUR_FACONNIER_FLUX` | Retour prestataire flux |
| `PLI` | Pli (document/courrier) |

---

## Migrations Flyway

| Version | Description |
|---------|-------------|
| V1_1 | Création schéma initial |
| V1_2 | Modif detail écart prestataire |
| V1_3 | Modif écart retour + detail emission |
| V1_4 | Modif écart emission (CHECK→CONTROL) |
| V1_5 | Index detail retour vu prestataire |
| V1_6 | Ajout indexes haute fréquence |
| V1_7 | Fix taille colonne motif_rejet (100→4000) |
| V1_8 | Taille colonne archive (10→30) |
| V1_9 | Découpage JSON (ajout colonnes) |
| V20 | Tables TIM (InitLot, ListeLot, ListeDoc, ListePli) |
| V21 | Tables RET_BS (InitBS, BSPrimaire) |
| V22 | Tables de référence |
| V23 | Tables RET_AE (InitFct, FctPrimaire, Pas) |

**Note** : `afterMigrate.sql` contient des procs PL/SQL (`pe_ajout_synonymes_tout_cc`, `pe_ajout_azotes_*`) qui peuvent échouer avec exit code 1 si les procs ne sont pas déclarées — non bloquant pour les tests (les tables sont créées).

---

## Dockerfile

Le `Dockerfile` fait `chmod +x oracle.docker.sh` avant le `RUN` car le bit exécutable peut être perdu sur les postes entreprise (`git core.fileMode=false` sur CIFS/Windows).

---

## Démarrage

```bash
# Via docker-compose (depuis le repo test)
docker compose up <service-base>
# ~90s au premier démarrage (création schemas + Flyway)
# Container healthy quand Oracle est prêt
```

Mémoire recommandée : 3 GB.
