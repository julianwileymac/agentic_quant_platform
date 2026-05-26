---
title: Linkerd + SPIRE rollout runbook
description: Phase 4 §7.1 / §7.2 runbook — install per-cell Linkerd 2.16 + SPIRE 1.10, validate mTLS, ratchet from Audit to Enforce.
sidebar_label: Linkerd + SPIRE rollout
---

# Linkerd + SPIRE rollout runbook

> Phase 4 §7.1 + §7.2 of
> [RESTRUCTURING_PLAN.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md).
> Covers the per-cell install of Linkerd 2.16 (service mesh) and
> SPIRE 1.10 (workload identity) plus the matching validation
> steps.

## Scope

Per-cell installs of:

- **Linkerd 2.16** — mTLS-by-default for every pod-to-pod call inside
  a cell. Cross-cell calls re-terminate at `aqp-edge` (Envoy).
- **SPIRE 1.10** — issues SPIFFE JWT-SVIDs and X.509-SVIDs via the
  Workload API. Replaces the kubelet-bound ServiceAccount token
  usage in `aqp/auth/m2m.py`.

Both ship as kustomize bases under
`aqp_platform/deployments/kubernetes/mesh-identity/`. Argo CD's
`cells` `ApplicationSet` (Phase 3 §6.5) is extended in Phase 4.5 to
stamp one per-component Application per cell.

## Prerequisites

1. The cell namespace exists and carries the Phase 4 §7.1
   `linkerd.io/inject: enabled` annotation. Verify:
   ```bash
   kubectl get ns cell-shared-std-us-east-1a -o yaml | grep linkerd.io/inject
   # expected: linkerd.io/inject: enabled
   ```
