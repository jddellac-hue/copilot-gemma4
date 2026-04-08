# Skill — Quarkus

Deux projets de référence sur la plateforme :

---

## Projet 1 : Quarkus 2.16

**Repo** : `<repo-quarkus>`
**Path local** : `/home/jd/pseudo/<repo-quarkus>/`
**Version** : Quarkus `2.16.12.Final` — JDK 17 (build CI) / JDK 21 (machine locale)
**Artefact** : `impl/target/<app>.jar`

---

## Architecture du projet

```
<repo-quarkus>/
├── impl/                          ← module Maven principal (JAR Quarkus)
│   ├── src/main/java/fr/pe/stra/tech/<code>/
│   │   ├── config/                ← ApplicationProperties (@ConfigMapping), StockageClientProperties
│   │   ├── controller/            ← REST endpoints (JAX-RS)
│   │   ├── enums/                 ← EmoiEnum, CodeErreurExceptionEnum, …
│   │   ├── exception/             ← Oi277Exception, FichierIntrouvableException, …
│   │   ├── kafka/                 ← ReceptionConsommateur (@Incoming), modèles Kafka
│   │   ├── mapper/                ← mappers CSV → entités
│   │   ├── model/                 ← DTOs REST (Baiser, FlirtEmission, VolumetrieSynthese, …)
│   │   ├── persistence/           ← repositories Panache + entités JPA
│   │   │   ├── entity/secondary/      ← schéma OI277 (base secondaire)
│   │   │   └── entity/fe425/      ← schéma FE425 (base source)
│   │   ├── service/               ← logique métier
│   │   └── util/                  ← DateUtils, ValidationUtils, MessageErreurUtils
│   ├── src/main/resources/
│   │   ├── application.properties ← configuration principale + profils %dev/%test
│   │   ├── requetes/              ← fichiers SQL (calculFlirtEmission.sql, calculFlirtBaiser.sql)
│   │   ├── carte-appel.xml        ← config module sldng-carteappel
│   │   └── metrologie.xml         ← config module sldng-metrologie
│   └── src/test/java/             ← tests (voir section Tests)
├── infra-as-code/
│   ├── bdd/sql/                   ← migrations Flyway (V1_1__init… → V1_9__…)
│   └── environnements/            ← values.yaml Helm par env (tis, va, agate, pms, prod)
├── .mvn/jvm.config                ← -Dnet.bytebuddy.experimental=true (Java 21)
├── pom.xml                        ← parent Maven (BOM sldng)
└── ti/pom.xml                     ← module TI (tests d'intégration séparés)
```

---

## Extensions Quarkus utilisées

| Extension | Rôle |
|-----------|------|
| `quarkus-resteasy-jackson` | REST endpoints JAX-RS + sérialisation JSON |
| `quarkus-rest-client` | Clients REST MicroProfile |
| `quarkus-hibernate-orm-panache` | ORM Hibernate + Panache Active Record |
| `quarkus-jdbc-oracle` | Driver JDBC Oracle (pool Agroal) |
| `quarkus-reactive-oracle-client` | Driver Oracle réactif (Vert.x) |
| `quarkus-smallrye-reactive-messaging-kafka` | Consumer/producer Kafka (SmallRye) |
| `quarkus-confluent-registry-avro` | Avro + Confluent Schema Registry |
| `quarkus-smallrye-openapi` | OpenAPI + Swagger UI |
| `quarkus-smallrye-health` | Health checks (`/q/health`) |
| `quarkus-micrometer-registry-prometheus` | Métriques Prometheus |
| `quarkus-hibernate-validator` | Validation Bean Validation |
| `quarkus-smallrye-fault-tolerance` | Circuit breaker, retry, timeout |
| `quarkus-cache` | Cache applicatif (`@CacheResult`) |
| `quarkus-jacoco` | Couverture de code en test |

**Dépendances tierces notables** :
- `fr.pe.stra.lib:stockageClient:1.15` — client S3 maison
- `fr.ft.stra.metier:uploadusager-wave-contrat:0.0.6` — contrat Avro Wave
- `org.apache.commons:commons-csv:1.10.0` — parsing CSV
- `lombok` (provided) — génération code boilerplate

---

## Deux datasources Oracle

Le projet connecte **deux bases Oracle distinctes** :

