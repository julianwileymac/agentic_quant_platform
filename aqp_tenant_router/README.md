# aqp-tenant-router

Cell-routing decision service for the Agentic Quant Platform.
Phase 3 §6.4 of [RESTRUCTURING_PLAN.md](../RESTRUCTURING_PLAN.md).

## What it does

The router answers one question on the hot path between Envoy
(`aqp-edge`) and the per-cell FastAPI instances:

> Given a JWT (with `sub`, `workspace_id`, optionally `tenant_id`),
> which deployment cell should this request route to?

The answer is a tuple:

```
(cell_id, region, k8s_namespace, routes)
```

Envoy uses the `cell_id` to either inject an `x-aqp-cell` header
and forward to the matching upstream cluster, or to short-circuit
with a 503 when no cell can serve the tenant.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`  | `/healthz` | Liveness probe (always 200 OK once the cache is hydrated). |
| `GET`  | `/readyz` | Readiness: 200 when the cell cache is hydrated; 503 otherwise. |
| `POST` | `/resolve` | Direct lookup. Body: `{"user_id": "...", "workspace_id": "...", "tenant_id": "...?"}`. Response: `{"cell_id": "...", "region": "...", "k8s_namespace": "...", "routes": {...}}`. |
| `POST` | `/ext_authz/v3/check` | Envoy ext_authz HTTP contract. Reads inbound headers + body, returns `{"status": {"code": 0}}` with an `x-aqp-cell` header on success, or `{"status": {"code": 7}}` (PermissionDenied) on failure. |

## Build

```bash
pip install -e .[dev]
aqp-tenant-router --host 0.0.0.0 --port 8080
```

Docker (Chainguard Wolfi per Phase 2 §5.1):

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file aqp_platform/build/docker/aqp-tenant-router/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-tenant-router:dev \
  .
```

## Local smoke test

```bash
# Hydrate the cache from a local control plane:
export AQP_TENANT_ROUTER_CONTROL_PLANE_URL=http://localhost:9000
aqp-tenant-router --host 127.0.0.1 --port 8080 &

# Resolve a tenant:
curl -sS -XPOST http://127.0.0.1:8080/resolve \
     -H 'content-type: application/json' \
     -d '{"user_id": "u1", "workspace_id": "ws1", "tenant_id": "tenant_acme"}'
# {"cell_id": "cell-silo-reg-acme", "region": "us-east-1", "k8s_namespace": "cell-silo-reg-acme", "routes": {"api": "https://acme.silo-reg.aqp.fund", "ws": "wss://acme.silo-reg.aqp.fund/ws"}}
```

## Phase 3 status

- §6.4 step 1 (deploy in parallel with the Python proxy): the
  Dockerfile + K8s manifest land in this PR.
- §6.4 step 2 (DNS canary 10% traffic): the operator runbook at
  `aqp_docs/docs/how-to/cell-router-cutover.md` documents the
  steps; the DNS shift is a manual operator action.
- §6.4 step 5 (remove Python proxy): deferred to a follow-up PR
  per RESTRUCTURING_PLAN.md §6.6.
