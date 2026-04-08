# Quarkus 3.x — Specifiques version

## Differences majeures vs 2.16

| Aspect | Quarkus 2.16 | Quarkus 3.x |
|--------|-------------|-------------|
| Namespace | `javax.*` | `jakarta.*` |
| `db-kind` | build-time fixe | **runtime-overridable** |
| `jdbc.driver` | build-time fixe | runtime-overridable |
| `@Transactional` private | Ignore silencieusement | **Erreur de build** |
| RESTEasy | `quarkus-resteasy` | `quarkus-rest` (renomme en 3.9) |
| Hibernate ORM | 5.6 | 6.2+ |

## Pattern application.properties (possible en 3.x)

Grace au `db-kind` runtime, on peut avoir H2 par defaut et Oracle en `%dev` :

```properties
# Default = TU (H2, in-memory Kafka, pas de tiers)
quarkus.datasource.db-kind=h2
quarkus.datasource.jdbc.url=jdbc:h2:mem:default;MODE=Oracle
quarkus.datasource.username=sa
quarkus.datasource.password=

mp.messaging.incoming.my-channel.connector=smallrye-in-memory

# %dev = Docker Compose localhost
%dev.quarkus.datasource.db-kind=oracle
%dev.quarkus.datasource.jdbc.driver=oracle.jdbc.driver.OracleDriver
%dev.quarkus.datasource.jdbc.url=jdbc:oracle:thin:@//localhost:1521/mydb
%dev.quarkus.datasource.username=myuser
%dev.quarkus.datasource.password=mypass

%dev.mp.messaging.incoming.my-channel.connector=smallrye-kafka
%dev.mp.messaging.incoming.my-channel.bootstrap.servers=localhost:9092
```

### Avantage : Docker Compose minimaliste

```yaml
dd281-app:
  environment:
    - QUARKUS_PROFILE=dev
    # C'est tout ! Toute la config est dans application.properties %dev
```

Et `mvn quarkus:dev` active `%dev` automatiquement → meme config → dev replacement parfait.

## Dev Services ameliores

En 3.x, les Dev Services supportent nativement :
- **PostgreSQL** / **MySQL** / **MariaDB** via TestContainers
- **Kafka** via Redpanda
- **Redis**

Si Docker est disponible et compatible, Quarkus 3.x demarre automatiquement les tiers en dev/test. Pas besoin de Docker Compose pour le dev.

## Migration 2.16 → 3.x

```bash
quarkus update --stream=3.x
git diff  # inspecter les transformations automatiques
```

### Points d'attention

1. **`javax` → `jakarta`** : renommage massif (imports, annotations, packages)
2. **Hibernate 6.2** : API modifiee (Criteria, certaines annotations)
3. **RESTEasy** : `quarkus-resteasy` → `quarkus-rest`
4. **`@Transactional` private** : maintenant erreur de build → corriger avant migration
5. **Config** : certaines cles renommees (consulter le guide de migration)

## Tests — bonnes pratiques 3.x

```java
// @QuarkusTest + @InjectMock pour les tests d'integration CDI
@QuarkusTest
class MonServiceIT {
    @InjectMock  // CDI mock (Quarkus-aware)
    Repository repo;

    @Inject
    MonService service;

    @Test
    void testAvecMockCDI() { ... }
}

// @ExtendWith pour les tests unitaires purs (rapides)
@ExtendWith(MockitoExtension.class)
class MonServiceTest {
    @Mock Repository repo;
    @InjectMocks MonService service;
}
```

En 3.13+ : `@WithTestResource` remplace `@QuarkusTestResource` (API simplifiee).