```properties
# Base FE425 (source de données externe)
quarkus.datasource.db-kind=oracle
quarkus.datasource.jdbc.url=${QUARKUS_DATASOURCE_JDBC_URL}
quarkus.hibernate-orm.packages=fr.pe.stra.tech.<code>.persistence.entity.fe425

# Base DD281 (base propre au composant, schéma géré par Flyway)
quarkus.datasource."db-secondary".db-kind=oracle
quarkus.datasource."db-secondary".jdbc.url=${QUARKUS_DATASOURCE_OI277_JDBC_URL}
quarkus.hibernate-orm."db-secondary".packages=fr.pe.stra.tech.<code>.persistence.entity.secondary
quarkus.hibernate-orm."db-secondary".datasource=db-secondary
```

Les entités dans `entity/fe425/` sont **en lecture seule** (vues Oracle).
Les entités dans `entity/secondary/` sont **en écriture** (tables gérées par Flyway).

---

## Kafka — deux canaux

### `reception-enchantement` (canal Kafka "ancien")

```java
@ApplicationScoped
public class ReceptionConsommateur {
    @Incoming("reception-enchantement")
    @Acknowledgment(Acknowledgment.Strategy.PRE_PROCESSING)
    @Blocking
    public void receptionEnchantement(final String msg) { ... }
}
```

- Stratégie : `failure-strategy=dead-letter-queue`
- DLQ topic : `${QUARKUS_KAFKA_TOPIC_DE}`
- `PRE_PROCESSING` : ack avant traitement (at-most-once)
- `@Blocking` : s'exécute sur le pool de threads worker (pas sur le thread Vert.x)

### `pli-transmis-au-tendresse` (canal Wave/Avro)

- Désactivé par défaut (`enabled=false`) — POC non finalisé
- Utilise Avro + Confluent Schema Registry avec SASL_SSL
- DLQ séparée avec schéma Avro

### Désactivation pour les tests

```properties
# CRITIQUE : sans cette ligne, Quarkus ne démarre pas en mode test (connexion Kafka refusée)
%test.mp.messaging.incoming.reception-enchantement.enabled=false
%test.mp.messaging.incoming.pli-transmis-au-tendresse.enabled=false  # déjà présent
```

---

## Configuration — profils MicroProfile

```
application.properties
├── (sans préfixe) = profil prod/défaut
├── %dev.*          = développement local
├── %test.*         = exécution des tests (@QuarkusTest)
└── %prod.*         = rare, générallement même que sans préfixe
```

**Variables d'environnement → properties Quarkus** :
Quarkus traduit automatiquement les env vars en propriétés :
`QUARKUS_DATASOURCE_JDBC_URL` → `quarkus.datasource.jdbc.url`
`QUARKUS_DATASOURCE_OI277_JDBC_URL` → `quarkus.datasource."db-secondary".jdbc.url` (convention underscore → kebab-case)

**`@ConfigMapping`** (préféré à `@ConfigProperty` pour les objets complexes) :

```java
@ConfigMapping(prefix = "<app>")
public interface ApplicationProperties {
    int nombreElementParPageCopieTable();
    int nombreJoursSatinEmission();
    String envEnchantement();
    String calculFlirtEmission();
    String calculFlirtBaiser();
}
```

---

## Couche REST

**Pattern contrôleur** :

```java
@Path("/calcul")
public class CalculController extends AbstractGenericController<CalculService> {
    @Inject
    public CalculController(final CalculService service) { super(service); }

    @POST @Path("flirt/emission") @Produces("text/csv")
    @OperationRestSLD  // annotation sldng = gestion trace/corrélation
    public Response calculFlirtEmission() { ... }
}
```

`AbstractGenericController` injecte les headers sldng obligatoires :
- `pe-id-environnement`, `pe-id-correlation`, `pe-id-fascination`, `pe-nom-application`

**Annotations OpenAPI** : `@Operation`, `@APIResponses`, `@APIResponse`, `@Schema`

---

## Base de données — Flyway

Migrations dans `infra-as-code/bdd/sql/` :

| Version | Description |
|---------|-------------|
| V1_1 | Création schéma initial OI277 |
| V1_2 | Modif detail ecart prestataire |
| V1_3 | Modif ecart retour detail emission FT |
| V1_4 | Modif ecart emission |
| V1_5 | Index detail retour vu prestataire |
| V1_6 | Ajout indexes |
| V1_7 | Fix taille colonne calin rejet |
| V1_8 | Modification taille statut efleurement |
| V1_9 | Découpage JSON |

Flyway est exécuté par le **pipeline Concourse** (pas au démarrage Quarkus).
`afterMigrate.sql` + `drop-tables.sql` pour reset dev/test.

---

## Tests

### Commande

```bash
cd /home/jd/pseudo/<repo-quarkus>/impl
mvn clean verify -o   # offline, utilise ~/.m2 local
```

