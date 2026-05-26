# aqp-index debt — Phase 5 per-tenant MCP + agent sandbox

> Per the always-on
> [aqp-index-reflect rule](../rules/aqp-index-reflect.mdc), Phase 5
> §8 of
> [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) touches
> enough qualifying surfaces (new biscuit + cell-bound auth modules,
> MCP registry hashing, Alembic 0084 + ORM, tenant_router, gVisor
> tree, per-tenant MCP Helm chart, envoy.template ext_authz chain,
> two new docs files) that `aqp_index/` MUST be refreshed by the
> [`aqp-index-curator`](../agents/aqp-index-curator.md) subagent in
> the same PR — OR a debt note (this file) must capture the
> changed surfaces so the curator's next scheduled pass picks
> them up.
>
> This note is option 2.

## Surfaces changed in Phase 5

### `aqp/`

- **`aqp/auth/biscuit.py`** (NEW) — `Capability`,
  `IssuedBiscuit`, `VerifiedBiscuit` dataclasses +
  `mint_biscuit / attenuate_for_call / verify_biscuit`. Sits
  alongside `TokenExchangeBroker` (Rule 54).
- **`aqp/auth/cell_bound.py`** (NEW) — `CellBoundClaims`,
  `mint / verify`, `CELL_BOUND_HEADER = "Cell-Bound-Authorization"`,
  `CBA_TTL_SECONDS = 60`. Smoke-tested end-to-end with
  RSA-2048 keys.
- **`aqp/data/mcp/registry.py`** — added `DATA_MCP_TOOL_HASHES`
  cache + `compute_descriptor_hash`, `descriptor_hash_for`,
  `snapshot_catalog` helpers. `register_data_mcp_tool` now
  populates the hash cache automatically.
- **`aqp/data/mcp/server.py`** — new `_snapshot_mcp_tool_versions()`
  helper called from `run_stdio()` boot. Idempotent
  `INSERT ON CONFLICT DO NOTHING` against the new
  `mcp_tool_versions` table.
- **`aqp/data/mcp/tenant_router.py`** (NEW) — `McpEndpoint`,
  `resolve_mcp_endpoint`, `headers_for`. Resolves
  `(workspace_id, tenant_id, mcp_kind)` to an in-cluster MCP
  URL + audience via the cells registry. 30s cache.
- **`aqp/agents/runtime.py`** — added `record_mcp_tool_hash(name)`
  + `_mcp_tool_hashes: set[str]` on `AgentRuntime`. `_finalise()`
  now persists the hash set onto `agent_runs_v2.mcp_tool_descriptor_hashes`
  when the column exists (added by Alembic 0084).
- **`pyproject.toml`** — added
  `biscuit-python>=0.4.0; platform_system != 'Windows'` to the
  `[auth]` extra. Marker-gated because Biscuit's Rust-backed
  wheels are not published for Windows.

### `alembic/`

- **`alembic/versions/0084_mcp_tool_versioning.py`** (NEW) — creates
  the `mcp_tool_versions` table (with UNIQUE constraint on
  `tool_name + descriptor_hash`) and adds
  `agent_runs_v2.mcp_tool_descriptor_hashes` (JSON column).
- **`alembic/versions/.hashes.lock`** — added one new entry
  (85 total).

### `aqp/persistence/`

- **`aqp/persistence/models_mcp_tools.py`** (NEW) — `MCPToolVersion`
  ORM model mirroring the migration's `mcp_tool_versions` table
  schema 1:1.

### `aqp_platform/deployments/`

- **`aqp_platform/deployments/kubernetes/agent-sandbox/`** (NEW TREE):
  - `gvisor/runtimeclass.yaml` — `RuntimeClass{name: gvisor, handler: runsc}`.
  - `gvisor/installer-daemonset.yaml` — Namespace + ServiceAccount +
    ClusterRole/Binding + installer DaemonSet that downloads
    `runsc` + patches containerd + labels nodes
    `aqp.io/gvisor=installed`.
  - `pool/namespace.yaml` + `pool/deployment.yaml` —
    `aqp-agent-sandbox-pool` Deployment with
    `runtimeClassName: gvisor` + `aqp.io/sandbox-required: "true"`.
- **`aqp_platform/deployments/helm/aqp-mcp-tenant/`** (NEW HELM CHART):
  - `Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`,
    `templates/mcp-deployment.yaml`. One Helm release per
    `(cell_id, tenant_id)` for `shared-prem` / `silo-reg` tiers.
    Renders 6 objects per release (2 Deployments + 2 Services +
    2 PDBs).
- **`aqp_platform/build/docker/aqp-edge/envoy.template.yaml`** —
  added an FIRST ext_authz step at
  `aqp-cell-bound-validator.aqp-edge.svc.cluster.local` that
  validates the `Cell-Bound-Authorization` header (Phase 5 §8.5)
  BEFORE the tenant-router ext_authz step. Added the matching
  upstream cluster.

