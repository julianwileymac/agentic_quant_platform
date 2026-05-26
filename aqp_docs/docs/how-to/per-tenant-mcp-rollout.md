---
title: Per-tenant MCP rollout
description: Phase 5 §8.1 runbook — deploy per-tenant MCP servers + the gVisor agent-sandbox pool + Cell-Bound-Authorization validation.
sidebar_label: Per-tenant MCP rollout
---

# Per-tenant MCP rollout runbook

> Phase 5 §8 of
> [RESTRUCTURING_PLAN.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md).
> Walks the cluster operator through deploying per-tenant MCP
> servers, the gVisor agent-sandbox pool, and the Cell-Bound-
> Authorization gate at `aqp-edge`.

## Scope

1. **gVisor RuntimeClass** — install via the DaemonSet at
   `aqp_platform/deployments/kubernetes/agent-sandbox/gvisor/`.
2. **aqp-agent-sandbox-pool** — the gVisor-isolated Deployment at
   `aqp_platform/deployments/kubernetes/agent-sandbox/pool/`.
3. **Per-tenant MCP servers** — Helm-rendered Deployments from
   `aqp_platform/deployments/helm/aqp-mcp-tenant/` for each
   `shared-prem` / `silo-reg` tenant.
4. **Cell-Bound-Authorization** — the second ext_authz step in
   `aqp_platform/build/docker/aqp-edge/envoy.template.yaml`.
5. **MCP tool catalog versioning** — Alembic 0084 creates the
   `mcp_tool_versions` table + adds
   `agent_runs_v2.mcp_tool_descriptor_hashes`.

## Prerequisites

1. Phase 3 cells are registered and at least one is in
   `state=active`.
2. Phase 4 SPIRE control plane is healthy in the cell. Verify:
   ```bash
   kubectl -n spire-system rollout status statefulset/spire-server
   kubectl -n spire-system get pods -l app=spire-agent
   ```
3. The Alembic head is at `0084_mcp_tool_versioning`. Verify:
   ```bash
   alembic current  # expected: 0084_mcp_tool_versioning (head)
   ```
4. Phase 2 Kyverno policies are loaded. Verify:
   ```bash
   kubectl get clusterpolicy aqp-require-gvisor-for-agent-sandbox
   ```

## Step 0 — Install gVisor

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/agent-sandbox/gvisor/
kubectl -n gvisor rollout status daemonset/gvisor-installer --timeout=10m

# Wait for the node labels to appear (the installer marks each node
# `aqp.io/gvisor=installed` after patching containerd):
kubectl get nodes -L aqp.io/gvisor
# Expected: every node ends with `installed`.
```

## Step 1 — Deploy the agent-sandbox pool

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/agent-sandbox/pool/
kubectl -n aqp-agent-sandbox rollout status deployment/aqp-agent-sandbox-pool --timeout=5m

# Confirm gVisor is active inside the pod (the kernel reports as `runsc`):
POD=$(kubectl -n aqp-agent-sandbox get pods -l app=aqp-agent-sandbox-pool -o name | head -1)
kubectl -n aqp-agent-sandbox exec "$POD" -- /bin/sh -c "uname -r; cat /proc/version"
# Expected: kernel version reports as runsc/gVisor.

# Confirm the Kyverno gate is enforced — try to deploy a Pod with the
# `aqp.io/sandbox-required` label but WITHOUT runtimeClassName:gvisor:
cat <<EOF | kubectl apply -f - --dry-run=server
apiVersion: v1
kind: Pod
metadata:
  name: sandbox-test
  namespace: aqp-agent-sandbox
  labels:
    aqp.io/sandbox-required: "true"
spec:
  containers:
    - name: x
      image: cgr.dev/chainguard/python:3.11
EOF
# Expected: admission rejected with `cedar_denied: aqp-require-gvisor-...`
```

## Step 2 — Deploy a per-tenant MCP server (silo-reg example)

```bash
# Render the Helm chart for the Acme tenant:
helm upgrade --install \
  acme-mcp \
  aqp_platform/deployments/helm/aqp-mcp-tenant/ \
  --namespace cell-silo-reg-acme \
  --set cell_id=cell-silo-reg-acme \
  --set tenant_id=tenant_acme \
  --set tier=silo-reg

# Verify:
kubectl -n cell-silo-reg-acme get deployments -l aqp.io/tenant-id=tenant_acme
# Expected: aqp-data-mcp-tenant_acme + aqp-codebase-mcp-tenant_acme.
```

## Step 3 — Snapshot the tool catalog

The MCP server snapshots its tool catalog into `mcp_tool_versions`
on boot. Verify:

```bash
kubectl -n cell-silo-reg-acme exec \
  $(kubectl -n cell-silo-reg-acme get pods -l aqp.io/mcp-kind=data -o name | head -1) \
  -- /bin/sh -c "psql \$AQP_POSTGRES_DSN -c 'SELECT tool_name, substring(descriptor_hash, 1, 12) FROM mcp_tool_versions LIMIT 10;'"
```

Expected output:

```
       tool_name        | substring
------------------------+--------------
 data.catalog.browse    | abc123def456
 data.entities.search   | f0e1d2c3b4a5
 ...
```

## Step 4 — Verify agent_runs_v2 records descriptor hashes

After running a backtest that invokes MCP tools, the
`agent_runs_v2.mcp_tool_descriptor_hashes` column carries the set
of hashes the run saw:

```sql
SELECT id, status, mcp_tool_descriptor_hashes
FROM agent_runs_v2
WHERE workspace_id = '<your-workspace>'
ORDER BY started_at DESC
LIMIT 5;
```

The hash array MUST be a subset of `mcp_tool_versions.descriptor_hash`
at the matching cell_id. The Phase 7 §10.2 replay harness will
verify this invariant.

## Step 5 — Validate Cell-Bound-Authorization

Cross-cell MCP calls now require the `Cell-Bound-Authorization`
header. Without it, `aqp-edge` returns 403 at the second ext_authz
step.

```bash
# From outside the cluster, simulate a cross-cell call missing CBA:
curl -sS -XPOST https://manage.aqp.fund/mcp/data/cell-silo-reg-acme/some.tool \
  -H 'authorization: Bearer <jwt>' \
  -d '{"args": {}}'
# Expected: 403 with `cell_bound_invalid` in the body.

# With a valid CBA (minted by the source-cell tenant-router):
curl -sS -XPOST https://manage.aqp.fund/mcp/data/cell-silo-reg-acme/some.tool \
  -H 'authorization: Bearer <jwt>' \
  -H 'Cell-Bound-Authorization: <cba-jwt>' \
  -d '{"args": {}}'
# Expected: tool result.
```

The CBA validator service is a Phase 5.5 deliverable; today the
ext_authz config points at the planned service address but the
service itself ships in the follow-up PR. Until then, the
`failure_mode_allow: false` flag means cross-cell calls without a
CBA fail closed (the validator returns 503 because it doesn't
exist yet) — which is the intended behaviour for the security
posture.

## Rollback

Each component is independently revertable:

```bash
# Per-tenant MCP — uninstall the Helm release:
helm uninstall acme-mcp -n cell-silo-reg-acme

# Agent sandbox pool — scale to zero:
kubectl -n aqp-agent-sandbox scale deployment aqp-agent-sandbox-pool --replicas=0

# gVisor — DO NOT DROP the installer DaemonSet without first
# removing every Pod with `runtimeClassName: gvisor`, otherwise
# the pods will sit in RunPodSandboxFailed forever.

# Cell-Bound-Authorization — flip ext_authz failure_mode_allow to true
# in the envoy ConfigMap then `kubectl rollout restart -n aqp-edge
# deployment/aqp-edge`. Cross-cell calls then bypass the CBA gate.
```

## Phase 5.5 follow-ups

1. **aqp-cell-bound-validator service** — the small HTTP service the
   ext_authz step points at. Phase 5 ships the Envoy config; the
   actual service implementation is a thin Starlette app that
   wraps `aqp.auth.cell_bound.verify(...)`.
2. **shared-std MCP pool chart** — the `shared-std` tier uses one
   pool per cell with per-tenant Linux cgroups (cgroups v2 + Pod
   Security Standards `restricted`). The Helm chart for the pool
   is a Phase 5.5 deliverable; the per-tenant chart in this PR
   targets `shared-prem` and `silo-reg`.
3. **Biscuit + TokenExchangeBroker wire-up in AgentRuntime** —
   the helpers in `aqp/auth/biscuit.py` are standalone today; the
   `AgentRuntime` integration that mints + attenuates the biscuit
   per call is Phase 5.5.
4. **MCP tool versioning replay** — `mcp_tool_descriptor_hashes`
   recording works in Phase 5; the replay harness that verifies
   the recorded set matches the live catalog is Phase 7 §10.2.

## Related documents

- [RESTRUCTURING_PLAN.md §8](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md)
- [aqp_docs/docs/concepts/identity/biscuit-capabilities.md](../concepts/identity/biscuit-capabilities.md)
- [aqp_docs/docs/how-to/linkerd-spire-rollout.md](linkerd-spire-rollout.md)
- [aqp_docs/docs/concepts/identity/spiffe-workload-identity.md](../concepts/identity/spiffe-workload-identity.md)