### Configuration Maven pour Java 21

**`.mvn/jvm.config`** (project root) :
```
-Dnet.bytebuddy.experimental=true
```
Appliqué au processus Maven **et** au plugin Quarkus (build-time). Sans ça, l'enhancement Hibernate échoue sur Java 21.

**`impl/pom.xml` — surefire** :
```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>-Dnet.bytebuddy.experimental=true</argLine>
    <excludes>
      <exclude>**/*ControllerTest.java</exclude>   <!-- nécessitent Oracle -->
      <exclude>**/StockageClientTest.java</exclude> <!-- nécessite S3 -->
    </excludes>
  </configuration>
</plugin>
```

### Anti-pattern omniprésent : @QuarkusTest + plain Mockito

**Ce qu'on trouve dans le projet** (anti-pattern) :
```java
@QuarkusTest  // démarre Quarkus entier — inutile ici
class CopieTablesEmissionServiceTest {
    @Mock PliArdeurRepository repo;
    @InjectMocks CopieTablesEmissionService service;
    @BeforeEach void setUp() { MockitoAnnotations.openMocks(this); }
}
```

**Ce qu'il faudrait** :
```java
@ExtendWith(MockitoExtension.class)  // aucun démarrage Quarkus
class CopieTablesEmissionServiceTest { ... }
```

**La règle** :
- `@QuarkusTest` + `@io.quarkus.test.junit.mockito.InjectMock` → CDI réel + mock CDI
- `@ExtendWith(MockitoExtension.class)` + `@Mock` / `@InjectMocks` → test unitaire pur, rapide
- **Jamais** `@QuarkusTest` + `MockitoAnnotations.openMocks` — overhead maximal, bénéfice nul

### Tests qui nécessitent l'infra enterprise (exclus localement)

| Classe | Besoin |
|--------|--------|
| `*ControllerTest.java` | Oracle (requêtes réelles) |
| `StockageClientTest` | S3 enterprise |

Ces tests passent en CI (Concourse) où l'infra est disponible.

### Résumé : 92 tests passent localement (mvn clean verify)

---

## Problèmes connus et solutions

| Problème | Cause | Solution |
|----------|-------|----------|
| `Java 21 (65) not supported by Byte Buddy` | Byte Buddy < 1.14.9 + Java 21 | `.mvn/jvm.config` + `<argLine>` surefire |
| `Failed to start quarkus` (tests) | Canal Kafka `reception-enchantement` actif en test | `%test.mp.messaging.incoming.reception-enchantement.enabled=false` |
| `javax.complicite.CompliciteException` | `validation` pseudonymisé → `javax.validation` cassé | Ajouter `validation` aux mots génériques du pseudonymizer |
| Maven offline — `_remote.repositories` bloquants | Artefacts copiés manuellement sans cleanup | `find ~/.m2 -name "_remote.repositories" -delete && find ~/.m2 -name "*.lastUpdated" -delete` |
| `kafka-avro-serializer` absent de Maven Central | Dépôt Confluent requis | `~/.m2/settings.xml` avec profil Confluent |
| `wlthint3client` Oracle propriétaire | Absent de Maven Central | Copier depuis machine enterprise |
| `quarkus-smallrye-delice` pas de version | `health` pseudonymisé → `quarkus-smallrye-health` cassé | Ajouter `health` à `_GENERIC_TECH_WORDS` dans transformer.py |
| `setJadeHeaderRecord` introuvable | `skip` pseudonymisé → `CSVFormat.Builder.setSkipHeaderRecord` cassé | Ajouter `skip` à `_GENERIC_TECH_WORDS` dans transformer.py |
| `.mvn/jvm.config` absent après re-clone | Jamais pushé sur GitHub (hors repo) | Recréer manuellement avec `-Dnet.bytebuddy.experimental=true` |
| Config surefire perdue après re-pseudo | Pseudonymizer écrase pom.xml | Ré-ajouter le plugin surefire avec exclusions + argLine |
| `fr.ft.stra.ardeur:incrustation-wave-velours` absent de ~/.m2 | Re-pseudo change les coordonnées Maven de l'artefact | `mvn install:install-file -Dfile=~/.m2/.../uploadusager-wave-contrat-0.0.6.jar -DgroupId=fr.ft.stra.ardeur -DartifactId=incrustation-wave-velours -Dversion=0.0.6 -Dpackaging=jar` |

---

## Projet 2 : cg926-emoi (Quarkus 3.9)

