---
title: Cell-router cutover runbook
description: Phase 3 §6.4 runbook — deploy the Envoy cell router + aqp-tenant-router decision service, canary 10% / 50% / 100%, retire the Python FastAPI proxy.
sidebar_label: Cell-router cutover
---

# Cell-router cutover runbook

> Phase 3 §6 of
> [RESTRUCTURING_PLAN.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md).
> Covers the cutover from the single-container Python FastAPI cell
> proxy (in `aqp_client/`) to the Envoy + `aqp-tenant-router`
> two-component cell router. This runbook is the operator-facing
> companion to the deployment manifests at
> `aqp_platform/deployments/kubernetes/edge/`.

## Architecture (Phase 3 §6.4)

```
[ user / agent ]
       │ TLS
       ▼
[ Cloudflare Tunnel (aqp.fund) ]
       │
       ▼
[ aqp-edge — Envoy (HTTP-only) ]
       │  ext_authz callout
       │ ──────────────────────▶  [ aqp-tenant-router ]
       │                                │ /resolve
       │                                ▼
       │                          [ cells registry (control plane) ]
       │ ◀──────────────────── x-aqp-cell header
       │
       ▼  Route on x-aqp-cell:
[ aqp-cell-<id>-api  (FastAPI) ]
[ aqp-cell-<id>-workers (Celery, gVisor for agents) ]
[ aqp-cell-<id>-postgres ]   [ aqp-cell-<id>-minio ]
```

## Prerequisites

1. The four canonical AQP images (`aqp-api`, `aqp-worker`,
   `aqp-client`, `aqp-control-plane`) are running on the
   pre-Phase-3 single-namespace topology. The Phase 3 work runs
   IN PARALLEL until the canary completes — nothing is taken away
   from the running fleet.
2. The Alembic head is at `0083_audit_cell_id_column.py`. Verify:
   ```bash
   alembic current
   # expected: 0083_audit_cell_id_column (head)
   ```
3. The `cells` registry has at least one `state=active` cell
   row. Verify via the control plane:
   ```bash
   curl -sS https://manage.aqp.fund/manage/cells | jq '.data[].id'
   ```
4. The `aqp-edge` namespace exists and carries the
   `aqp.io/host-network-allowed: "true"` exception label per
   Phase 2 §5.4.

## Step 0 — Build the Phase 3 images

```bash
# aqp-edge (Envoy)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file aqp_platform/build/docker/aqp-edge/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-edge:v0.1.0 \
  --push .

# aqp-tenant-router (Python + uvloop)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file aqp_platform/build/docker/aqp-tenant-router/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-tenant-router:v0.1.0 \
  --push .
```

The Phase 2 §5.2 CI pipeline at
`.github/workflows/build-multi-arch.yml` will cosign-sign and
generate SBOMs for both images on the same tag.

## Step 1 — Deploy in parallel (week 6)

```bash
# Apply both Deployments + Services + PodDisruptionBudgets:
kubectl apply -k aqp_platform/deployments/kubernetes/edge/aqp-edge/
kubectl apply -k aqp_platform/deployments/kubernetes/edge/aqp-tenant-router/

# Verify the tenant-router hydrated the cells cache:
kubectl -n aqp-edge port-forward svc/aqp-tenant-router 18080:8080
curl -sS http://127.0.0.1:18080/readyz
# expected: {"status":"ok","cells":<n>}
```

DNS still points to the Python proxy. No user traffic flows to
`aqp-edge` yet.

## Step 2 — DNS canary 10% (week 7)

Cloudflare Workers + Load Balancer split the apex hostname (`aqp.fund`)
across the two backends:

```toml
# cloudflare/aqp_load_balancer.tf (excerpt)
resource "cloudflare_load_balancer_pool" "aqp_proxy_legacy" {
  origins = [{ name = "aqp-client", address = "...", weight = 0.9 }]
}
resource "cloudflare_load_balancer_pool" "aqp_proxy_envoy" {
  origins = [{ name = "aqp-edge", address = "...", weight = 0.1 }]
}
```

Apply via `aqp deploy terraform plan apply` (NEVER raw `terraform
apply` per AGENTS rule 42).

Verify both pools healthy:

```bash
kubectl -n aqp-edge get pods -l app=aqp-edge
kubectl -n aqp-edge get pods -l app=aqp-tenant-router

# Tail tenant-router logs for any 503s / cache misses:
kubectl -n aqp-edge logs -l app=aqp-tenant-router --tail=200 -f
```

Stop conditions (rollback to 100% legacy):
- `aqp-tenant-router` `/readyz` returns 503 for > 1 minute.
- Envoy `5xx` rate on `aqp-edge` ingress > 0.5% over a 5-minute
  window.
- Any audit event with `cell_id IS NULL` after the canary starts
  (indicates the X-AQP-Cell header isn't propagating into
  `RequestContext`).

## Step 3 — 50% traffic (week 8)

Cloudflare LB weight: 0.5 / 0.5. Repeat the verification + stop
conditions from step 2. Watch the `aqp.cell.id` distribution in
Tempo:

```
{aqp.cell.id="cell-shared-std-local"} | count_over_time(span_count[5m])
```

Both routes should converge on the same cell-id distribution.

## Step 4 — 100% traffic (week 9)

Cloudflare LB weight: 0.0 / 1.0. The Python proxy continues to
run but receives no live traffic. Keep it running for 7 days as
the rollback safety net.

## Step 5 — Remove the Python FastAPI proxy (week 10)

This step is intentionally NOT in the Phase 3 PR; it lands as a
follow-up after the 7-day soak. The removal removes
`aqp_platform/build/docker/aqp_client/Dockerfile`'s FastAPI
proxy module (the `production` stage's uvicorn entrypoint) and
strips the `/api/*`, `/ws/*`, `/manage/*`, `/static` route
handlers from `aqp/api/main.py`.

Tag the last buildable proxy image (`aqp-client:proxy-last-stable`)
before the removal lands so a regression has a known-good rollback
target.

## Rollback at any step

- Cloudflare LB weight back to 1.0 / 0.0 — instant traffic drain
  back to the legacy proxy.
- `kubectl -n aqp-edge scale deployment aqp-edge --replicas=0`
  prevents Envoy from accepting any traffic even if DNS still
  points at it.

## Phase 3 §6.6 follow-up — the removal PR

The Python proxy lives at
`aqp/api/proxy.py` + the relevant routes in
`aqp/api/main.py`. The Phase 3 §6.6 removal PR:

1. Cuts the route registrations.
2. Updates the `aqp-client` Dockerfile to drop the proxy CMD.
3. Removes the proxy's tests under `tests/api/`.
4. Tags the prior commit `aqp-client-proxy-final` so a rollback
   restores the buildable artifact.

## Related documents

- [RESTRUCTURING_PLAN.md §6](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md)
- [aqp_platform/deployments/kubernetes/cells/README.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_platform/deployments/kubernetes/cells/README.md)
- [aqp_platform/deployments/argocd/applicationsets/cells-appset.yaml](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_platform/deployments/argocd/applicationsets/cells-appset.yaml)
- [aqp_tenant_router/AGENTS.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_tenant_router/AGENTS.md)
