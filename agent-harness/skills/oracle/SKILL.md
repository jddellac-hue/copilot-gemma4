# Skill -- Oracle Database, GoldenGate & PL/SQL

> Connaissances Oracle accumulees lors du projet OGG Stock Refresh
> et bonnes pratiques generales Oracle DBA / GoldenGate.
> Source projet : https://github.com/jddellac-hue/ogg-stock-refresh (prive)
> Derniere mise a jour : 09/03/2026

---

## 1. Oracle Database -- Fondamentaux

### Architecture CDB/PDB
- CDB (Container Database) = root + seed + PDBs
- PDB (Pluggable Database) = base logique isolee, apparait comme une non-CDB pour les clients Oracle Net
- CON_ID=0 : non-CDB (base classique, pas de container)
- CON_ID=1 : CDB$ROOT (racine du container)
- CON_ID=3 : premier PDB (ex: PDB0, XEPDB1)
- `ALTER SESSION SET CONTAINER = PDB0;` pour travailler dans un PDB
- Certaines commandes sont CDB-only : `ALTER SYSTEM SWITCH LOGFILE`, `ALTER SYSTEM CHECKPOINT`
- Piege ORA-65040 : executer SWITCH LOGFILE depuis un PDB → erreur "operation not allowed from within a pluggable database"
  - Fix : se connecter au CDB root (`/ as sysdba` sans `ALTER SESSION SET CONTAINER`)
- Piege : creer des utilisateurs ou objets applicatifs dans CDB$ROOT au lieu du PDB cible
- Common users (prefix `C##`) : visibles dans tous les PDBs ; local users : confines a un seul PDB
- Verifier le container courant : `SELECT SYS_CONTEXT('USERENV','CON_NAME') FROM DUAL;`
- Lister les PDBs : `SELECT CON_ID, NAME, OPEN_MODE FROM V$PDBS;`

### ARCHIVELOG
- Mode requis pour toute replication (OGG, DataGuard) et pour RMAN point-in-time recovery
- Verifier : `SELECT LOG_MODE FROM V$DATABASE;` (doit retourner ARCHIVELOG)
- Activer : `SHUTDOWN IMMEDIATE; STARTUP MOUNT; ALTER DATABASE ARCHIVELOG; ALTER DATABASE OPEN;`
- Les archived redo logs consomment de l'espace dans la FRA -- surveiller en continu

### FORCE_LOGGING
- Garantit que TOUS les DML generent du redo, meme avec NOLOGGING ou hints `/*+ APPEND */`
- Critique pour DataGuard et GoldenGate (sinon les donnees NOLOGGING ne sont pas repliquees)
- Sans FORCE_LOGGING, un `INSERT /*+ APPEND */ INTO ... NOLOGGING` ne genere pas de redo → perte silencieuse en standby/OGG
- Verifier : `SELECT FORCE_LOGGING FROM V$DATABASE;`
- Activer : `ALTER DATABASE FORCE LOGGING;`
- Piege : FORCE_LOGGING + gros batch = generation massive de redo → saturation rapide de la FRA

### FRA (Fast Recovery Area)
- Stocke les archivelogs, backups RMAN, flashback logs
- Surveiller l'espace **non reclaimable** (pas juste le % utilise -- Oracle reclame automatiquement a ~80%)
- Si l'espace non reclaimable depasse ~80%, action requise (la DB ne peut plus purger seule)
- Si saturee → DB s'arrete (impossible d'ecrire les archivelogs)
- Verifier :
```sql
SELECT ROUND((SPACE_LIMIT-SPACE_USED)/1073741824,1) FREE_GO,
       ROUND(SPACE_USED*100/SPACE_LIMIT,1) PCT_USED
FROM V$RECOVERY_FILE_DEST;
```
- Nettoyer :
```bash
rman target /
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> DELETE NOPROMPT EXPIRED ARCHIVELOG ALL;
RMAN> DELETE NOPROMPT ARCHIVELOG ALL COMPLETED BEFORE 'SYSDATE-7';
```
- Bonne pratique : placer la FRA sur un disque separe des datafiles
- Bonne pratique : stocker les backups RMAN hors FRA si possible