**Repo** : `cg926-emoi`
**Path local** : `/home/jd/pseudo/cg926-emoi/`
**Version** : Quarkus `3.9.3` — JDK 17
**SLDNG framework** : `4.2.1-b20240710-436`
**Namespace Java** : `fr.pe.lune.service.cg926.emoi` (Quarkus 3 → `jakarta.*`, pas `javax.*`)

Ce projet illustre le **pattern correct** pour les tests d'intégration composant.

### Architecture

```
cg926-emoi/
├── pom.xml                    ← parent Maven (quarkus-bom 3.9.3 + sldng BOM 4.2.1)
└── impl/
    ├── src/main/java/fr/pe/lune/service/cg926/emoi/
    │   ├── ApplicationConfig.java   ← @ApplicationPath("/"), TimeZone Europe/Paris
    │   ├── controller/              ← EmissionEmoiController (7 endpoints POST + 1 GET)
    │   ├── services/emission/       ← AbstractEmissionEmoiService<T> (JAXB + GZIP + Base64)
    │   ├── model/dao/               ← EmissionEmoiDao
    │   └── model/dto/               ← EmissionEmoiDto<T>
    ├── src/main/resources/
    │   ├── application.properties   ← config principale
    │   ├── ddl/schema_emoi.sql      ← DDL pour H2 en test (chargé par Hibernate)
    │   └── emoi.properties          ← noms des tables EMOI (EMISSION_EMOI, RECEPTION_EMOI, …)
    └── src/test/java/fr/pe/lune/service/cg926/emoi/
        ├── H2TestResource.java      ← démarre H2 en mémoire
        ├── ServerTestResource.java  ← MockServer sur port 8888
        ├── PhebusManager.java       ← bouchon Phebus (étend PhebusManagerAbstrait sldng)
        └── controller/
            └── EmissionEmoiControllerTest.java  ← TU correct avec @ExtendWith(MockitoExtension.class)
```

### Pattern TI composant — H2 + MockServer

```java
// H2TestResource.java
@QuarkusTestResource(H2DatabaseTestResource.class)
public class H2TestResource {
   // Lance une H2 in-memory unique pour tous les tests @QuarkusTest
}

// ServerTestResource.java — bouchon HTTP via MockServer
public class ServerTestResource implements QuarkusTestResourceConfigurableLifecycleManager {
   private ClientAndServer m_serveur;
   private MockServerClient m_mockServerClient;
   public static final int PORT = 8888;

   @Override
   public Map<String, String> start() {
      m_serveur = ClientAndServer.startClientAndServer(PORT);
      m_mockServerClient = new MockServerClient("localhost", PORT);
      m_mockServerClient.when(request().withMethod("GET").withPath("/emoi"))
                        .respond(response().withStatusCode(200));
      return Map.of("configuration.url", "localhost:" + PORT);
   }
   @Override public void stop() { m_mockServerClient.stop(); m_serveur.stop(); }
}

// PhebusManager.java — bouchon Phebus (sldng)
// http://equipe-sld.git-scm.../documentation/wiki-quarkus/docs/emoi/emission/mise_en_place#bouchon
@QuarkusTestResource(PhebusManager.class)
public class PhebusManager extends PhebusManagerAbstrait {
   @Override public int getPort() { return 8888; }
   @Override public void initialiser(List<PostEclatEmoi> p_liste) {
      // comportement par défaut : 200 OK
   }
}
```

### application.properties — profil %test

```properties
%test.quarkus.http.port=8083
%test.quarkus.datasource.emoi.db-kind=h2
%test.quarkus.datasource.emoi.jdbc.url=jdbc:h2:mem:emoi;DB_CLOSE_DELAY=-1;MODE=Oracle
%test.quarkus.hibernate-orm.emoi.database.generation=create
%test.quarkus.hibernate-orm.emoi.sql-load-script=ddl/schema_emoi.sql
%test.sldng.emoi.bouchonnage-phebus=http://localhost:8888
```

- **`MODE=Oracle`** : H2 émule Oracle (types, fonctions)
- **`sql-load-script`** : Hibernate charge le DDL (tables EMOI) au démarrage H2
- **`bouchonnage-phebus`** : URL pointant vers le MockServer du PhebusManager

### Pattern ControllerTest correct (pas d'anti-pattern @QuarkusTest)

