# Phoenix

Phase 2d of the AQP infra-expansion plan ships self-hosted Arize
Phoenix in the `aqp-observability` namespace for LLM / agent / RAG
observability. Phoenix sits NEXT TO the existing OTel pipeline;
infra spans (FastAPI / Celery / SQLAlchemy / httpx / Redis / Kafka)
keep flowing to the OTel Collector + Tempo, while the OpenInference
auto-instrumentations on top tag agent / LLM / RAG spans with
`openinference.span.kind` so the OTel gateway routes them to
Phoenix.

## Bootstrap

[`aqp/observability/phoenix.py`](../aqp/observability/phoenix.py)
exposes:

- `configure_phoenix_for_app()` — called from
  [`aqp/api/main.py`](../aqp/api/main.py) after `configure_tracing()`.
- `configure_phoenix_for_celery()` — called from
  [`aqp/tasks/celery_app.py`](../aqp/tasks/celery_app.py)'s
  `worker_process_init` signal so each worker has its own provider.
- `using_session_id(session_id)` / `using_attributes(**kwargs)` —
  Phoenix context helpers (no-op when the package is missing).

## Auto-instrumentation

Phoenix's `register(auto_instrument=True)` activates the
OpenInference instrumentations for OpenAI, LiteLLM, Anthropic,
LangChain, LlamaIndex, CrewAI, DSPy, AutoGen, and others. AQP
agent code that goes through the canonical
[`router_complete`](../aqp/llm/providers/router.py) path (rule 2)
emits the right spans automatically.

## Kubernetes manifests

[`aqp_platform/deployments/kubernetes/observability/phoenix/`](../aqp_platform/deployments/kubernetes/observability/phoenix/):

- `postgres.yaml` — dedicated Postgres backend
  (`phoenix-postgresql.aqp-observability.svc.cluster.local:5432`).
- `secret.yaml` — `phoenix-db-secret` placeholder.
- `deployment.yaml` — `arizephoenix/phoenix:latest`, ports 6006 +
  4317, init container `phoenix db migrate`.
- `service.yaml` — ClusterIP exposing `ui-http` (6006) + `otlp-grpc`
  (4317).
- `servicemonitor.yaml` — kube-prometheus-stack discovery.

Install:

```bash
PHOENIX_PASSWORD=$(openssl rand -base64 24) \
  ./scripts/cluster_install/install-phoenix.sh
```

## DataMCP tools

| Tool | Purpose |
|---|---|
| `data.observability.phoenix.list_projects` | Discovery. |
| `data.observability.phoenix.get_trace` | Fetch a trace by id. |
| `data.observability.phoenix.annotate_span` | Attach an evaluator / human verdict (write). |

## Topology entry

`services > phoenix` (cluster `observability.ai`, namespace
`aqp-observability`). Endpoints: `ui`, `otlp_http`, `otlp_grpc`.
