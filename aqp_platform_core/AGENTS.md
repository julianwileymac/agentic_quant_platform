# AGENTS.md

Agent contract for `aqp_platform_core`.

## Purpose

This package is the shared foundation for AQP projects. It contains stable
value types, provider protocols, auth/resource-filter primitives, topology
models, and workload runtime abstractions used by both the monolith and the
control plane.

## Hard Boundaries

1. Do not import `aqp.*` or `aqp_cp.*`.
2. Keep runtime dependencies small and explicit: no FastAPI routes,
   SQLAlchemy models, Celery tasks, React code, or concrete cloud workflows.
3. Prefer Pydantic models, protocols, ABCs, and pure helpers.
4. Treat public model fields as wire contracts. Renames and removals require
   a major-version migration plan.
5. Avoid import-time side effects, network I/O, environment mutation, and
   registry population that depends on optional SDKs.

## Where Changes Go

- Shared deployment or topology model: `src/aqp_platform_core/topology/`.
- Shared provider interface: `src/aqp_platform_core/providers/`.
- Auth/resource filtering primitives: `src/aqp_platform_core/auth/`.
- Concrete AQP behavior, ORM persistence, or task dispatch: `../aqp/`.
- Control-plane provider execution: `../aqp_control_plane/`.

## Validation

```bash
pip install -e .[dev]
pytest -ra
mypy src/aqp_platform_core
ruff check src tests
```

