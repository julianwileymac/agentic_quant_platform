# Streaming admin (Kafka, Flink, schema registry, producers)

Streaming admin lives in two layers:

1. **Native** — direct talk to the broker / Flink / schema registry
   from inside the AQP API container. Implemented by
   [`aqp.streaming.admin`](../aqp/streaming/admin/__init__.py)
   (Kafka via `confluent_kafka.admin.AdminClient`, Flink via REST +
   the `kubernetes` Python client for `FlinkSessionJob` CRUD,
   Apicurio via httpx).
2. **Cluster-management proxy** — a thin httpx wrapper around the
   `rpi_kubernetes` management backend at `/api/{kafka,flink,
   alphavantage}` (see
   [`aqp.services.cluster_mgmt_client`](../aqp/services/cluster_mgmt_client.py)).
   Proxies Strimzi user CRUD, generic deployment scale, and the
   Alpha-Vantage producer toggle that the cluster mgmt backend already
   owns.

The web UI calls **AQP routes** (`/streaming/*`,
`/cluster-mgmt/*`); each AQP route prefers native and falls back to
the proxy when the SDK is missing or the cluster-managed resource is
the source of truth.

## Settings

| Env var | Purpose |
| --- | --- |
| `AQP_KAFKA_ADMIN_BOOTSTRAP` | Override bootstrap for the native admin client. Defaults to `AQP_KAFKA_BOOTSTRAP`. |
| `AQP_KAFKA_ADMIN_SECURITY_PROTOCOL` / `AQP_KAFKA_ADMIN_SASL_*` | SASL config for the admin listener. |
| `AQP_KAFKA_ADMIN_SCHEMA_REGISTRY_URL` | Apicurio URL (Confluent ccompat shim). |
| `AQP_FLINK_REST_URL` | Flink REST root (`http://flink-jobmanager:8081`). |
| `AQP_FLINK_NAMESPACE` | Kubernetes namespace for `FlinkSessionJob` CRUD. |
| `AQP_FLINK_SESSION_CLUSTER_NAME` | Operator deployment to attach jobs to. |
| `AQP_FLINK_FACTOR_JAR_URI` / `AQP_FLINK_FACTOR_ENTRY_CLASS` | Defaults for `submit_factor_job`. |
| `AQP_CLUSTER_MGMT_URL` | Base URL of the rpi_kubernetes management API (`http://management.rpi.svc:8000/api`). |
| `AQP_CLUSTER_MGMT_TOKEN` | Bearer token for the proxy. |
| `AQP_STREAMING_PRODUCERS_NAMESPACE` | Default namespace for kubernetes-deployed producers. |

## REST surface

### `/streaming/kafka`

- `GET /topics`, `POST /topics`, `DELETE /topics/{name}`, `GET /topics/{name}`
- `GET /topics/{name}/messages?limit=100` — `aiokafka` consumer sample.
- `POST /topics/{name}/produce` — Kafka Bridge produce via the proxy.
- `GET /consumer-groups`, `GET /consumer-groups/{group}/lag`
- `GET /schema-registry/subjects`,
  `GET /schema-registry/subjects/{name}/versions/latest`,
  `POST /schema-registry/subjects/{name}/versions`

### `/streaming/flink`

- `GET /sessionjobs` / `POST /sessionjobs` / `GET|PATCH|DELETE /sessionjobs/{name}`
- `POST /sessionjobs/{name}/{activate,suspend,scale,savepoint}`
- `GET /jobs`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/exceptions`
- `POST /jobs/factor-export` — calls
  [`submit_factor_job`](../aqp/streaming/runtime.py) (renders a
  manifest from
  [`aqp/streaming/templates`](../aqp/streaming/templates/__init__.py)
  and applies it via the kubernetes client).

### `/streaming/producers`

CRUD over [`MarketDataProducerRow`](../aqp/persistence/models_producers.py)
plus lifecycle controls:

- `POST /{name}/{start,stop,scale,restart}`
- `GET /{name}/{status,logs,topics}`

The supervisor seeds the curated catalog
([`PRODUCER_CATALOG`](../aqp/streaming/producers/catalog.py)) on first
boot so the Producers page renders Alpha-Vantage / IBKR / Alpaca /
polygon / synthetic immediately.

### `/cluster-mgmt`

Re-exposes the rpi_kubernetes management endpoints:

- `/kafka/{topics,users,connectors,consumer-groups,schema-registry/subjects}`
- `/flink/{deployments,sessionjobs,jobs}`
- `/alphavantage/{stream,health}`

## Streaming ↔ dataset linkage

Every operation that creates a topic, deploys a Flink job, scales a
producer, or runs a manifest writes a
[`StreamingDatasetLink`](../aqp/persistence/models_streaming_links.py)
row. The graph is queryable per-dataset via
`GET /datasets/{id}/streaming-links` and is refreshed by the
[`refresh_links`](../aqp/tasks/streaming_link_tasks.py) Celery task,
which is also kicked off from
[`aqp.data.datahub.sync.sync_all`](../aqp/data/datahub/sync.py) after
a DataHub pull.

## Implementing `submit_factor_job`

`aqp/api/routes/factors.py` and `aqp/api/routes/ml.py` had been
referencing `submit_factor_job` for months without an implementation.
The data layer expansion adds the function in
[`aqp/streaming/runtime.py`](../aqp/streaming/runtime.py): it renders
a `FlinkSessionJob` from
[`aqp/streaming/templates`](../aqp/streaming/templates/__init__.py)
and applies it through
[`FlinkSessionJobK8s`](../aqp/streaming/admin/flink_admin.py). When
the kubernetes client is unavailable the function returns the
rendered manifest with `status: "unavailable"` so callers can fall
back to a manual `kubectl apply`.