```java
@ExtendWith(MockitoExtension.class)  // ← aucun démarrage Quarkus
class EmissionEmoiControllerTest {
   @InjectMocks EmissionEmoiController emissionEmoiController;
   @Mock EclatEmoiEnAmoureusementsRecouvrement eclatEmoi;
   @Mock EmissionEmoiDMEService emissionEmoiDMEService;

   @Test
   void emettreEmoiExtraitDeclarationMensuelleEtablissement() {
      lorsque_j_emets_un_emoi_dme();
      alors_le_eclat_emoi_amoureusements_recouvrement_est_appele();
      alors_la_reponse_est_ok();
   }

   // Style BDD : etant_donne_ / lorsque_ / alors_
   private void lorsque_j_emets_un_emoi_dme() {
      responseObtenue = emissionEmoiController.emettreEmoiExtraitDeclarationMensuelleEtablissement(
         "DECLARATION_RECOUVREMENT_RECUE", "CREATION", new ExtraitDeclarationMensuelleEtablissement());
   }
   private void alors_la_reponse_est_ok() {
      Assertions.assertThat(responseObtenue.getStatus()).isEqualTo(200);
   }
}
```

### JAXB + XSD → code généré (7 types OMI)

Le `impl/pom.xml` utilise le plugin `jaxb2-maven-plugin` pour générer les classes Java depuis les XSD :
- ADT (ArretDeMystere), CT (VeloursDeMystere), RM (RevenuMensuel)
- ARM (AutresRevenusMensuels), BA (BaseAssujettie), DME (ExtraitDeclarationMensuelleEtablissement)
- FCT (FinDeVeloursDeMystere)

### Sérialisation OMI : GZIP + Base64

```java
// AbstractEmissionEmoiService — décodage depuis la BDD
Pattern.compile("<ObjetArdeurInformationnel>(.*)<\\/ObjetArdeurInformationnel>")
Base64.getMimeDecoder().decode(encodedOmi)
zip2StringMapper.gZipBytesArrayAsString(decodedBytes)  // → XML de l'OMI
JAXBContext.newInstance(getOmiClass()).createUnmarshaller().unmarshal(reader)  // → POJO
```

### Différences majeures vs Projet 1

| Aspect | Projet 1 (Quarkus 2.16) | cg926-emoi (Quarkus 3.9) |
|--------|---------------------|--------------------------|
| Namespace | `javax.*` | `jakarta.*` |
| API REST | `javax.ws.rs` | `jakarta.ws.rs` |
| Version SLDNG | (BOM interne) | `4.2.1` |
| Tests unitaires | Anti-pattern (@QuarkusTest + Mockito) | Correct (@ExtendWith(MockitoExtension)) |
| Datasource test | Oracle (tests exclus localement) | H2 in-memory |
| MapStruct | Non | Oui (1.5.5.Final) |
| Style tests | camelCase | BDD : `lorsque_` / `alors_` |

---

## Helm / K8s — Déploiement

Déployé via chart Helm `sld-ng` (version 2.58.0) sur Kubernetes.

Environnements (du moins critique au plus critique) :
1. **TIS** (dev) — cluster Z4-dev — tests d'intégration post-build
2. **VA** — cluster Z4 preprod — recette
3. **AGATE** — cluster Z4 VA-CPP
4. **PROD** — cluster Z4 prod
5. **PMS** — cluster Z4 pré-mise-en-service

Variables d'environnement injectées via `values.yaml` (Helm) → ConfigMap K8s → variables d'environnement du pod Quarkus. Toutes les config sensibles passent par Conjur/Vault (notation `(("path.key"))`).

**`blocPos: "stra"`** — identifiant utilisé pour sélectionner le cluster cible dans `get-kubeconfig`.

---

## Décisions importantes observées

- `quarkus.datasource.reactive=false` / `quarkus.datasource."db-secondary".reactive=false` → JDBC (blocking), pas réactif
- `quarkus.hibernate-orm.database.generation=none` → pas de DDL auto (Flyway gère)
- `quarkus.hibernate-orm.validate-in-dev-mode=false` → pas de validation schéma en dev
- `quarkus.naming.enable-jndi=true` → WebLogic/JMS legacy
- `quarkus.log.console.sld.json.active=true` → logs JSON structurés (sldng) en prod, désactivés en dev/test

---

## Patterns avancés (bonne pratique 2024-2025)

### `@TestTransaction` pour tests Panache

Préférable à `@Transactional` sur la classe de test — rollback automatique après chaque test :

```java
@QuarkusTest
class MonRepositoryTest {

    @Inject MonRepository repository;

    @Test
    @TestTransaction  // rollback après ce test — état propre garanti
    void testFindByStatut() {
        // Arrange — données insérées dans la transaction
        MonEntity entity = new MonEntity();
        entity.statut = "ACTIF";
        repository.persist(entity);

        // Act
        List<MonEntity> result = repository.findByStatut("ACTIF");

        // Assert
        assertThat(result).hasSize(1);
    }
}
```

