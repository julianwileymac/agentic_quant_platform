---
title: 'Local platform overlay'
summary: 'The rpi `kubernetes/` tree stays untouched — these are *copies*, not relocations. AQP attaches to either the local services or the cluster through the [`KubernetesAdapter`](../../concepts/infrastructure/kubernetes-adapter.md) abst...'
owner: infra-team
last_reviewed: 2026-05-25
audience: both
---

# Local platform overlay

Audience: a developer who wants to run AQP **standalone**, without
attaching to the rpi_kubernetes cluster. The platform overlay
(`aqp_platform/compose/docker-compose.platform.yml`) brings the data + observability
services AQP code expects into the local compose stack.

The rpi `kubernetes/` tree stays untouched — these are *copies*, not
relocations. AQP attaches to either the local services or the cluster
through the [`KubernetesAdapter`](../../concepts/infrastructure/kubernetes-adapter.md) abstraction.

## Compose-up matrix

| Goal | Command |
| --- | --- |
| Just the AQP API + workers | `docker compose up -d` |
| AQP + visualization stack (Trino, Polaris, Superset, Dagster, Dask, Ray) | `docker compose -f aqp_platform/compose/docker-compose.yml -f aqp_platform/compose/docker-compose.viz.yml --profile visualization up -d` |
| Full local platform parity (adds Apicurio + real Airbyte + DataHub + Loki + Vector + VictoriaMetrics) | `docker compose -f aqp_platform/compose/docker-compose.yml -f aqp_platform/compose/docker-compose.viz.yml -f aqp_platform/compose/docker-compose.platform.yml --profile visualization --profile platform up -d` |

The platform overlay also activates the `visualization` profile's
services it depends on (Polaris, Trino, Dagster). Don't pass `--profile
platform` alone — the AQP webui still depends on Superset from the
viz overlay.

## Services added by the platform overlay

| Service | Container | Default host port | Wires into |
| --- | --- | --- | --- |
| `apicurio` (Schema Registry) | `aqp-apicurio` | `8090 -> 8080` | `AQP_SCHEMA_REGISTRY_URL` already supports the URL knob |
| `airbyte-db` | `aqp-airbyte-db` | (internal) | Postgres backing for real Airbyte |
| `airbyte-server-real` | `aqp-airbyte-server-real` | `8005 -> 8001` | Real Airbyte API (the dev stub at `airbyte-server` keeps running on `:8002`) |
| `airbyte-webapp` | `aqp-airbyte-webapp` | `8001 -> 80` | UI for real Airbyte |
| `datahub-gms` | `aqp-datahub-gms` | `8081 -> 8080` | `AQP_DATAHUB_GMS_URL=http://datahub-gms:8080` |
| `datahub-frontend` | `aqp-datahub-frontend` | `9002 -> 9002` | DataHub UI |
| `loki` | `aqp-loki` | `3100 -> 3100` | Log aggregation; OTel collector + agents push here |
| `vector` | `aqp-vector` | (none) | Tails Docker container logs and ships to Loki |
| `victoriametrics` | `aqp-victoriametrics` | `8428 -> 8428` | Long-term metrics; scrapes the existing OTel collector + AQP API |

## Sub-profiles (documented but not enabled by default)

The plan keeps these out of the default platform set because the user
opted out of "full parity":

- `platform-rag` — RAGFlow + Milvus stack (heavy; pulls a vector DB).
- `platform-jh` — JupyterHub.

Add them yourself if needed by extending `aqp_platform/compose/docker-compose.platform.yml`
or shipping an alongside `docker-compose.platform.<profile>.yml`.

## Smoke test sequence

1. `docker compose -f aqp_platform/compose/docker-compose.yml -f aqp_platform/compose/docker-compose.viz.yml -f aqp_platform/compose/docker-compose.platform.yml --profile visualization --profile platform up -d`
2. `curl http://localhost:8428/-/ready` — VictoriaMetrics
3. `curl http://localhost:3100/ready` — Loki
4. `curl http://localhost:8081/health` — DataHub GMS
5. `curl http://localhost:8090/apis` — Apicurio
6. `curl http://localhost:8005/api/v1/health` — real Airbyte
7. `docker compose ps` — every service should be healthy or running

## Where the rpi cluster fits in

When `AQP_CLUSTER_MGMT_URL` is set, the
[`RpiClusterAdapter`](../../concepts/infrastructure/kubernetes-adapter.md#rpiclusteradapter) auto-promotes
and AQP forwards Kafka admin + Flink session-job + alphavantage stream
operations to the homelab management API. Setting both attach paths
side-by-side is fine — AQP routes the call wherever the active
adapter says.

## Cleanup

```
docker compose -f aqp_platform/compose/docker-compose.yml -f aqp_platform/compose/docker-compose.viz.yml -f aqp_platform/compose/docker-compose.platform.yml --profile visualization --profile platform down
```

Volumes are preserved; pass `-v` to wipe them.
