# Quarkus 2.16 — Specifiques version

## Contraintes build-time

En Quarkus 2.16, plusieurs proprietes sont resolues a la **compilation** (augmentation Quarkus) et ne peuvent pas etre changees au runtime via les profils :

| Propriete | Type | Consequence |
|-----------|------|-------------|
| `quarkus.datasource.db-kind` | build-time | Le driver JDBC est fige dans le binaire |
| `quarkus.datasource.jdbc.driver` | build-time | Idem — impossible de basculer H2/Oracle via `%dev`/`%test` |
| `quarkus.datasource.jdbc` | build-time | Activer/desactiver JDBC est fige |

### Consequence pour les profils

On ne peut **pas** avoir H2 par defaut et Oracle en `%dev`. Le workaround :
- **Default** = `db-kind=oracle` + `jdbc.driver=oracle.jdbc.driver.OracleDriver` (pour le build Docker)
- **`%test`** = override `jdbc.driver=org.h2.Driver` + `jdbc.url=jdbc:h2:mem:test;MODE=Oracle` (fonctionne car le build pour `mvn test` inclut les deux extensions via les deps Maven)
- **`%dev`** = herite des defaults Oracle (localhost Docker Compose)

### Dev Services

Quarkus 2.16 utilise TestContainers pour les Dev Services. Si le Docker local n'est pas compatible (API trop ancienne), il faut les desactiver :

```properties
quarkus.kafka.devservices.enabled=false
quarkus.datasource.devservices.enabled=false
quarkus.apicurio-registry.devservices.enabled=false
```

## Namespace Java

`javax.*` (pas `jakarta.*`). Migration vers Jakarta dans Quarkus 3.x.

```java
import javax.enterprise.context.ApplicationScoped;
import javax.inject.Inject;
import javax.ws.rs.Path;
import javax.persistence.Entity;
```

## Kafka SmallRye — particularites

### Acknowledgment PRE_PROCESSING

```java
@Incoming("requests-xml")
@Acknowledgment(Acknowledgment.Strategy.PRE_PROCESSING)
@Blocking(ordered = false)
public void processXmlDocument(final String msg) { ... }
```

- **PRE_PROCESSING** : offset commite avant traitement (at-most-once)
- **POST_PROCESSING** : offset commite apres traitement (at-least-once, necessite idempotence)

### Consumer throttling en mode dev

En `quarkus:dev`, les consumers Kafka SmallRye peuvent etre lents (20s entre messages). Ajouter dans le profil `%dev` :

```properties
%dev.mp.messaging.incoming.my-channel.pause-if-no-requests=false
%dev.mp.messaging.incoming.my-channel.throttled.unprocessed-record-max-age.ms=120000
```

### In-memory connector pour les TU

```xml
<dependency>
    <groupId>io.smallrye.reactive</groupId>
    <artifactId>smallrye-reactive-messaging-in-memory</artifactId>
</dependency>
```

```properties
# Default (TU) : pas de broker Kafka reel
mp.messaging.incoming.my-channel.connector=smallrye-in-memory
# %dev : broker reel
%dev.mp.messaging.incoming.my-channel.connector=smallrye-kafka
%dev.mp.messaging.incoming.my-channel.bootstrap.servers=localhost:9092
```

## Pattern application.properties recommande

```
# Defaults = TU-safe (H2 en %test, Kafka in-memory, S3 NONE)
# %test = H2 en memoire (jdbc.driver override)
# %dev = Docker Compose localhost (Oracle, Kafka, S3Mock)
# Prod = env vars K8s surchargent tout
```

## Anti-pattern @QuarkusTest + Mockito

```java
// MAUVAIS — demarre Quarkus entier pour rien
@QuarkusTest
class MonServiceTest {
    @Mock Repository repo;
    @InjectMocks MonService service;
    @BeforeEach void setUp() { MockitoAnnotations.openMocks(this); }
}

// CORRECT — test unitaire pur, rapide
@ExtendWith(MockitoExtension.class)
class MonServiceTest {
    @Mock Repository repo;
    @InjectMocks MonService service;
}
```

## Dependencies test recommandees

```xml
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-jdbc-h2</artifactId>
</dependency>
<dependency>
    <groupId>io.smallrye.reactive</groupId>
    <artifactId>smallrye-reactive-messaging-in-memory</artifactId>
</dependency>
<dependency>
    <groupId>io.quarkus</groupId>
    <artifactId>quarkus-junit5-mockito</artifactId>
    <scope>test</scope>
</dependency>
```