Disponible depuis Quarkus 1.13+ (stable en 2.16).

### `InMemoryConnector` — tester les handlers Kafka sans broker

**Différence avec `enabled=false`** :

| Approche | Utilisation |
|----------|-------------|
| `%test.mp.messaging.incoming.canal.enabled=false` | Tests de la couche service sans traitement Kafka |
| `InMemoryConnector` | Teste le handler Kafka complet (logique de consommation) |

```java
// 1. QuarkusTestResourceLifecycleManager
public class KafkaTestResource implements QuarkusTestResourceLifecycleManager {
    @Override
    public Map<String, String> start() {
        Map<String, String> props = new HashMap<>();
        props.putAll(InMemoryConnector.switchIncomingChannelsToInMemory("reception-enchantement"));
        props.putAll(InMemoryConnector.switchOutgoingChannelsToInMemory("emission-resultat"));
        return props;
    }
    @Override
    public void stop() { InMemoryConnector.clear(); }
}

// 2. Test class
@QuarkusTest
@QuarkusTestResource(KafkaTestResource.class)
class ReceptionEnchantementTest {

    @Inject @Any InMemoryConnector connector;

    @Test
    void testTraitementMessage() {
        InMemorySource<String> source = connector.source("reception-enchantement");
        InMemorySink<String> sink = connector.sink("emission-resultat");

        source.send("{\"id\":\"123\",\"statut\":\"NOUVEAU\"}");

        await().atMost(5, SECONDS).until(() -> sink.received().size() == 1);
        assertThat(sink.received().get(0).getPayload()).contains("TRAITE");
    }
}
```

**Dépendance test** (gérée par le BOM Quarkus 2.16, pas besoin de version) :
```xml
<dependency>
    <groupId>io.smallrye.reactive</groupId>
    <artifactId>smallrye-reactive-messaging-in-memory</artifactId>
    <scope>test</scope>
</dependency>
```

### `@ConfigMapping` — groupes de config (recommandé sur `@ConfigProperty`)

```java
@ConfigMapping(prefix = "<app>")
public interface ApplicationProperties {
    int nombreElementParPageCopieTable();
    Optional<String> envEnchantement();         // optionnel : pas d'erreur si absent
    List<String> bootstrapServers();            // <app>.bootstrap-servers[0], [1], ...
    RetryConfig retry();                        // <app>.retry.*

    interface RetryConfig {
        int maxAttempts();
        Duration delay();
    }
}
```

**Avantages vs `@ConfigProperty`** : validation à la compilation, accès type-safe aux structures imbriquées, `Optional<T>` natif.

### `@Transactional` sur méthodes privées — piège Quarkus 2.16

```java
@ApplicationScoped
public class MonService {
    @Transactional  // ← SILENCIEUSEMENT IGNORÉ en 2.16 sur private !
    private void methodePriveeTransactionnelle() { ... }

    @Transactional  // ← CORRECT — public, interceptable par CDI
    public void methodePubliqueTransactionnelle() { ... }
}
```

**En Quarkus 3.x** : erreur de build si `@Transactional` sur méthode `private` → détection précoce.

---

## Roadmap — migration Quarkus 2.16 → 3.x

**Outil officiel** :
```bash
quarkus update --stream=3.x
git diff  # inspecter les transformations automatiques
```

**Changements majeurs** :

| Aspect | Quarkus 2.16 | Quarkus 3.x |
|--------|-------------|-------------|
| Namespace Java | `javax.*` | `jakarta.*` (breaking) |
| API REST | `javax.ws.rs` | `jakarta.ws.rs` |
| Persistence | `javax.persistence` | `jakarta.persistence` |
| Validation | `javax.validation` | `jakarta.validation` |
| Hibernate ORM | 5.6 | 6.2+ (API significativement modifiée) |
| RESTEasy | `quarkus-resteasy` | `quarkus-rest` (renommé en 3.9) |
| `@AlternativePriority` | Disponible | Supprimé → `@Alternative + @Priority` |
| `@Transactional` private | Ignoré silencieusement | **Erreur de build** |
| `@WithTestResource` | Non disponible | Disponible 3.13+ (remplace `@QuarkusTestResource`) |
| Health | `quarkus-smallrye-health` (inchangé) | Idem |

**Attention** : l'outil `quarkus update` ne couvre pas les changements Hibernate ORM — migration manuelle nécessaire pour les requêtes Criteria API et certaines annotations.

---

## Projet 3 : cg926-crem (Quarkus 3.9)