### `aqp_docs/`

- **`aqp_docs/docs/how-to/per-tenant-mcp-rollout.md`** (NEW) —
  operator-facing runbook covering gVisor install, agent-sandbox
  pool deploy, per-tenant MCP Helm install, mcp_tool_versions
  verification, agent_runs_v2 hash-set verification, CBA gate
  validation, rollback steps.
- **`aqp_docs/docs/concepts/identity/biscuit-capabilities.md`**
  (NEW) — concept doc covering the JWT-vs-biscuit trade-off,
  AQP integration code samples, capability shape, key-rotation
  procedure, failure modes.

## Files the curator should refresh

| `aqp_index/` file | Why it needs a refresh |
| --- | --- |
| `aqp_index/projects/aqp.md` | New `aqp/auth/biscuit.py` + `aqp/auth/cell_bound.py` + `aqp/data/mcp/tenant_router.py` + `aqp/persistence/models_mcp_tools.py`. Registry and AgentRuntime have new public symbols. |
| `aqp_index/projects/aqp_platform.md` | New `agent-sandbox/` K8s tree + new `helm/aqp-mcp-tenant/` chart + envoy.template ext_authz chain extended. |
| `aqp_index/projects/aqp_docs.md` | Two new docs pages (concepts/identity + how-to). |
| `aqp_index/sources-of-truth.md` | `mcp_tool_versions` is the new SSoT for tool catalog snapshots; biscuit signing key is the new SSoT for agent capability attenuation; `Cell-Bound-Authorization` JWT is the new SSoT for cross-cell call provenance. |
| `aqp_index/config-sets/alembic.md` | Head is now `0084_mcp_tool_versioning`. |
| `aqp_index/config-sets/mcp-tools.md` | Tool descriptors now hash-tracked; the registry helper surface grew three functions. |

## Phase 5 §8 sub-section coverage

| RESTRUCTURING_PLAN.md sub-§ | Status |
| --- | --- |
| §8.1 Per-tenant MCP server isolation | `tenant_router.py` Python module + `aqp-mcp-tenant` Helm chart for shared-prem/silo-reg tiers |
| §8.2 Biscuit capability tokens | `aqp/auth/biscuit.py` + biscuit-python in [auth] extra (conditional on platform) + concept doc |
| §8.3 gVisor RuntimeClass | `agent-sandbox/gvisor/runtimeclass.yaml` + installer DaemonSet + `aqp-agent-sandbox-pool` Deployment with `runtimeClassName: gvisor` |
| §8.4 Tool descriptor versioning | Alembic 0084 + ORM model + `compute_descriptor_hash` / `snapshot_catalog` + `_snapshot_mcp_tool_versions` on MCP boot + `record_mcp_tool_hash` on AgentRuntime |
| §8.5 Cell-Bound-Authorization | `aqp/auth/cell_bound.py` + envoy.template.yaml ext_authz chain (CBA validator first) + 60-second TTL + verbatim cell-id convention |

## Phase 5.5 follow-ups

1. **shared-std MCP pool chart** — the `shared-std` tier shares a
   per-cell pool with Linux cgroup tenant isolation. The Helm chart
   in this PR targets `shared-prem` and `silo-reg`; the pool chart
   is the Phase 5.5 deliverable.
2. **aqp-cell-bound-validator service** — the Envoy ext_authz step
   points at `aqp-cell-bound-validator.aqp-edge.svc.cluster.local`
   but the service itself ships in the follow-up. Until then,
   `failure_mode_allow: false` means cross-cell calls fail closed
   (intended).
3. **Agent runtime biscuit wire-up** — the helpers in
   `aqp/auth/biscuit.py` are standalone. The
   `AgentRuntime.invoke_mcp_tool()` integration that mints + attenuates
   the biscuit per call lands in Phase 5.5.
4. **Multi-key biscuit verify** — `verify_biscuit` accepts a single
   public key today; multi-key fallback for the 7-day rotation
   overlap window lands in Phase 5.5.
5. **MCP server-side biscuit enforcement** — wire `verify_biscuit`
   into `aqp/data/mcp/server.py`'s HTTP request handler so every
   tool call that doesn't carry a valid biscuit gets 401.
6. **gVisor performance baselines** — measure the throughput
   overhead of gVisor on agent-sandbox-pool against the prior
   runc-only baseline. Document in
   `aqp_docs/docs/concepts/identity/biscuit-capabilities.md`.
7. **Replay harness verification** — Phase 7 §10.2 reads back
   `agent_runs_v2.mcp_tool_descriptor_hashes` and verifies the
   live `mcp_tool_versions` table contains the matching hashes.

## Provenance

- Discovered while implementing
  [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) Phase 5 in
  the same PR.
- All surfaces enumerated above show up in `git status` for this PR.