### Supplemental Logging
- Requis pour OGG (LogMiner) : `ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;`
- **Minimal** : lie les redo operations aux DML (requis pour LogMiner et OGG)
- **ALL COLUMNS** : capture toutes les colonnes dans le redo (pas seulement les modifiees)
  - Activer par table : `ALTER TABLE schema.table ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;`
  - ALL COLUMNS requis par GoldenGate pour les UPDATEs quand HANDLECOLLISIONS est actif (sinon impossible de reconstituer la ligne pour l'INSERT de substitution)
  - Overhead significatif sur le volume de redo genere
  - Desactiver ALL COLUMNS quand HANDLECOLLISIONS est retire (revenir a SCHEDULINGCOLS)
- Verifier niveau DB : `SELECT SUPPLEMENTAL_LOG_DATA_MIN FROM V$DATABASE;` (doit etre YES)
- Verifier par table : `SELECT LOG_GROUP_NAME, TABLE_NAME FROM DBA_LOG_GROUPS WHERE OWNER = 'SCHEMA';`

### enable_goldengate_replication
- Parametre systeme requis pour OGG : `ALTER SYSTEM SET enable_goldengate_replication=TRUE SCOPE=BOTH;`
- Doit etre active sur source ET cible
- Sans ce parametre, les processus OGG ne peuvent pas fonctionner
- Verifier : `SHOW PARAMETER enable_goldengate_replication;`

### DataGuard / FSFO
- **MAXIMUM AVAILABILITY** : chaque commit attend l'acquittement du standby → performance degradee pour les batch
- **MAXIMUM PERFORMANCE** : pas d'attente standby → risque de perte de donnees en cas de failover
- **FSFO (Fast-Start Failover)** : failover automatique, seuil configurable (ex: 30s)
  - Observer : processus dedie surveillant la connectivite (ex: so00214044/sozk04)
  - Piege : operations longues (IMPDP, gros batch) peuvent declencher un failover si elles bloquent la synchronisation au-dela du seuil
- Verifier le mode : `SELECT PROTECTION_MODE, PROTECTION_LEVEL FROM V$DATABASE;`

### Tablespace monitoring
```sql
SELECT df.TABLESPACE_NAME,
       ROUND(df.TOTAL/1024) TOTAL_GO,
       ROUND(NVL(fs.FREE,0)/1024) FREE_GO,
       ROUND((df.TOTAL - NVL(fs.FREE,0))*100/NULLIF(df.TOTAL,0),1) PCT_USED
FROM (SELECT TABLESPACE_NAME, SUM(BYTES)/1048576 TOTAL
      FROM DBA_DATA_FILES GROUP BY TABLESPACE_NAME) df
LEFT JOIN (SELECT TABLESPACE_NAME, SUM(BYTES)/1048576 FREE
           FROM DBA_FREE_SPACE GROUP BY TABLESPACE_NAME) fs
ON df.TABLESPACE_NAME = fs.TABLESPACE_NAME;
```
- Piege BUG-3 : jointure directe `DBA_DATA_FILES x DBA_FREE_SPACE` sans pre-aggregation → produit cartesien avec valeurs multipliees (814 000 Go affiches au lieu de 814 Go)

---

## 2. Oracle GoldenGate

### Architecture
- **Manager** : processus superviseur, gere le demarrage/arret des autres processus, purge des trails
  - `MINKEEPDAYS` : retention minimum des trail files (recommandation >= 7 jours pendant les operations de refresh)
  - Trop bas → les trails sont purges avant que le Replicat les traite
  - Recharger apres modification : `SEND MANAGER RELOAD`
  - Ports : 13000 (source), 13100 (cible) -- convention projet
- **Extract** (source) : capture les changements depuis les redo logs
  - **Integrated Capture** : utilise LogMiner (Oracle API), supporte CDB/PDB, parallelisme natif
  - **Classic Capture** : lit directement les redo logs (plus rapide en debit, pas de support CDB natif)
  - Integrated est le mode recommande depuis Oracle 12c
  - Enregistrer avant le demarrage : `REGISTER EXTRACT <name> DATABASE CONTAINER (<pdb>)`
- **Trail files** : fichiers binaires de changements (stockage intermediaire)
  - Repertoire : `dirdat/`
  - Nommage : prefixe 2 lettres + sequence (ex: `ex000000000`, `ex000000001`)
  - Taille configurable (defaut 500 MB en Enterprise)
- **Replicat** (cible) : applique les changements sur la base cible
  - **Integrated Replicat** : utilise l'API Oracle Apply (parallelisme, gestion de conflits)
  - **Classic Replicat** : execute directement les DML (plus simple, suffisant pour la plupart des cas)
  - Checkpoint table : enregistre la position du Replicat dans les trails

### Integrated Extract et LogMiner
- LogMiner a un `streaming_duration` de 60s par defaut
- Signifie : les changements sont captures par lots de ~60s (latence incompressible)
- `ALTER SYSTEM SWITCH LOGFILE` force LogMiner a traiter immediatement le redo courant → reduit la latence a ~10s
- `ALTER SYSTEM CHECKPOINT` pour flush des dirty blocks
- SWITCH LOGFILE doit etre au niveau CDB (pas PDB → ORA-65040)
- `TRANLOGOPTIONS INTEGRATEDPARAMS (streaming_duration N)` permet de tuner la duree en OGG Enterprise
- MAIS NON supporte en OGG Free 23.5 → ABEND OGG-10141
- Bonne pratique : executer SWITCH LOGFILE + CHECKPOINT apres chaque batch DML important pour accelerer la capture

### HANDLECOLLISIONS
- Convertit les erreurs de duplication/absence en operations de reconciliation :
  - UPDATE sur ligne absente → INSERT (si supplemental logging ALL COLUMNS actif)
  - INSERT sur ligne existante → UPDATE
  - DELETE sur ligne absente → ignore silencieusement
- Supplemental logging ALL COLUMNS requis pour que la conversion UPDATE→INSERT fonctionne
- Utile pendant les phases de resynchronisation (refresh stock, initial load)
- **NE DEVRAIT PAS rester permanent en production** :
  - Masque les erreurs reelles de coherence
  - Pas d'alerte sur les incidences → les problemes s'accumulent silencieusement
  - Overhead performance : necessite ALL COLUMNS supplemental logging en permanence
- Bonne pratique : activer uniquement pendant l'operation, retirer des que source et cible sont synchronisees
- Bonne pratique : appliquer selectivement par table (`MAP ... HANDLECOLLISIONS`) plutot que globalement
- Si HANDLECOLLISIONS est permanent → ouvrir un ticket pour investigation et retrait

### ATCSN (AT Checkpoint SCN)
- `START REPLICAT RRSO0850, ATCSN <SCN>` -- repositionne le Replicat a un SCN specifique
- Usage : apres TRUNCATE+IMPDP pour resynchroniser depuis le SCN de l'export
- Non supporte via REST API → utiliser ggsci ou adminclient CLI obligatoire

### TRANLOGOPTIONS INTEGRATEDPARAMS
- `TRANLOGOPTIONS INTEGRATEDPARAMS (streaming_duration N)` : permet de tuner la duree de streaming en OGG Enterprise
- NON supporte en OGG Free 23.5 → ABEND OGG-10141
- Workaround : utiliser `ALTER SYSTEM SWITCH LOGFILE` pour forcer le flush

### Checkpoint management
- Fichier CPR : position du Replicat dans les trail files (`dirchk/`)
- **TOUJOURS sauvegarder AVANT toute operation** :
```bash
cp $OGG_HOME/dirchk/RRSO0850.cpr /tmp/RRSO0850_pre_refresh_$(date +%Y%m%d_%H%M%S).cpr
```
- Permet de rollback le Replicat a son ancienne position si l'operation echoue

### MINKEEPDAYS
- Retention minimum des trail files dans `dirdat/`
- Valeur trop basse → trails purges par le Manager avant que le Replicat les traite
- Augmenter a >= 7 avant toute operation de refresh
- Modifier dans `mgr.prm` puis `SEND MANAGER RELOAD`

### REST API vs adminclient
| Operation | REST API | adminclient/ggsci |
|-----------|----------|------------------|
| Status/Info | Oui | Oui |
| Start/Stop | Oui | Oui |
| ATCSN | Non | Oui (obligatoire) |
| REGISTER EXTRACT | Non | Oui (obligatoire) |
| SEND MANAGER | Non | Oui |
| STATS | Partiel | Complet |

### OGG Free 23ai
- Mot de passe fort obligatoire : majuscule + minuscule + chiffre + caractere special (ex: `Ogg-Test01`)
- `TRANLOGOPTIONS INTEGRATEDPARAMS` non supporte → ABEND OGG-10141
- REST API limitee (pas d'ATCSN)
- Gratuit (vs Enterprise payant avec licence)
- Support communaute (pas de support Oracle officiel)

### Convergence monitoring
- **Lag OGG = 0 n'est PAS la convergence** : lag=0 peut etre affiche avant meme que les changements soient captures par LogMiner (extraction n'a pas encore commence)
- Methode fiable : polling SQL sur les donnees cible (row-count, pas metadonnees OGG)
```sql
-- Compter les lignes avec le timestamp de refresh sur la cible
SELECT COUNT(*) FROM schema.table
WHERE TMST_SOURCE = TO_TIMESTAMP('2026-03-09 10:30:00', 'YYYY-MM-DD HH24:MI:SS');
```
- Attendre que count cible == count source pour confirmer la convergence
- Timeout recommande : 30-120s selon le volume et la latence LogMiner

### Ne jamais confondre les processus
- RRSO0850 et RPSO0850 sont des pipelines differents
- Toujours verifier le nom exact du processus avant toute operation ggsci
- `INFO ALL` pour lister tous les processus actifs

### REPORTCOUNT et REPERROR
- `REPORTCOUNT EVERY 15 MINUTES, RATE` : statistiques de traitement dans le fichier rapport (.rpt) a intervalle regulier
- `REPERROR (DEFAULT, ABEND)` : force le Replicat a s'arreter immediatement sur une erreur de donnees (recommande hors HANDLECOLLISIONS)

### OGG_NOOP pattern (testing)
- Pour les tests Docker : definir des fonctions shell qui remplacent ggsci par des no-ops
- Permet de tester la logique des scripts shell sans OGG reel
- Toutes les fonctions ggsci (start, stop, info, stats) deviennent des no-ops retournant des valeurs simulees

---

## 3. PL/SQL -- Patterns

### BATCH_TOUCH_PARTITION
Procedure de bulk UPDATE par partition avec ROWID et LIMIT batching :
```sql
CREATE OR REPLACE PROCEDURE BATCH_TOUCH_PARTITION(
    p_schema    IN VARCHAR2,
    p_table     IN VARCHAR2,
    p_partition IN VARCHAR2,
    p_col_noop  IN VARCHAR2,
    p_batch     IN NUMBER DEFAULT 10000,
    p_sleep     IN NUMBER DEFAULT 0,
    p_value     IN VARCHAR2 DEFAULT NULL  -- valeur TMST_SOURCE a injecter
) AS
    TYPE t_rowid IS TABLE OF ROWID;
    v_rowids t_rowid;
    v_sql    VARCHAR2(4000);
    v_total  NUMBER := 0;
    v_start  NUMBER := DBMS_UTILITY.GET_TIME;
    CURSOR c IS
        SELECT ROWID FROM <schema>.<table> PARTITION(<partition>);
BEGIN
    IF p_value IS NOT NULL THEN
        v_sql := 'UPDATE ' || p_schema || '.' || p_table
               || ' SET ' || p_col_noop || ' = TO_TIMESTAMP(''' || p_value || ''', ''YYYY-MM-DD HH24:MI:SS'')'
               || ' WHERE ROWID = :rid';
    ELSE
        v_sql := 'UPDATE ' || p_schema || '.' || p_table
               || ' SET ' || p_col_noop || ' = ' || p_col_noop
               || ' WHERE ROWID = :rid';
    END IF;
    OPEN c;
    LOOP
        FETCH c BULK COLLECT INTO v_rowids LIMIT p_batch;
        EXIT WHEN v_rowids.COUNT = 0;
        FORALL i IN 1..v_rowids.COUNT
            EXECUTE IMMEDIATE v_sql USING v_rowids(i);
        COMMIT;
        v_total := v_total + v_rowids.COUNT;
        IF p_sleep > 0 THEN DBMS_LOCK.SLEEP(p_sleep); END IF;
    END LOOP;
    CLOSE c;
    DBMS_OUTPUT.PUT_LINE('BATCH_TOUCH FIN ' || p_table || '.' || p_partition
        || ' : ' || v_total || ' lignes / '
        || ROUND((DBMS_UTILITY.GET_TIME - v_start)/100) || 's');
END;
```

### FORALL...EXECUTE IMMEDIATE avec USING
- `FORALL` pour les DML batch (10-100x plus rapide que boucle row-by-row)
- Reduit les context switches PL/SQL <-> SQL engine (une seule bascule au lieu d'une par ligne)
- Test reel : 100K inserts row-by-row = 4.94s vs FORALL = 0.12s (x41)
- `EXECUTE IMMEDIATE ... USING` pour SQL dynamique avec bind variables (evite le hard-parsing)
- `SAVE EXCEPTIONS` pour continuer malgre les erreurs individuelles et les traiter apres :
```sql
FORALL i IN 1..v_rowids.COUNT SAVE EXCEPTIONS
    EXECUTE IMMEDIATE v_sql USING v_rowids(i);
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -24381 THEN  -- ORA-24381: error(s) in array DML
            FOR j IN 1..SQL%BULK_EXCEPTIONS.COUNT LOOP
                DBMS_OUTPUT.PUT_LINE('Erreur index ' || SQL%BULK_EXCEPTIONS(j).ERROR_INDEX
                    || ' : ' || SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE));
            END LOOP;
        ELSE
            RAISE;
        END IF;
```

### BULK COLLECT ... LIMIT
- Evite la saturation memoire PGA
- Valeur 100 = sweet spot par defaut (Oracle optimise les cursor FOR loop avec cette valeur)
- Valeur 10000 = bon compromis pour les batch lourds (contexte OGG refresh)
- Au-dela de 10000, le gain marginal diminue
- Regle : si >= 4 lignes affectees, bulk SQL apporte un gain significatif

### SYS_REFCURSOR pour iteration dynamique
- Permet d'ouvrir un curseur sur une requete construite dynamiquement
- Utile pour iterer sur les partitions d'une table sans connaitre les noms a l'avance :
```sql
DECLARE
    v_cur SYS_REFCURSOR;
    v_partition_name VARCHAR2(128);
BEGIN
    OPEN v_cur FOR
        'SELECT PARTITION_NAME FROM DBA_TAB_PARTITIONS'
        || ' WHERE TABLE_OWNER = :owner AND TABLE_NAME = :tab'
        || ' ORDER BY PARTITION_NAME'
        USING p_schema, p_table;
    LOOP
        FETCH v_cur INTO v_partition_name;
        EXIT WHEN v_cur%NOTFOUND;
        -- Appeler BATCH_TOUCH_PARTITION pour chaque partition
        BATCH_TOUCH_PARTITION(p_schema, p_table, v_partition_name, p_col_noop, p_batch, p_sleep, p_value);
    END LOOP;
    CLOSE v_cur;
END;
```

### DBMS_OUTPUT pour progress reporting
- `DBMS_OUTPUT.PUT_LINE()` pour afficher la progression des batch longs
- Activer cote client : `SET SERVEROUTPUT ON SIZE UNLIMITED`
- Limitation : la sortie n'apparait qu'apres la fin du bloc PL/SQL (pas en temps reel)
- Alternative temps reel : `DBMS_APPLICATION_INFO.SET_SESSION_LONGOPS` (visible dans `V$SESSION_LONGOPS`)

### DBMS_LOCK.SLEEP pour throttling
- `DBMS_LOCK.SLEEP(p_sleep)` entre les batchs pour eviter la saturation I/O en production
- Parametre optionnel (0 = pas de pause)

### COMMIT par batch
- Limiter la taille des transactions (undo/redo)
- Evite les ORA-01555 "Snapshot too old" sur les longues transactions
- Evite la saturation de l'undo tablespace

---

## 4. Data Pump (EXPDP/IMPDP)

### DIRECTORY object
- Doit exister cote OS ET cote Oracle :
```sql
CREATE OR REPLACE DIRECTORY DUMP_DIR AS '/path/to/dump';
GRANT READ, WRITE ON DIRECTORY DUMP_DIR TO user;
```
- L'utilisateur Oracle OS doit avoir les droits d'ecriture sur le repertoire

### EXPDP (Export)
```bash
expdp user/pass@PDB DIRECTORY=DUMP_DIR \
    DUMPFILE=export_%U.dmp LOGFILE=export.log \
    TABLES=SCHEMA.TABLE1,SCHEMA.TABLE2 \
    PARALLEL=4 COMPRESSION=ALL \
    FLASHBACK_SCN=12345678 \
    CONTENT=DATA_ONLY
```
- **FLASHBACK_SCN** : capturer le SCN AVANT le debut du batch pour garantir un snapshot coherent
  - `SELECT CURRENT_SCN FROM V$DATABASE;` juste avant l'EXPDP
  - Essentiel si la source est active pendant l'export
- **PARALLEL** : ne pas depasser 2x le nombre de CPUs
  - Utiliser `%U` dans DUMPFILE pour permettre plusieurs fichiers (un par worker)
  - Placer les fichiers dump sur des disques separes des tablespaces
- **COMPRESSION=ALL** : reduit la taille des dumps (CPU vs I/O trade-off, generalement favorable)
- **CONTENT=DATA_ONLY** : pour les refresh (schema deja existant sur la cible)

### IMPDP (Import)
```bash
impdp user/pass@PDB DIRECTORY=DUMP_DIR \
    DUMPFILE=export_%U.dmp LOGFILE=import.log \
    REMAP_SCHEMA=SRC_SCHEMA:TGT_SCHEMA \
    TABLE_EXISTS_ACTION=APPEND \
    CONTENT=DATA_ONLY \
    PARALLEL=4
```
- **TABLE_EXISTS_ACTION** :
  - `APPEND` : ajoute aux donnees existantes (utile pour methode B staging)
  - `TRUNCATE` : le plus rapide pour les refresh complets (pas de DROP/CREATE)
- **REMAP_SCHEMA** : obligatoire si les schemas source et cible ont des noms differents

### Pieges IMPDP
- Oracle XE Docker : volumes Docker montes root-owned, oracle (uid 54321) ne peut pas ecrire
  - **Solution definitive** : volume tmpfs avec uid oracle dans docker-compose :
    ```yaml
    volumes:
      ogg-dump-xfer:
        driver: local
        driver_opts:
          type: tmpfs
          device: tmpfs
          o: "uid=54321,gid=54321,mode=0777"
    ```
  - `chmod 777 /dump` dans l'entrypoint echoue car oracle ne peut pas chown/chmod un volume root
  - `user: root` + `chroot --userspec` casse le healthcheck
- Operations longues bloquees par DataGuard en MAX AVAILABILITY
- Pre-allouer le tablespace USERS pour eviter les resize incrementaux lents :
  ```sql
  ALTER DATABASE DATAFILE '/opt/oracle/oradata/XE/XEPDB1/users01.dbf' RESIZE 200M;
  ```

---

## 5. Partitioning

### LIST partitioning
- `PARTITION BY LIST (CODE_DR)` : chaque partition contient les lignes pour un code direction regionale
- Convention de nommage : `TABLE_DR_XX_PART` (ex: `PJ1F_DR_01_PART`, `PJ1F_DR_12_PART`)
- Verifier les partitions :
```sql
SELECT PARTITION_NAME, NUM_ROWS, LAST_ANALYZED
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER = 'X' AND TABLE_NAME = 'Y'
ORDER BY PARTITION_NAME;
```

### EXCHANGE PARTITION
- Swap de metadonnees entre une table et une partition -- operation DDL instantanee (millisecondes)
- Pas de copie de donnees, pas de redo/undo genere
- Micro-interruption uniquement pendant le swap DDL
- Workflow zero-downtime :
  1. Charger les donnees dans une table staging
  2. Construire les index et contraintes sur la staging table AVANT l'exchange
  3. `ALTER TABLE t EXCHANGE PARTITION p WITH TABLE staging;`
- Supporte range, hash, list, et composite partitioning

### TRUNCATE PARTITION
- Plus rapide que DELETE pour vider une partition
- Genere du redo si FORCE_LOGGING est actif
- **TRUNCATE PARTITION avec UPDATE GLOBAL INDEXES** : evite ORA-01502 (index unusable)
```sql
ALTER TABLE schema.table TRUNCATE PARTITION partition_name UPDATE GLOBAL INDEXES;
```
- Sans `UPDATE GLOBAL INDEXES`, les index globaux deviennent UNUSABLE et doivent etre reconstruits manuellement

---

## 6. Docker Test Environment

### Images
- Oracle XE 21c : `gvenzl/oracle-xe:21-slim` (gratuit, communautaire)
- OGG Free 23ai : `container-registry.oracle.com/goldengate/goldengate-free:latest`
- Ports : source 1521, cible 1522, OGG REST API 9443

### Topologie test
```
oracle-source (XE 21c, :1521)  <->  OGG Free 23ai (:9443)  ->  oracle-target (XE 21c, :1522)
      PDB XEPDB1                     Extract -> Trail -> Replicat      PDB XEPDB1
      RSO085J1, RSO085H1              ERCT0010    ex    RRSO0850       RCT00100
```

### Ecarts Dev/Prod -- Factor X (12-Factor Dev/Prod Parity)
| Aspect | Test Docker | Production |
|--------|------------|------------|
| Oracle | XE 21c (limite CPU/RAM/taille) | 19c EE |
| OGG | Free 23ai | Enterprise 19.1/21c |
| Tables | 3 tables, 1800 lignes | 26 tables, ~1 milliard lignes |
| Partitions | 3 LIST ('01','12','13') | 34 LIST (codes DR) |
| Replicat | Classic | Integrated |
| CDB/PDB | Les deux sont CDB+PDB | Source CDB+PDB, cible non-CDB |

Surveiller les differences comportementales entre ces versions. Documenter tout ecart decouvert.

### container-entrypoint.sh
- Oracle XE Docker : utiliser `exec container-entrypoint.sh` (dans le PATH du container)
- Ne PAS utiliser un chemin absolu (ex: `/opt/oracle/scripts/container-entrypoint.sh`) -- le chemin varie selon l'image
- Le script gere l'initialisation de la base, la creation du PDB, et le demarrage du listener

### Volume /dump
- Les volumes Docker sont crees root-owned, oracle (uid 54321) ne peut pas ecrire
- **Solution** : volume tmpfs avec `uid=54321` dans docker-compose (voir section 4. Pieges IMPDP)
- `chmod 777` dans l'init script ne fonctionne PAS car l'init tourne en tant qu'oracle
- `user: root` dans docker-compose casse le healthcheck (qui doit tourner en tant qu'oracle)

### Pieges Docker
- `ALTER SYSTEM SWITCH LOGFILE` depuis PDB → ORA-65040 (utiliser `/ as sysdba` = CDB root)
- OGG healthcheck : accepter HTTP 401 (pas d'auth) comme "healthy"
- `enable_goldengate_replication=TRUE` requis sur source ET cible
- Passage en ARCHIVELOG requis sur la source (redemarrage DB necessaire)
- Mot de passe OGG Free : doit etre fort (`Ogg-Test01` -- maj+min+chiffre+special)

### Tests Docker
```bash
cd tests/docker && sg docker -c "docker compose --profile ogg up -d"
python3 -m pytest tests/ -v
# 68 tests, 68 passent (0 echec) apres fix tmpfs + pre-allocation tablespace
```

---

## 7. Zero-Downtime Refresh (Method C)

### Colonne TMST_SOURCE
- Colonne TIMESTAMP ajoutee sur les tables cible pour le suivi du refresh
- Permet de distinguer les lignes "fraiches" (refresh_ts) des lignes "stale" (ancienne valeur ou NULL)

### Flux complet
1. **Batch touch** : `UPDATE SET TMST_SOURCE = refresh_ts` sur toutes les partitions source
   - Via procedure BATCH_TOUCH_PARTITION (bulk UPDATE par ROWID, LIMIT batching)
   - `DBMS_LOCK.SLEEP` optionnel entre les batchs pour throttling
2. **Log switch** : `ALTER SYSTEM SWITCH LOGFILE` + `ALTER SYSTEM CHECKPOINT` pour accelerer la capture LogMiner (~10s au lieu de ~60s)
3. **Convergence polling** : `COUNT(TMST_SOURCE = refresh_ts)` sur la cible == expected_count
   - Timeout recommande : 30-120s selon le volume
   - Lag OGG n'est PAS un indicateur fiable de convergence
4. **Purge stale** : `DELETE WHERE TMST_SOURCE != refresh_ts` (avec gardes multi-niveaux)

### Gardes avant purge (multi-niveaux)
1. Convergence confirmee (state = OK sur toutes les tables)
2. Counts fresh >= expected pour chaque table
3. Ratio purge < seuil configurable (defaut 50%)
4. Option `--force` pour bypasser le seuil si le ratio est attendu (ex: divergence connue > 50%)

### Avantages
- Le Replicat reste RUNNING tout au long de l'operation -- aucune interruption de service
- Pas de TRUNCATE, pas d'ATCSN, pas de repositionnement de checkpoint
- Compatible avec HANDLECOLLISIONS (les UPDATEs sur lignes absentes en cible sont convertis en INSERT)

---

## 8. Common Pitfalls

### ORA-65040 : SWITCH LOGFILE at PDB level
- `ALTER SYSTEM SWITCH LOGFILE` est une commande CDB-only
- L'executer depuis un PDB → ORA-65040 "operation not allowed from within a pluggable database"
- Fix : se connecter au CDB root (`sqlplus / as sysdba` sans `ALTER SESSION SET CONTAINER`)

### OGG lag=0 is NOT convergence
- Le lag OGG peut afficher 0 avant meme que l'extraction ait commence (pas de changements a capturer = lag 0)
- La convergence se verifie par les donnees (row-count polling), pas par les metadonnees OGG

### HANDLECOLLISIONS permanent en production
- Situation anormale : masque les erreurs de coherence entre source et cible
- Ouvrir un ticket pour investigation et retrait
- Overhead : necessite ALL COLUMNS supplemental logging en permanence

### FRA saturation pendant le refresh
- Les batch DML (touch) generent du redo massif
- Avec FORCE_LOGGING actif, meme les operations NOLOGGING generent du redo
- Surveiller la FRA toutes les 30 minutes pendant les operations de refresh
- Action si < 10 Go libres : `RMAN> DELETE NOPROMPT ARCHIVELOG ALL COMPLETED BEFORE 'SYSDATE-1';`

### MINKEEPDAYS trop bas
- Les trail files sont purges par le Manager avant que le Replicat les traite
- Symptome : le Replicat ABEND car le trail file n'existe plus
- Fix : augmenter MINKEEPDAYS a >= 7 avant toute operation de refresh

### Confusion de processus OGG (RPSO0850 vs RRSO0850)
- Deux pipelines differents peuvent coexister sur la meme instance OGG
- Toujours verifier le nom exact avec `INFO ALL` avant toute operation
- Ne JAMAIS toucher un processus qui n'est pas dans le scope de l'operation

### OGG-10141 (TRANLOGOPTIONS INTEGRATEDPARAMS)
- `TRANLOGOPTIONS INTEGRATEDPARAMS (streaming_duration N)` non supporte en OGG Free 23.5
- L'Extract ABEND avec OGG-10141
- Fix : retirer le parametre, utiliser `ALTER SYSTEM SWITCH LOGFILE` a la place

### BUG SQL : produit cartesien DBA_DATA_FILES x DBA_FREE_SPACE
- Jointure directe sans pre-aggregation → valeurs multipliees
- Fix : pre-agreger les deux vues en sous-requetes `GROUP BY TABLESPACE_NAME`

### BUG SQL : PARTITION_COUNT / SUBPARTITIONING_TYPE absents de DBA_TABLES
- Ces colonnes sont dans `DBA_PART_TABLES`, pas `DBA_TABLES`
- Fix : `LEFT JOIN DBA_PART_TABLES` pour obtenir ces informations

---

## 9. Comptes et securite Oracle

### Modele de comptes OGG
| Compte | Scope | Privileges | Usage |
|--------|-------|-----------|-------|
| C##GGADMIN | Common (CDB) | DBA, DBMS_GOLDENGATE_AUTH | Extract + Replicat OGG |
| ggadmin | Local (PDB) | DBA, DBMS_GOLDENGATE_AUTH | Metadata OGG (checkpoints) |
| Schema source (ex: RSO085J1) | Local (PDB) | CONNECT, RESOURCE | Tables de donnees |
| Schema cible (ex: RCT00100) | Local (PDB) | CONNECT, RESOURCE | Tables cible + DB link |
| Compte lecture seule (ex: OGG_REFRESH_SRC) | Local (PDB) | CREATE SESSION, SELECT | Acces read-only pour refresh |

### Bonnes pratiques
- Ne jamais creer d'objets applicatifs dans CDB$ROOT
- Minimiser les privileges : principe du moindre privilege (pas de DBA pour les schemas applicatifs)
- Comptes OGG separes des comptes applicatifs
- DB link : utiliser un compte read-only dedie (pas le schema proprietaire)

---

## 10. Commandes de reference rapide

### SQL diagnostic
```sql
-- FRA monitoring
SELECT ROUND((SPACE_LIMIT-SPACE_USED)/1073741824,1) FREE_GO,
       ROUND(SPACE_USED*100/SPACE_LIMIT,1) PCT_USED
FROM V$RECOVERY_FILE_DEST;

-- SCN courant
SELECT CURRENT_SCN FROM V$DATABASE;

-- Container courant
SELECT SYS_CONTEXT('USERENV','CON_NAME') FROM DUAL;

-- Changer de container
ALTER SESSION SET CONTAINER = PDB0;

-- Mode de la base
SELECT LOG_MODE, FORCE_LOGGING, PROTECTION_MODE FROM V$DATABASE;

-- PDBs
SELECT CON_ID, NAME, OPEN_MODE FROM V$PDBS;

-- Sessions actives sur un schema
SELECT SID, SERIAL#, USERNAME, PROGRAM, STATUS
FROM V$SESSION WHERE USERNAME = 'RCT00100';

-- Partitions d'une table
SELECT PARTITION_NAME, NUM_ROWS, LAST_ANALYZED
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER = 'RCT00100' AND TABLE_NAME = 'PJ1F'
ORDER BY PARTITION_NAME;

-- Supplemental logging
SELECT LOG_GROUP_NAME, TABLE_NAME
FROM DBA_LOG_GROUPS WHERE OWNER = 'RSO085J1';

-- Tablespace usage (avec pre-aggregation -- cf. BUG-3)
SELECT df.TABLESPACE_NAME,
       ROUND(df.TOTAL/1024) TOTAL_GO,
       ROUND(NVL(fs.FREE,0)/1024) FREE_GO,
       ROUND((df.TOTAL - NVL(fs.FREE,0))*100/NULLIF(df.TOTAL,0),1) PCT_USED
FROM (SELECT TABLESPACE_NAME, SUM(BYTES)/1048576 TOTAL
      FROM DBA_DATA_FILES GROUP BY TABLESPACE_NAME) df
LEFT JOIN (SELECT TABLESPACE_NAME, SUM(BYTES)/1048576 FREE
           FROM DBA_FREE_SPACE GROUP BY TABLESPACE_NAME) fs
ON df.TABLESPACE_NAME = fs.TABLESPACE_NAME;

-- enable_goldengate_replication
SHOW PARAMETER enable_goldengate_replication;
```

### GGSCI / adminclient
```bash
# Commandes essentielles
INFO ALL
INFO EXTRACT ERCT0010, DETAIL
INFO REPLICAT RRSO0850, DETAIL
STATS REPLICAT RRSO0850, LATEST
STOP REPLICAT RRSO0850
START REPLICAT RRSO0850, ATCSN <SCN>
SEND MANAGER RELOAD
SEND EXTRACT ERCT0010, STATUS

# Sauvegarde checkpoint (TOUJOURS en premier)
# (en shell, pas dans ggsci)
cp $OGG_HOME/dirchk/RRSO0850.cpr /tmp/RRSO0850_pre_refresh_$(date +%Y%m%d_%H%M%S).cpr
```

### RMAN
```bash
rman target /
RMAN> CROSSCHECK ARCHIVELOG ALL;
RMAN> DELETE NOPROMPT EXPIRED ARCHIVELOG ALL;
RMAN> DELETE NOPROMPT ARCHIVELOG ALL COMPLETED BEFORE 'SYSDATE-7';
```
