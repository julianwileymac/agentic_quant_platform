# Entity Graph And Service Control

AQP now treats the entity graph as the canonical relationship layer for
instruments, companies, datasets, pipeline assets, and service metadata.
Postgres remains the compatibility store for existing APIs, while Neo4j is
the graph backend when `AQP_GRAPH_STORE=neo4j`.

## Local Services

Start the local stack with the visualization overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.viz.yml --profile visualization up -d
```

Neo4j is part of the base compose file and is exposed on:

- Browser: `http://localhost:7474`
- Bolt: `bolt://localhost:7687`

Relevant env keys:

```bash
AQP_GRAPH_STORE=neo4j
AQP_NEO4J_URI=bolt://localhost:7687
AQP_NEO4J_USER=neo4j
AQP_NEO4J_PASSWORD=aqpneo4j
AQP_NEO4J_DATABASE=neo4j
AQP_ENTITY_GRAPH_SYNC_ENABLED=true
```

## Entity Sync

The active instrument cache reads from the existing `instruments` table and
upserts each instrument as a `security` entity with identifiers for
`vt_symbol`, ticker, and any instrument metadata identifiers.

Dataset registration for market-bar datasets links dataset versions to the
instrument entities they describe. Airbyte and Dagster metadata syncs also
write service nodes and relationships so the graph can show ingestion and
pipeline context around datasets.

Useful endpoints:

- `GET /registry/entities/graph`
- `GET /registry/entities/instruments/active`
- `POST /registry/entities/instruments/sync`
- `POST /registry/entities/instruments/load-template`

## Service Manager

The service manager aggregates health/config/logs for:

- Trino
- Polaris
- Iceberg
- Superset
- Airbyte
- Dagster
- Neo4j

Useful endpoints:

- `GET /service-manager/health`
- `GET /service-manager/{service}/health`
- `GET /service-manager/{service}/logs`
- `POST /service-manager/{service}/actions`

Lifecycle actions and logs are guarded by `AQP_SERVICE_CONTROL_ENABLED=true`
because they invoke Docker Compose from inside the API process.

## UI

- `/data/entity-graph` exposes the Neo4j-backed entity graph and active
  instrument list.
- `/data/services` exposes service health cards, guarded lifecycle actions,
  and log tails.
- `/workflows/data` includes Dagster assets, runs, schedules, and sensors.
