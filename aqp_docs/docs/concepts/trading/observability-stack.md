---
title: 'Observability stack'
summary: '```mermaid flowchart LR apps[AQP services + agents] subgraph aqpobs[aqp-observability] otelagent[OTel Agent DaemonSet] otelgw[OTel Gateway Deployment] prom[Prometheus] graf[Grafana] tempo[Tempo] loki[...'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# Observability stack

Phase 2c + 2d of the AQP infra-expansion plan stand up the AQP-owned
observability plane in the `aqp-observability` namespace. Everything
the cluster previously read from `rpi_kubernetes/observability/` is
re-homed here.

```mermaid
flowchart LR
    apps[AQP services + agents]
    subgraph aqpobs[aqp-observability]
      otelagent[OTel Agent DaemonSet]
      otelgw[OTel Gateway Deployment]
      prom[Prometheus]
      graf[Grafana]
      tempo[Tempo]
      loki[Loki]
      phoenix[Arize Phoenix]
      pgphx[(Phoenix Postgres)]
    end
    apps -- OTLP --> otelagent
    otelagent -- OTLP --> otelgw
    otelgw -- "AI spans (openinference.span.kind)" --> phoenix
    otelgw -- "infra spans" --> tempo
    otelgw -- "remote_write" --> prom
    otelgw -- "OTLP logs" --> loki
    phoenix --> pgphx
    graf -. "Prometheus + Loki + Tempo + QuestDB datasources" .- prom
    graf -. .- loki
    graf -. .- tempo
```

## Components

| Component | Folder | Replaces |
|---|---|---|
| kube-prometheus-stack | [observability/kube-prometheus-stack/](../aqp_platform/deployments/kubernetes/observability/kube-prometheus-stack/) | rpi `observability/prometheus/` |
| OpenTelemetry Operator | [observability/opentelemetry-operator/](../aqp_platform/deployments/kubernetes/observability/opentelemetry-operator/) | new |
| OTel Collector (gateway + agent) | [observability/opentelemetry-collector-gateway/](../aqp_platform/deployments/kubernetes/observability/opentelemetry-collector-gateway/) | rpi `observability/otel-collector/` |
| Phoenix | [observability/phoenix/](../aqp_platform/deployments/kubernetes/observability/phoenix/) | new |

## Routing rule (gateway)

The `transform/ai_route` processor in
[`collector-gateway.yaml`](../aqp_platform/deployments/kubernetes/observability/opentelemetry-collector-gateway/collector-gateway.yaml)
inspects every span and tags it with `aqp.ai_trace=true` when:

- `attributes["openinference.span.kind"] != nil`, or
- `attributes["llm.model_name"] != nil`, or
- `attributes["agent.name"] != nil`.

Two trace pipelines (`traces/ai`, `traces/infra`) split on that
attribute. Tail sampling preserves error traces + 100 % of AI
traces; everything else is sampled at 1 %.

## DataMCP tools

| Tool | Surface |
|---|---|
| `data.observability.prometheus.query` | Instant PromQL. |
| `data.observability.prometheus.query_range` | Range PromQL. |
| `data.observability.prometheus.list_alerts` | Active alerts. |
| `data.observability.grafana.list_dashboards` | Dashboard catalog. |
| `data.observability.grafana.export_dashboard` | Dashboard JSON. |
| `data.observability.phoenix.list_projects` | Phoenix projects. |
| `data.observability.phoenix.get_trace` | LLM / agent trace. |
| `data.observability.phoenix.annotate_span` | Write evaluator verdict. |

## Frontend

- [/admin/topology](../aqp_client/src/routes/admin/topology/page.tsx)
  — Phase 0 topology overview.
- (Phase 6 follow-up) `/admin/observability/{prometheus,grafana,phoenix,otel}`
  — domain-scoped admin pages.
