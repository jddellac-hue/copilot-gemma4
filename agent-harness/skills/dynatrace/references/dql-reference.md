# DQL Reference

## Table of Contents
1. [Query Fundamentals](#query-fundamentals)
2. [Data Source Commands](#data-source-commands)
3. [Filter Commands](#filter-commands)
4. [Field Commands](#field-commands)
5. [Aggregation Commands](#aggregation-commands)
6. [Timeseries Commands](#timeseries-commands)
7. [Parse Command](#parse-command)
8. [Join and Lookup](#join-and-lookup)
9. [Functions Reference](#functions-reference)
10. [Operators](#operators)
11. [Data Types](#data-types)
12. [Best Practices](#best-practices)

---

## Query Fundamentals

DQL uses pipe-based processing. Data flows from one command to the next via `|`.

```dql
fetch logs                           // Load data
| filter loglevel == "ERROR"         // Filter records
| fieldsAdd severity = upper(loglevel) // Transform
| summarize count(), by:{severity}   // Aggregate
| sort `count()` desc                // Order
| limit 10                           // Limit output
```

### Timeframe Parameters
- `from:now()-1h` - Relative time (1 hour ago)
- `to:now()` - Current time
- `from:"2024-01-01T00:00:00Z"` - Absolute ISO timestamp
- Default timeframe: 2 hours if not specified

### Time Literals
- Minutes: `5m`, `30m`
- Hours: `1h`, `24h`
- Days: `1d`, `7d`
- Weeks: `1w`

---

## Data Source Commands

### fetch
Load data from Grail storage.

```dql
fetch <data_object> [, from:] [, to:] [, timeframe:] [, samplingRatio:] [, scanLimitGBytes:]
```

**Data objects:**
| Object | Description |
|--------|-------------|
| `logs` | Log records |
| `events` | Davis events |
| `bizevents` | Business events |
| `spans` | Distributed trace spans |
| `dt.entity.host` | Host entities |
| `dt.entity.service` | Service entities |
| `dt.entity.process_group` | Process groups |
| `dt.entity.process_group_instance` | Process instances |

**Examples:**
```dql
// Basic fetch with timeframe
fetch logs, from:now()-24h, to:now()

// With sampling for large datasets
fetch logs, from:now()-7d, samplingRatio:0.1

// Limit scan size
fetch logs, scanLimitGBytes:100
```

### data
Generate sample data for testing.

```dql
data record(name="test", value=100),
     record(name="test2", value=200)
```

### describe
Show schema for a data object.

```dql
describe logs
```

### load
Load lookup data from tabular files.

```dql
load "/lookups/regions"
```

---

## Filter Commands

### filter
Keep records matching condition.

```dql
fetch logs
| filter loglevel == "ERROR"
| filter contains(content, "timeout")
```

### filterOut
Remove records matching condition.

```dql
fetch logs
| filterOut loglevel == "DEBUG"
```

### search
Full-text search (less precise than filter).

```dql
fetch logs
| search "error timeout"
```

### dedup
Remove duplicates.

```dql
fetch logs
| dedup dt.entity.host
```

**Filter operators:**
| Operator | Description |
|----------|-------------|
| `==` | Equals |
| `!=` | Not equals |
| `>`, `<`, `>=`, `<=` | Comparison |
| `and`, `or`, `not` | Logical |
| `in()` | Member of list |
| `contains()` | String contains |
| `startsWith()` | String prefix |
| `endsWith()` | String suffix |
| `matchesPhrase()` | Phrase match |
| `matchesValue()` | Pattern match |

---

## Field Commands

### fields
Select and optionally transform fields.

```dql
fetch logs
| fields timestamp, severity=lower(loglevel), content
```

### fieldsAdd
Add new computed fields.

```dql
fetch logs
| fieldsAdd duration_ms = duration / 1000000
| fieldsAdd is_error = loglevel == "ERROR"
```

### fieldsKeep
Keep only specified fields (no transformation).

```dql
fetch logs
| fieldsKeep timestamp, content, loglevel
```

### fieldsRemove
Remove specific fields.

```dql
fetch logs
| fieldsRemove internal_id, trace_id
```

### fieldsRename
Rename fields.

```dql
fetch logs
| fieldsRename log_level = loglevel, message = content
```

### fieldsFlatten
Flatten nested records.

```dql
fetch bizevents
| parse Response, "JSON:json"
| fieldsFlatten json, prefix:"response."
```

---

## Aggregation Commands

### summarize
Aggregate records with grouping.

```dql
summarize <aggregation> [, <aggregation>...], by:{<group_fields>}
```

**Aggregation functions:**

| Function | Description |
|----------|-------------|
| `count()` | Count records |
| `countIf(condition)` | Conditional count |
| `sum(field)` | Sum values |
| `avg(field)` | Average |
| `min(field)` | Minimum |
| `max(field)` | Maximum |
| `median(field)` | Median (50th percentile) |
| `percentile(field, n)` | nth percentile |
| `stddev(field)` | Standard deviation |
| `variance(field)` | Variance |
| `countDistinct(field)` | Unique count (exact) |
| `countDistinctApprox(field)` | Unique count (approx) |
| `collectArray(field)` | Collect into array |
| `collectDistinct(field)` | Collect unique values |
| `takeFirst(field)` | First value |
| `takeLast(field)` | Last value |
| `takeAny(field)` | Any value |
| `takeMin(field)` | Value at min |
| `takeMax(field)` | Value at max |

**Examples:**
```dql
// Count by host
fetch logs
| summarize log_count=count(), error_count=countIf(loglevel=="ERROR"), by:{dt.entity.host}

// Statistics
fetch spans
| summarize avg_duration=avg(duration), p95=percentile(duration, 95), by:{service.name}

// Multiple aggregations
fetch bizevents
| summarize {sum(amount), count(), avg(amount)}, by:{product_category}
```

### fieldsSummary
Get cardinality summary of fields.

```dql
fetch logs
| fieldsSummary loglevel, dt.entity.host
```

---

## Timeseries Commands

### timeseries
Query and aggregate metrics (starting command).

```dql
timeseries <aggregation>(metric_key) [, by:] [, filter:] [, interval:] [, default:]
```

**Aggregations:** `avg`, `sum`, `min`, `max`, `count`, `percentile`

```dql
// CPU usage by host
timeseries avg(dt.host.cpu.usage), by:dt.entity.host, interval:5m

// Multiple metrics
timeseries cpu=avg(dt.host.cpu.usage), mem=avg(dt.host.memory.usage), interval:1h

// With filter
timeseries avg(dt.host.cpu.usage), filter:in(dt.entity.host, "HOST-1", "HOST-2")

// Fill gaps with default
timeseries sum(dt.service.request.count), default:0, interval:1m
```

### makeTimeseries
Create timeseries from event data.

```dql
fetch logs
| makeTimeseries count(), by:{loglevel}, interval:5m
```

```dql
fetch bizevents
| makeTimeseries total=sum(amount), avg_amount=avg(amount), by:{region}, interval:1h
```

---

## Parse Command

Extract data from string fields using patterns.

```dql
parse <field>, "<pattern>"
```

### Pattern Types

**JSON parsing:**
```dql
fetch logs
| parse content, "JSON:parsed"
| fieldsAdd error_code = parsed[error][code]
```

**Key-value parsing:**
```dql
fetch logs
| parse content, "KVP:kvp"
```

**Pattern matchers:**
| Matcher | Description |
|---------|-------------|
| `LD` | Any characters (lazy) |
| `WORD` | Word characters |
| `INT` | Integer |
| `LONG` | Long integer |
| `DOUBLE` | Floating point |
| `IPADDR` | IP address |
| `SPACE` | Whitespace |
| `EOL` | End of line |
| `EOS` | End of string |

**Example with matchers:**
```dql
fetch logs
| parse content, "LD IPADDR:ip ':' LONG:port SPACE LD 'status=' INT:status"
```

**Regex parsing:**
```dql
fetch logs
| parse content, "REGEX:(?<ip>\\d+\\.\\d+\\.\\d+\\.\\d+):(?<port>\\d+)"
```

---

## Join and Lookup

### lookup
Add fields from lookup table.

```dql
fetch bizevents
| lookup [load "/lookups/products"], sourceField:product_id, lookupField:id
```

### join
Join two data sources.

```dql
fetch logs
| join [fetch dt.entity.host], on:{dt.entity.host}
```

**Join types:**
- Default: inner join
- `leftOuter:true` - Left outer join

```dql
fetch spans
| join [fetch dt.entity.service], on:{dt.entity.service}, leftOuter:true
```

### append
Combine results from multiple queries.

```dql
fetch logs, from:now()-1h
| filter loglevel == "ERROR"
| append [
    fetch logs, from:now()-1h
    | filter loglevel == "WARN"
  ]
```

---

## Functions Reference

### String Functions
| Function | Description |
|----------|-------------|
| `concat(s1, s2, ...)` | Concatenate strings |
| `lower(s)` | Lowercase |
| `upper(s)` | Uppercase |
| `trim(s)` | Remove whitespace |
| `substring(s, start, length)` | Extract substring |
| `indexOf(s, substr)` | Find position |
| `replace(s, old, new)` | Replace substring |
| `contains(s, substr)` | Check if contains |
| `startsWith(s, prefix)` | Check prefix |
| `endsWith(s, suffix)` | Check suffix |
| `split(s, delimiter)` | Split to array |
| `matches(s, regex)` | Regex match |

### Timestamp Functions
| Function | Description |
|----------|-------------|
| `now()` | Current timestamp |
| `formatTimestamp(ts, format:)` | Format timestamp |
| `getYear(ts)` | Extract year |
| `getMonth(ts)` | Extract month (1-12) |
| `getDayOfMonth(ts)` | Extract day |
| `getDayOfWeek(ts)` | Extract day of week |
| `getHour(ts)` | Extract hour |
| `getMinute(ts)` | Extract minute |
| `toTimestamp(s)` | Parse timestamp |
| `toUnixSeconds(ts)` | Convert to Unix seconds |

**Format patterns:**
```dql
formatTimestamp(timestamp, format:"yyyy-MM-dd HH:mm:ss")
formatTimestamp(timestamp, format:"EE")  // Day name
```

### Math Functions
| Function | Description |
|----------|-------------|
| `abs(n)` | Absolute value |
| `ceil(n)` | Round up |
| `floor(n)` | Round down |
| `round(n, decimals)` | Round |
| `sqrt(n)` | Square root |
| `pow(base, exp)` | Power |
| `log(n)` | Natural log |
| `log10(n)` | Base-10 log |

### Array Functions
| Function | Description |
|----------|-------------|
| `array(a, b, c)` | Create array |
| `arraySize(arr)` | Array length |
| `arrayFirst(arr)` | First element |
| `arrayLast(arr)` | Last element |
| `arrayConcat(arr1, arr2)` | Concatenate |
| `arrayDistinct(arr)` | Unique values |
| `arrayFilter(arr, condition)` | Filter array |

### Conditional Functions
| Function | Description |
|----------|-------------|
| `if(cond, then, else)` | Conditional |
| `coalesce(a, b, c)` | First non-null |
| `isNull(val)` | Check null |
| `isNotNull(val)` | Check not null |

### Casting Functions
| Function | Description |
|----------|-------------|
| `toString(val)` | Convert to string |
| `toLong(val)` | Convert to long |
| `toDouble(val)` | Convert to double |
| `toBoolean(val)` | Convert to boolean |
| `toTimestamp(val)` | Convert to timestamp |
| `toDuration(val)` | Convert to duration |

---

## Operators

### Comparison
| Operator | Description |
|----------|-------------|
| `==` | Equal |
| `!=` | Not equal |
| `<`, `>` | Less/Greater than |
| `<=`, `>=` | Less/Greater or equal |

### Logical
| Operator | Description |
|----------|-------------|
| `and` | Logical AND |
| `or` | Logical OR |
| `not` | Logical NOT |

### Arithmetic
| Operator | Description |
|----------|-------------|
| `+`, `-`, `*`, `/` | Basic math |
| `%` | Modulo |

### Membership
```dql
// In list
filter status in(200, 201, 204)

// Not in list
filter status not in(500, 502, 503)
```

---

## Data Types

| Type | Description | Example |
|------|-------------|---------|
| `string` | Text | `"hello"` |
| `long` | 64-bit integer | `42` |
| `double` | Floating point | `3.14` |
| `boolean` | True/false | `true` |
| `timestamp` | Date/time | `2024-01-01T00:00:00Z` |
| `duration` | Time span | `5m`, `1h`, `1d` |
| `array` | List | `array(1, 2, 3)` |
| `record` | Nested object | `record(a=1, b=2)` |
| `ip` | IP address | `192.168.1.1` |

---

## Best Practices

### Performance
1. **Filter early**: Apply filters as early as possible
2. **Limit fields**: Use `fields` to select only needed columns
3. **Use scanLimitGBytes**: Limit data scan for large queries
4. **Avoid `*` in fields**: Be explicit about needed fields
5. **Use samplingRatio**: For exploratory queries on large datasets

### Query Patterns

**Error rate calculation:**
```dql
fetch spans, from:now()-1h
| summarize 
    total=count(), 
    errors=countIf(status.code != 0),
    error_rate=100.0 * countIf(status.code != 0) / count(),
    by:{service.name}
```

**Top N pattern:**
```dql
fetch logs
| summarize count(), by:{dt.entity.host}
| sort `count()` desc
| limit 10
```

**Time bucketing:**
```dql
fetch bizevents
| fieldsAdd hour = getHour(timestamp)
| summarize count(), by:{hour}
| sort hour asc
```

**Null handling:**
```dql
fetch logs
| fieldsAdd safe_value = coalesce(optional_field, "default")
| filter isNotNull(required_field)
```

**Percentile comparison:**
```dql
fetch spans
| summarize
    p50=percentile(duration, 50),
    p90=percentile(duration, 90),
    p99=percentile(duration, 99),
    by:{service.name}
```

---

## Query Costs & Optimization

### DDU (Davis Data Units) Pricing

DQL queries are billed based on **data scanned** (not data returned).

**Cost Formula:**
```
(GB of uncompressed data scanned) × 1.70 DDU = DDUs consumed
```

**Or direct pricing:**
```
(GiB scanned) × (price per GiB from rate card) ≈ $0.0035/GiB
```

**What triggers DDU consumption:**
- Executing DQL queries in Logs & Events viewer
- Dashboard tiles with DQL queries
- API calls using `queryExecutionClient.queryExecute()`
- App Functions executing DQL

**Optimizations applied automatically:**
- ✅ 98% discount on irrelevant data identified by query optimizer
- ✅ Compression and intelligent indexing
- ✅ Early filtering reduces scan volume

**Pricing Models:**
1. **Retain with Included Queries**: Fixed cost, queries included for 35 days (recommended)
2. **Usage-based**: Pay per query, retention up to 10 years

### Query Optimization Strategies

**1. Filter Early and Often**
```dql
-- BAD: Filters after aggregation
fetch logs, from:now()-24h
| summarize count(), by:{loglevel}
| filter loglevel == "ERROR"

-- GOOD: Filter before aggregation (scans less data)
fetch logs, from:now()-24h
| filter loglevel == "ERROR"
| summarize count()
```

**2. Limit Time Windows**
```dql
-- BAD: Large time window
fetch logs, from:now()-30d

-- GOOD: Specific time range
fetch logs, from:now()-1h, to:now()
```

**3. Use Specific Filters in WHERE Clauses**
```dql
-- Optimize with server-side filtering
fetch dt.entity.service
| filter tags contains "app:production"
| filter serviceType == "WEB_SERVICE"
```

**4. Leverage scanLimitGBytes**
```dql
-- Prevent runaway costs on exploratory queries
fetch logs, from:now()-7d, scanLimitGBytes:50
| filter contains(content, "error")
```

**5. Use Dedicated Endpoints**
```dql
-- BAD: Fetch all data to extract filter options
fetch dt.entity.service, limit:5000
| fields entity.name, tags
-- Client-side: extract unique values

-- GOOD: Dedicated query with higher limit for options only
fetch dt.entity.service, limit:10000
| fields entity.name, equipe, produit_it
-- 1 query vs 2, more complete results
```

---

## Advanced Entity Queries

### Tag Inheritance Pattern

Services inherit tags from Process Groups when service-level tags are empty.

```dql
fetch dt.entity.service
| fieldsAdd tags_str = toString(tags)
| fieldsAdd pg_id = runs_on[dt.entity.process_group]
| fieldsAdd pg_name = entityName(pg_id, type:"dt.entity.process_group")
| parse tags_str (
    extraction 7 tags,
    LD 'equipe=' data:equipe_svc (using LD optional) LD,
    LD 'produit_it=' data:produit_it_svc (using LD optional) LD,
    LD 'code_composant=' data:code_composant_svc (using LD optional) LD
  )
| lookup [
    fetch dt.entity.process_group
    | fieldsAdd tags_str_pg = toString(tags)
    | parse tags_str_pg (
        extraction 7 tags,
        LD 'equipe=' data:equipe_pg (using LD optional) LD,
        LD 'produit_it=' data:produit_it_pg (using LD optional) LD
      )
    | fields id, equipe_pg, produit_it_pg
  ], sourceField:pg_id, lookupField:id
| fieldsAdd equipe = if(isNotNull(equipe_svc) and equipe_svc != "", equipe_svc, equipe_pg)
| fieldsAdd produit_it = if(isNotNull(produit_it_svc) and produit_it_svc != "", produit_it_svc, produit_it_pg)
```

**Pattern breakdown:**
1. **Extract service tags** using `parse tags_str`
2. **Get Process Group ID** via `runs_on` relationship
3. **Lookup PG tags** with nested `fetch` + `parse`
4. **Merge with priority**: Service tags override PG tags if present

### Service Dependency Queries

```dql
-- Get services with their dependencies
fetch dt.entity.service
| fieldsAdd caller_ids = called_by[dt.entity.service]
| fieldsAdd callee_ids = calls[dt.entity.service]
| fields entity.name, caller_ids, callee_ids

-- Flatten dependencies into edges
fetch dt.entity.service
| fieldsAdd callee_ids = calls[dt.entity.service]
| expand callee_ids
| fields source=id, target=callee_ids
```

### Dynamic Filtering with Variables

```dql
-- Build dynamic WHERE clause
fetch dt.entity.service
| filter isNotNull(equipe) and equipe == "TeamA"
| filter isNotNull(environnement) and environnement == "production"
| filter serviceType in("WEB_SERVICE", "MESSAGING_SERVICE")
```

**Server-side optimization**: Filters applied during fetch reduce data transfer.

### Aggregating Unique Values for Filters

```dql
-- Extract all unique filter options
fetch dt.entity.service, limit:10000
| fields entity.name, equipe, produit_it, code_composant, departement
| summarize
    equipes = collectDistinct(equipe),
    produits = collectDistinct(produit_it),
    composants = collectDistinct(code_composant),
    departements = collectDistinct(departement)
```

**Use case**: Populate filter dropdowns without fetching full topology.

---

## Real-World Query Examples

### Example 1: Service Topology with Filters

```dql
fetch dt.entity.service
| fieldsAdd tags_str = toString(tags)
| fieldsAdd serviceType, databaseVendor, databaseHostNames
| fieldsAdd caller_ids = called_by[dt.entity.service]
| fieldsAdd callee_ids = calls[dt.entity.service]
| fieldsAdd pg_id = runs_on[dt.entity.process_group]
| fieldsAdd pg_name = entityName(pg_id, type:"dt.entity.process_group")
| parse tags_str (
    extraction 7 tags,
    LD 'equipe=' data:equipe_svc (using LD optional) LD,
    LD 'produit_it=' data:produit_it_svc (using LD optional) LD,
    LD 'environnement=' data:environnement_svc (using LD optional) LD
  )
| lookup [
    fetch dt.entity.process_group
    | fieldsAdd tags_str_pg = toString(tags)
    | parse tags_str_pg (
        extraction 7 tags,
        LD 'equipe=' data:equipe_pg (using LD optional) LD
      )
    | fields id, equipe_pg
  ], sourceField:pg_id, lookupField:id
| fieldsAdd equipe = if(isNotNull(equipe_svc) and equipe_svc != "", equipe_svc, equipe_pg)
| filter isNotNull(equipe) and equipe == "TeamA"
| sort entity.name
| limit 5000
```

**Optimizations:**
- Filter after enrichment to get complete data
- Limit to 5000 to control costs
- Server-side tag parsing reduces client processing

### Example 2: Filter Options Query

```dql
fetch dt.entity.service, limit:10000
| fieldsAdd tags_str = toString(tags)
| fieldsAdd pg_id = runs_on[dt.entity.process_group]
| fieldsAdd pg_name = entityName(pg_id, type:"dt.entity.process_group")
| parse tags_str (extraction 7 tags)
| lookup [
    fetch dt.entity.process_group
    | fieldsAdd tags_str_pg = toString(tags)
    | parse tags_str_pg (extraction 7 tags)
    | fields id, equipe_pg, produit_it_pg
  ], sourceField:pg_id, lookupField:id
| fieldsAdd equipe = coalesce(equipe_svc, equipe_pg)
| fields entity.name, equipe, produit_it, code_composant, departement, environnement
```

**Benefits:**
- 1 query instead of 2 (50% cost reduction)
- Limit 10000 vs 5000 (more complete data)
- No dependency data (lighter payload)

### Example 3: Monitor Query Costs

```dql
-- Track DQL query execution and costs
fetch dt.system.events
| filter matchesValue(event.kind, "QUERY_EXECUTION_EVENT")
| fieldsAdd
    query_text = event.query,
    scan_gb = event.scannedBytes / 1073741824,
    duration_sec = event.duration / 1000000000,
    ddu_cost = scan_gb * 1.70
| summarize
    total_queries = count(),
    total_scan_gb = sum(scan_gb),
    total_ddu = sum(ddu_cost),
    avg_duration = avg(duration_sec),
    by:{getHour(timestamp)}
| sort getHour desc
```

**Use**: Cost monitoring dashboard to track DQL usage and optimize expensive queries.
