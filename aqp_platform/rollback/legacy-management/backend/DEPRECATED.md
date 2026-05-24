# `management/backend/` — DEPRECATED (Phase 7)

> **Status**: Sunset. The AQP refactor introduces an isolated control-plane micro-project that absorbs every responsibility this FastAPI backend currently owns.

## Why

The AQP control-plane refactor (see
`agentic_quant_platform/docs/architecture/decisions/005-separated-control-plane.md`
in the sibling AQP repository) stands up a standalone `aqp_control_plane/`
micro-project that:

- Speaks five infrastructure backends (`docker_compose`, `kubernetes`, `aws`, `azure`, `gcp`) via a single `InfrastructureProvider` ABC
- Re-validates every JWT independently against Auth0 JWKS (zero-trust)
- Filters every list endpoint through `filter_resources(items, payload)` so users only see resources in their `https://aqp.internal/resources` claim
- Writes an append-only `workload_runs` audit row BEFORE every mutating action

`management/backend/` overlaps with all of the above. Maintaining both planes diverges security policy, RBAC scopes, and audit semantics.

## Migration plan

| Endpoint here                          | New home in `aqp_control_plane`            | Status     |
| -------------------------------------- | ------------------------------------------ | ---------- |
| `GET  /api/cluster/{pods,services,...}`| `GET  /manage/deployments`                 | Pending    |
| `POST /api/cluster/.../exec`           | `POST /manage/deployments/{id}/exec`       | Implemented |
| `GET  /api/cluster/.../logs/stream`    | `GET  /manage/deployments/{id}/logs`       | Implemented |
| `GET  /api/kafka/*`                    | `data.streaming.*` MCP tools (AQP)         | Mature     |
| `GET  /api/flink/*`                    | `data.streaming.*` MCP tools (AQP)         | Mature     |
| `GET  /api/mlflow/*`                   | `data.mlflow.*` MCP tools (AQP)            | Mature     |
| `GET  /api/observability/*`            | `GET  /manage/telemetry/snapshot`          | Implemented |
| `GET  /api/traces/*`                   | AQP Jaeger proxy at `aqp/api/routes/...`   | Mature     |

## What to do today

If you're maintaining this code:

1. **Don't add new routes here.** Add them to `aqp_control_plane/src/aqp_cp/api/routers/`.
2. **Don't add new auth providers here.** Use `aqp_platform_core.auth.JwtValidator` instead.
3. **For cluster-side ops** (pod exec, log tail), prefer the AQP `KubernetesAdapter` (hard rule 28) which `aqp_control_plane.providers.kubernetes` already wraps.
4. **For operator UI integration**, the canonical Python client is now
   `rpi_k8s_sdk.AqpControlPlaneClient` — it points at the
   `aqp_control_plane` HTTP API by default.
5. **For command-line operations**, use the AQP CLI:
   `aqp cp ...` (for day-2 workload/cluster operations) and
   `aqp deploy ...` (for Terraform day-0 provisioning).

## Removal timeline

- **Now**: deprecation banner (this file)
- **Next release**: route handlers add `Deprecation: true` + `Link: <new-url>; rel="successor-version"` headers
- **Following release**: routes return `410 Gone` with a structured pointer to the successor URL
- **After 90 days at 410 Gone**: deletion

Track follow-up work under the `phase7-absorption` label in the AQP repo.
