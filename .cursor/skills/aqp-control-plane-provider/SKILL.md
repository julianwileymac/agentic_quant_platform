# AQP Control Plane Provider

Use this skill when adding or changing an `InfrastructureProvider` in
`aqp_control_plane`.

## Workflow

1. Read `docs/repository-split.md`.
2. Read `aqp_control_plane/AGENTS.md` and `aqp_platform_core/AGENTS.md`.
3. Add shared protocol or value-type changes to `aqp_platform_core` first.
4. Add concrete provider behavior under `aqp_control_plane/src/aqp_cp/providers/`.
5. Keep route handlers thin; expose behavior through `/manage/*` routers.
6. Add provider contract tests under `aqp_control_plane/tests/providers/`.

## Checks

```bash
rg --type py "^from aqp(\.|$)|^import aqp(\.|$)" aqp_control_plane/src
cd aqp_platform_core && python -m pytest tests
cd ../aqp_control_plane && python -m pytest tests/providers
```

Never print tokens, kubeconfigs, tunnel credentials, or secret payloads.

