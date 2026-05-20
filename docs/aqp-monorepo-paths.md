# AQP Monorepo Paths

Status: active.

Canonical path contract for this repository. Sibling repos (`rpi_kubernetes`,
`theia-ide`, `aqp_platform_admin`) mirror this table in their own
`docs/aqp-monorepo-paths.md` files.

| AQP responsibility | Path |
| --- | --- |
| Control plane | `aqp_control_plane/` |
| Shared platform contracts | `aqp_platform_core/` |
| Active client (Vite) | `aqp_client/` |
| Bot runtime/templates | `aqp_bots/` |
| Snippet corpus | `aqp_snippets/` |
| Monolith runtime | `aqp/` |
| Kubernetes workloads | `deployments/kubernetes/` |

Compatibility stubs (do not add active source here):

| Legacy path | Points to |
| --- | --- |
| `frontend/` | `aqp_client/` |
| `extractions/` | `aqp_snippets/extractions/` |
| `inspiration/` | `aqp_snippets/inspiration/` (ignored raw repos) |
| `aqp/bots/` | `aqp_bots/` (import shim) |