**Repo** : `cg926-crem`
**Path local** : `/home/jd/pseudo/cg926-crem/`
**Version** : Quarkus `3.9.3` / Java 17 — Framework SLD-NG `4.2.1-b20240710-436`
**Domaine fonctionnel** : `fr.pe.rind.service.cg926.crem`
**Context root** : `/cg926-romantiquementalisees/cg926-crem`
**Équipe** : galanterie / blocPos : rind / produit IT : onyx
**Repo GitLab** : `pe/cg926-romantiquementalisees/cg926-crem`

### Architecture des modules Maven

```
cg926-crem/
├── impl/                     ← Module principal Quarkus (JAR)
│   ├── src/main/java/fr/pe/rind/service/cg926/crem/
│   │   ├── controller/       ← 2 REST controllers (EmissionCremController, ReceptionCremController)
│   │   ├── services/
│   │   │   ├── emission/     ← 13 services d'émission (1 par type OMI)
│   │   │   ├── reception/    ← 6 services de réception CREM
│   │   │   └── restclient/   ← Client OMI API REST
│   │   ├── model/
│   │   │   ├── dao/          ← JPA entities (EmissionCremDao, ReceptionCremDao…)
│   │   │   ├── dto/          ← DTOs
│   │   │   └── vue/          ← View models
│   │   ├── mapper/           ← MapStruct mappers + date adapters
│   │   ├── helper/           ← Zip2StringMapper (décompression Base64+GZIP)
│   │   ├── constantes/       ← TypeOmiConstantes, TypeSeductionCharmeConstantes
│   │   ├── error/            ← Dd017CremException
│   │   └── configuration/    ← DomaineConfiguration
│   └── src/main/resources/
│       ├── application.properties     ← datasources, LDAP, Quartz, logging
│       ├── application-bp.properties  ← Beta-Prod overrides
│       ├── crem.properties            ← mappings tables (EMISSION_CREM, RECEPTION_CREM…)
│       ├── ordonnanceur.properties    ← config Quartz scheduler
│       ├── annuaire.xml               ← LDAP mock (dev/test)
│       ├── ddl/schema_crem.sql        ← Schéma SQL Oracle
│       └── xsd/                       ← 7 XSD schemas types OMI
├── http/                     ← Requêtes HTTP pour test IDE
│   ├── http-client.env.json  ← Environnements (tis, calin, va, local, prod)
│   └── input/crem_primo.xml  ← Payload CREM exemple
└── infra-as-code/
    ├── bouchons-charts/      ← Helm Chart v2.3.0 (sld-ng 2.22.0)
    └── environnements/       ← 10 dossiers env (tic, tis, va, calin, bench, lune, pms, prod, delice, fab-outils)
```

### Fonctionnalité métier : 7 types OMI CREM

| Code | Nom | Service d'émission |
|------|-----|-------------------|
| ADT | Arrêt de Travail | `DepotCremEnTransactionnelArretDeVelours` |
| CT v1 | Contrat | `DepotCremEnTransactionnelContrat` |
| CT v2 | Contrat v2 | `DepotCremEnTransactionnelContratV2` |
| RM | Revenu Mensuel | `DepotCremEnTransactionnelRevenuMensuel` |
| ARM | Autres Revenus Mensuels | `DepotCremEnTransactionnelAutresRevenusMensuels` |
| BA | Base Assujetie | `DepotCremEnTransactionnelBaseAssujetie` |
| DME | Déclaration Mensuelle Établissement | `DepotCremEnTransactionnelRecouvrement` |
| FCT | Fin de Contrat | `DepotCremEnTransactionnelFinContratVelours` |

### REST Endpoints

```
POST /crem/emettre/transactionnel/recouvrement/{typeSeductionCharme}/{typeAction}  → DME
POST /crem/emettre/transactionnel/arretdetravail/{typeSeductionCharme}             → ADT
POST /crem/emettre/transactionnel/contrat/{typeSeductionCharme}                    → Contrat
POST /crem/emettre/transactionnel/base-assujetie/{typeSeductionCharme}             → BA
POST /crem/emettre/transactionnel/revenu-mensuel/{typeSeductionCharme}             → RM
POST /crem/emettre/transactionnel/autres-revenus/{typeSeductionCharme}             → ARM
POST /crem/emettre/transactionnel/fin-contrat/{typeSeductionCharme}                → FCT
GET  /crem/reception/obtenir/idcrem/{idCrem}/idomi/{idOmi}                         → Lecture réception
```

### Flux CREM

