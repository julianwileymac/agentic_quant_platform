# AQP Monorepo Paths

Status: active.

Use workspace-relative AQP paths in docs, rules, and agent prompts. Do not
hardcode local `C:\Users\...` paths.

| AQP responsibility | Canonical path inside `agentic_quant_platform` |
| --- | --- |
| Active client | `aqp_client/` |
| Control plane | `aqp_control_plane/` |
| Shared contracts | `aqp_platform_core/` |
| Bots | `aqp_bots/` |
| Snippets | `aqp_snippets/` |

The Theia extension lives in this repository at `theia-extensions/aqp/` and
calls the AQP API/client surfaces through configuration, not direct imports.

