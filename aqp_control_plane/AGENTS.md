# AGENTS.md

Agent contract for `aqp_control_plane`.

## Purpose

This project is the standalone AQP control plane. It owns workload
lifecycle operations, remote resource control, provider adapters, and the
`/manage/*` API surface.

## Hard Boundaries

1. Never import `aqp.*` from `src/aqp_cp/`.
2. Shared value types and provider ABCs come from `aqp_platform_core`.
3. Mutating workload actions go through `WorkloadRuntime` or an
   `InfrastructureProvider`; do not shell out directly from routes.
4. Do not print or return credentials, bearer tokens, kubeconfigs, or secret
   payloads. Return metadata and redacted summaries.
5. Keep provider SDK dependencies behind optional extras in `pyproject.toml`.

## Where Changes Go

- New `/manage/*` route: `src/aqp_cp/api/routers/`.
- New provider implementation: `src/aqp_cp/providers/`.
- Shared model needed by AQP runtime and control plane:
  `../aqp_platform_core/src/aqp_platform_core/`.
- AQP business runtime behavior: `../aqp/`, not this project.

## Validation

```bash
pip install -e ../aqp_platform_core
pip install -e .[dev,all-providers]
pytest -ra
rg --type py "^from aqp(\.|$)|^import aqp(\.|$)" src tests
```

The `rg` command should return no matches for `src/aqp_cp`.