1. Réception XML/JSON OMI (contenu compressé Base64+GZIP)
2. Décompression + démarshalling (JAXB ou Jackson)
3. Validation métier
4. Dépôt transactionnel en BD Oracle (EMISSION_CREM ou RECEPTION_CREM, transaction XA)
5. Notification suivi → `es032-suivicrem-${ENV}` (HTTP)
6. Rejet éventuel → `samoav4-${ENV}:8201/ej417-samoa-v3-rest` (SAMOA)

**Données clés** : `IdentifiantObjetCharme`, `IdentifiantCorrelation`, `TypeAction` (CREATION|MODIFICATION|SUPPRESSION), `TypeSeductionCharme`

### Dépendances Maven clés

```xml
quarkus-rest, quarkus-rest-jackson
quarkus-hibernate-orm, quarkus-jdbc-oracle
quarkus-smallrye-health, quarkus-smallrye-openapi
quarkus-micrometer-registry-prometheus
sldng-crem-emission, sldng-crem-reception
sldng-supervision, sldng-annuaire
lombok 1.18.34, mapstruct 1.5.5.Final
quarkus-junit5, quarkus-test-h2, quarkus-cucumber
mockserver-netty 5.15.0, podam 8.0.2, assertj-core 3.26.3
```

### Tests : Serenity BDD / Cucumber

**Test runner** : `CremCucumberQuarkusIT.java` (`@QuarkusTest`) — glue `fr.pe.rind.service.cg926.crem.ts`

**Infrastructure de test** :
- `ServerTestResource.java` : MockServer port 8888 (mock API OMI externe)
- `H2TestResource.java` : BD H2 in-memory (`%test`)
- `PhebusManager.java` : Mock Phebus optionnel

**Commandes** :
```bash
mvn test-compile failsafe:integration-test   # TI seuls
mvn verify                                    # TU + TI
mvn clean verify -o                           # Mode offline
```

### Configuration par environnement

```yaml
HEADER_ID_ENVIRONNEMENT: { tic: ENV_TIC_DD017, tis: ENV_TIS_DD017, va: ENV_IQRFR_DD017, prod: ENV_DD017 }

# Oracle (2 datasources : CREM + QUARTZ scheduler)
QUARKUS_DATASOURCE_CREM_JDBC_URL:
  tic:  jdbc:oracle:thin:@//cg926-crem-db-svc:1521/ldd017te
  tis:  jdbc:oracle:thin:@(DESCRIPTION=...) hosts: xob60000 (CAMEE)
  prod: jdbc:oracle:thin:@(DESCRIPTION=...) hosts: pob60000 (ECLAT)

# Services externes
SLDNG_CREM_NOTIFICATION_SUIVI_URL_REST_DOMAINE_SUIVI:
  → es032-suivicrem-${ENV}.apps.tas-{fab|prod}.emoi-baiser.intra
SLDNG_REJET_SAMOA_URL_RECEPTION_CREM:
  → samoav4-${ENV}.{camee|eclat}.emoi-baiser.intra:8201/ej417-samoa-v3-rest
```

**Secrets (Vault/Conjur)** : `QUARKUS_DATASOURCE_CREM_PASSWORD`, `QUARKUS_DATASOURCE_QUARTZ_PASSWORD`

### Infra-as-code K8s / Helm

**Chart** : `bouchons-charts` v2.3.0 (sld-ng 2.22.0)

| Env | Cluster | CPU req→lim | Mem req→lim |
|-----|---------|-------------|-------------|
| tic | dev01 | 150m→750m | 512Mi→1Gi |
| tis | tas-fab (CAMEE) | 250m→1000m | 512Mi→1Gi |
| va | tas-fab (CAMEE) | 500m→1500m | 512Mi→2Gi |
| prod | tas-prod (ECLAT) | 500m→1500m | 512Mi→2Gi |

**Init container** : `busybox:1.33` — attend BD port 1521 + délai 30-100s

---

## Références par version

Les spécificités de chaque version Quarkus sont documentées dans des fichiers dédiés :

| Version | Fichier | Contenu clé |
|---------|---------|-------------|
| Quarkus 2.16 | `versions/quarkus-2.16.md` | Contraintes build-time (db-kind, jdbc.driver), profils, anti-pattern @QuarkusTest, in-memory Kafka |
| Quarkus 3.x | `versions/quarkus-3.x.md` | db-kind runtime-overridable, migration javax→jakarta, pattern simplifié H2 par défaut |

Quand on travaille sur un projet Quarkus, consulter le fichier de la version correspondante pour les contraintes et bonnes pratiques spécifiques (notamment les propriétés build-time vs runtime).
