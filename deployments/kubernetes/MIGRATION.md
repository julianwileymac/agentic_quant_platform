# Shared infrastructure migration: rpi_kubernetes -> agentic_quant_platform (HISTORICAL)

> **Status: complete. Historical reference only.**
>
> AQP is now self-contained: every shared cluster service runs in an
> AQP-owned `aqp-*` namespace under
> `agentic_quant_platform/deployments/kubernetes/`. `rpi_kubernetes`
> only owns RPi cluster bootstrap, the `julianwiley-portal` stack,
> and the rollback-only `legacy-management/` shell.
>
> This document is retained only to explain why the layout looks the
> way it does. Do not use it as a rollout runbook for new
> deployments - see
> [aqp_docs/operations/kubernetes-deploy.md](../../aqp_docs/operations/kubernetes-deploy.md)
> instead.

## Final ownership

| Domain | Path | Notes |
| --- | --- | --- |
| Streaming (Strimzi Kafka, Schema Registry, Flink, Redpanda, Redpanda Connect) | `deployments/kubernetes/base-services/{kafka-strimzi,schema-registry,flink,redpanda,redpanda-connect}/` (`aqp-streaming`) | Operators (Strimzi, Redpanda) installed via `scripts/cluster_install/` |
| Time-series (QuestDB) | `deployments/kubernetes/base-services/questdb/` (`aqp-timeseries`) | |
| Lakehouse (Polaris, Hudi, Spark Operator) | `deployments/kubernetes/base-services/polaris/` + `deployments/kubernetes/mlops/{hudi,spark-operator}/` (`aqp-lakehouse` / `aqp-mlops`) | Iceberg canonical, Hudi additive (rule 46) |
| Data services (Postgres, Redis, MinIO, ChromaDB, Milvus, DataHub) | `deployments/kubernetes/base-services/{postgres-shared,redis-shared,minio,chromadb,milvus,datahub}/` (`aqp-data-services`) | AQP DSNs in `aqp-config.yaml` resolve to `aqp-data-services` |
| ELT (Airbyte, RAGFlow, JupyterHub, Dask/Ray) | `deployments/kubernetes/base-services/{airbyte,ragflow,jupyterhub,dask-ray}/` (`aqp-elt`) | |
| MLOps (MLflow, Argo Workflows + Events, BentoML, KServe, Dagster, AQP bots, Pipelines) | `deployments/kubernetes/mlops/{mlflow,argo-workflows,argo-events,bentoml,kserve,dagster,bots,pipelines}/` (`aqp-mlops` / `aqp-bots`) | `bots/` is opt-in (Argo dependency) |
| Observability (kube-prometheus-stack, Grafana, OTel Operator + Collector, Tempo, Loki, Phoenix, Vector, VictoriaMetrics, Jaeger) | `deployments/kubernetes/observability/{kube-prometheus-stack,opentelemetry-operator,opentelemetry-collector-gateway,otel-collector,phoenix,loki,vector,victoriametrics,jaeger}/` (`aqp-observability`) | Tempo lives inside the kube-prometheus-stack release |
| Edge (cloudflared-aqp) | `deployments/kubernetes/edge/cloudflared-aqp/` (`aqp-edge`) | Tunnel `aqp-fund-edge` (`0cd12089-38ee-4dfb-95ba-65d2daa7b88b`) routes `aqp.fund`, `api.aqp.fund`, `manage.aqp.fund` |

## What still lives in rpi_kubernetes

- Cluster bootstrap: `kubernetes/bootstrap/` (deleted now that all
  AQP-related helm scripts moved to
  `agentic_quant_platform/scripts/cluster_install/`),
  `bootstrap/scripts/` (RPi-only: prepare-rpi, install_k3s,
  k3s-health-check, mount-USB-SSD, etc.), `kubernetes/policies/finops/`,
  `kubernetes/storage/`.
- `kubernetes/base-services/portal/` - `julianwiley-portal` Next.js
  app + portal-scoped Prometheus + `web`-namespace NetworkPolicy.
- `kubernetes/base-services/cloudflared/` - portal-only Cloudflare
  tunnel for `julianwiley.com`.
- `kubernetes/legacy-management/` + `kubernetes/base-services/management/` -
  rollback-only shell pinned to `:v1-final`.

## Domain isolation

| Domain | Cert / TLS | IdP | Namespace | Cloudflare tunnel |
| --- | --- | --- | --- | --- |
| `aqp.fund`, `api.aqp.fund`, `manage.aqp.fund` | cert-manager + Let's Encrypt | Auth0 (`aqp-fund.us.auth0.com`) | `aqp` / `aqp-admin` | `cloudflared-aqp` (`aqp-edge`) |
| `julianwiley.com`, `www.julianwiley.com` | Cloudflare edge TLS | Microsoft Entra (NextAuth) | `web` | `cloudflared` (`edge`) (rpi_kubernetes) |

Different tunnels, different cert chains, different IdPs, disjoint
namespaces, disjoint network policies. There is no cross-coupling.