2. The cell registry has the cell row in `state=provisioning` (so
   the cell-router doesn't send live traffic yet).
3. Vault PKI is configured and ready to issue:
   - Linkerd trust anchor + issuer cert (rotates via VaultStaticSecret).
   - SPIRE upstream authority (if running with `UpstreamAuthority`
     plugin; the Phase 4 spine uses self-signed for simplicity).

## Step 0 — Apply the mesh-identity spine

```bash
# Apply in dependency order:
#   1. SPIRE (everything else consumes SVIDs)
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/spire/

# Wait for SPIRE Server to be ready:
kubectl -n spire-system rollout status statefulset/spire-server --timeout=5m
kubectl -n spire-system get pods -l app=spire-agent

#   2. Linkerd (consumes SPIRE-issued trust anchor)
#   The trust anchor + issuer cert must already be in
#   Secret/linkerd-identity-issuer (see §7.6 wire-up).
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/linkerd/

# Wait for Linkerd identity service:
kubectl -n linkerd rollout status deployment/linkerd-identity --timeout=10m
kubectl -n linkerd rollout status deployment/linkerd-destination --timeout=10m
kubectl -n linkerd rollout status deployment/linkerd-proxy-injector --timeout=10m

# Optional: install linkerd-viz for golden-signal dashboards
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/linkerd/  # idempotent

#   3. vault-secrets-operator (mTLS via Linkerd, identity via SPIRE)
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/vault-secrets-operator/

#   4. Pomerium IAP (depends on Linkerd mTLS for backend reach)
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/pomerium/
```

## Step 1 — Validate SPIRE Workload API

```bash
# Find a workload pod that mounts the agent socket:
POD=$(kubectl -n cell-shared-std-us-east-1a get pods -l app=aqp-core -o name | head -1)

# Drop into the pod and fetch an SVID:
kubectl -n cell-shared-std-us-east-1a exec -it "$POD" -- /bin/sh -c "
  export SPIFFE_ENDPOINT_SOCKET=unix:///run/spire/sockets/agent.sock
  python -c '
from spiffe.workloadapi import default_jwt_source
src = default_jwt_source.DefaultJwtSource()
svid = src.fetch_svid(audiences=[\"aqp-tenant-router\"])
print(\"SPIFFE ID:\", svid.spiffe_id)
print(\"Audiences:\", svid.audiences)
print(\"Token (truncated):\", svid.token[:60], \"...\")
'
"
# Expected: SPIFFE ID spiffe://aqp.fund/cell/cell-shared-std-us-east-1a/aqp-core
```

If the SVID fetch fails, check the SPIRE Agent's registration
entries — the workload's ServiceAccount might not be selected:

```bash
kubectl -n spire-system exec -it spire-server-0 -- /opt/spire/bin/spire-server entry list
```

## Step 2 — Validate Linkerd mTLS

```bash
# Check that the proxy injected on every aqp-core pod:
kubectl -n cell-shared-std-us-east-1a get pods -l app=aqp-core \
  -o jsonpath='{range .items[*]}{.metadata.name}{":"}{.spec.containers[*].name}{"\n"}{end}'
# Expected: each pod has BOTH `api` and `linkerd-proxy` containers.

# Verify mTLS edge-to-edge between two AQP pods:
linkerd -n cell-shared-std-us-east-1a viz stat deploy
# Expected: every deployment row shows `MESHED 1/1` (or matching replica count)
# and the SUCCESS RATE column reports % over the last 1m window.

linkerd -n cell-shared-std-us-east-1a viz edges deployment
# Expected: every edge is "mTLS YES" — if any edge shows "NO", the
# source or destination pod is missing the proxy injection.
```

If pods are NOT meshed, the Proxy Injector didn't see the
`linkerd.io/inject: enabled` annotation. Check the namespace:

```bash
kubectl get ns cell-shared-std-us-east-1a -o yaml | grep -A 2 annotations
# Expected: linkerd.io/inject: enabled
```

## Step 3 — Validate Pomerium IAP

The Pomerium routes for `/manage/*` live in
`aqp_platform/deployments/kubernetes/mesh-identity/pomerium/route-manage.yaml`.

```bash
# From outside the cluster, the IAP-protected route should redirect
# to authenticate.aqp.fund (Pomerium's authenticate service):
curl -sIL https://manage.aqp.fund/manage/cells | head -10
# Expected: 302 to https://authenticate.aqp.fund/.pomerium/...

# After completing the Auth0 flow + step-up MFA, the request reaches
# aqp-cp.aqp-admin.svc.cluster.local:9000 with the
# X-Pomerium-Jwt-Assertion header attached:
curl -sS https://manage.aqp.fund/manage/cells \
  --cookie "_pomerium=<session>" \
  | jq '.data[].id'
```

The receiving FastAPI route validates the assertion via
`aqp.auth.providers.pomerium.extract_pomerium_claims` (Phase 4 §7.5).

## Step 4 — Cedar policy gate

Trigger a Cedar evaluation:

```bash
# Try to register a cell as a user WITHOUT the cell_operator role —
# should 403:
curl -sS -XPOST https://manage.aqp.fund/manage/cells \
  -H 'authorization: Bearer <JWT>' \
  -H 'content-type: application/json' \
  -d '{"id":"cell-x","tier":"shared-std",...}' \
  -o /tmp/cedar-deny.json
cat /tmp/cedar-deny.json
# Expected: {"detail":{"error":"cedar_denied",...}}

# With the role granted by the Auth0 Action, the same call succeeds:
# (cell_operator role is wired via the action at
# aqp/api/routes/auth0_sync.py per Phase 4 §7.3.)
```

## Step 5 — VaultStaticSecret rotation

Verify the `aqp-cell-postgres-credentials` Secret rotates within the
30-minute `refreshAfter` window:

```bash
# Watch the Secret's resourceVersion:
kubectl -n cell-shared-std-us-east-1a get secret postgres-credentials \
  -o jsonpath='{.metadata.resourceVersion}' --watch

# Trigger a Vault-side rotation:
vault kv put cells/shared-std/cell-shared-std-us-east-1a host=newhost.example port=5432

# Within 30 minutes the resourceVersion increments and the deployments
# listed in `rolloutRestartTargets` perform a rolling restart.
```

## Rollback

Each component is independently revertable:

```bash
# Linkerd — remove the proxy injection (existing pods stay meshed
# until their next rollout):
kubectl annotate ns cell-shared-std-us-east-1a linkerd.io/inject-

# SPIRE — workloads fall back to the Auth0 M2M path (chain order in
# aqp.credentials.resolver) when the SPIFFE socket isn't reachable.
kubectl -n spire-system scale daemonset spire-agent --replicas=0

# Pomerium — direct /manage/* to aqp-cp via DNS, bypassing the IAP.
kubectl -n pomerium scale deployment pomerium-proxy --replicas=0

# vault-secrets-operator — Secrets stop refreshing but stay readable.
kubectl -n vault-secrets-operator scale deployment vault-secrets-operator --replicas=0
```

## Phase 4.5 follow-ups

1. Per-cell SPIRE `ClusterSPIFFEID` CRDs binding workload selectors.
2. M2MTokenIssuer dispatch through `AQP_AUTH_M2M_PROVIDER=spiffe`.
3. Per-cell `VaultStaticSecret` set for every persistent service
   (Postgres, Redis, MinIO, MLflow, ChromaDB).
4. Per-cell Pomerium routes for the `aqp_admin` UI surface.
5. Linkerd SPIFFE trust anchor wired from SPIRE Server's
   upstream-authority CA.

## Related documents

- [RESTRUCTURING_PLAN.md §7](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md)
- [aqp_docs/docs/concepts/identity/spiffe-workload-identity.md](spiffe-workload-identity.md)
- [aqp_platform/deployments/kubernetes/mesh-identity/README.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_platform/deployments/kubernetes/mesh-identity/README.md)
- [aqp_docs/docs/how-to/cell-router-cutover.md](cell-router-cutover.md)
