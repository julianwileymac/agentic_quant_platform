# AQP Cedar policy bundle

Phase 4 §7.3 of
[RESTRUCTURING_PLAN.md](../../../../RESTRUCTURING_PLAN.md). Every
`.cedar` file in this directory is loaded once at process start by
`aqp.api.security_cedar.load_policies()` and evaluated on every
`require_cedar(...)` FastAPI dependency call.

## Files

| File | Scope |
| --- | --- |
| `00_cells.cedar` | `/manage/cells/*` mutations (Phase 3 §6.2). |
| `01_manage.cedar` | Other `/manage/*` mutations: secrets, builds, terraform, tenants. |
| `02_agents.cedar` | Agent-sandbox MCP tool surface (Phase 5 §8). |
| `03_data.cedar` | DataMCP tool surface — dataset read/write/delete/export. |

Files load in alphabetical order; the leading two-digit prefix is
the ordering convention. New policies SHOULD pick a free prefix
slot rather than overloading an existing file.

## Entity model

Every policy file shares the same entity vocabulary:

- **`User`** — JWT principal. Attributes: `org_id`, `workspace_id`,
  `roles[]`, `scopes[]`, `clearances[]`.
- **`Agent`** — autonomous agent runtime. Attributes: `agent_id`,
  `on_behalf_of`, `capabilities[]`, `gvisor_class`.
- **`Cell`** — deployment cell from the cells registry (Phase 3 §6.2).
- **`Secret`**, **`Build`**, **`TerraformStack`**, **`Tenant`** —
  control-plane mutable resources.
- **`Tool`** — MCP tool descriptor. Attributes: `descriptor_hash`,
  `mutates`, `required_capability`, `audience`, `required_runtime`,
  `approval_id`.
- **`Dataset`** — Iceberg / Postgres dataset. Attributes:
  `namespace`, `sensitivity`, `owner_org_id`, `retention_days`.

## Action vocabulary

- Cells: `manage_cell`, `register_cell`, `update_cell_state`,
  `decommission_cell`, `place_tenant_in_cell`,
  `migrate_tenant_to_cell`.
- Manage: `rotate_secret`, `build_image`, `terraform_plan`,
  `terraform_apply`, `terraform_destroy`, `terraform_refresh`,
  `provision_tenant`, `deprovision_tenant`.
- Agents: `invoke_tool`, `read_secret`, `write_outbox`.
- Data: `read_dataset`, `write_dataset`, `delete_dataset`,
  `export_dataset`.

When a route adds a new action, ALSO add a corresponding policy
clause (even if the clause is just a `permit (principal, action ==
Action::"new_action", resource);` no-op gate). Cedar's default is
deny — a route protected by `require_cedar("new_action", ...)`
with no policy hits will always 403.

## Validation

```bash
# Static check (requires cedarpy installed via the [auth] extra):
python -c "
from aqp.api.security_cedar import load_policies, reset_cedar_cache
reset_cedar_cache()
ps = load_policies()
print(f'Loaded {len(ps.policy_paths)} policy file(s); {len(ps.policy_text)} bytes total.')
"

# Live decision smoke (requires a running FastAPI app):
curl -sS -XPOST http://localhost:8000/manage/cells \
  -H 'authorization: Bearer <jwt>' \
  -H 'content-type: application/json' \
  -d '{"id":"cell-x","tier":"shared-std",...}'
# Expected 403 if your JWT lacks the cell_operator role + the
# matching scope, 200 otherwise.
```

## Sensitivity classification

The `Dataset.sensitivity` attribute uses the same values as the
FinOps `data_classification` namespace label (Phase 2 §5.3):

- `public` — public reference data (no restrictions).
- `internal` — operational metrics, FinOps tags.
- `proprietary-alpha` — alpha signals, training data.
- `customer-pii` — anything containing customer identifiers.
- `regulated` — FINRA / SEC / MiFID II covered data.

When you add a new sensitivity tier (e.g. `regulated-itar`),
also extend the corresponding `permit` clauses here.

## Phase 4.5 follow-ups

- Per-cell policy isolation: policies will get a per-cell suffix
  (`00_cells.cell-shared-std.cedar`) so each cell can carry its
  own override layer. Today every cell shares this global bundle.
- Hot reload via `POST /manage/cedar/reload`: the loader caches
  for the process lifetime; an admin reload endpoint lands when
  policy iteration becomes a daily activity.
- OPA → Cedar migration: any leftover OPA Rego policies in
  `aqp/api/` will move here once Phase 4 §7.4 confines OPA to
  cluster admission only.
