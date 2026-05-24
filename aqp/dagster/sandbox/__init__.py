"""Interactive Dagster sandbox (data fabric phase 3).

An ephemeral, per-session Dagster definitions environment that
loads a user-supplied component (or an Airbyte connection authored
in the visual builder) and streams asset materialization events
back to the UI without polluting production state. Production
endpoints (Iceberg REST URI, AV API URL, Polaris) are substituted
for mocked alternatives via :class:`SandboxEnvResolver` so the
sandbox can never write to the production warehouse.

Public surface::

    from aqp.dagster.sandbox import SandboxRuntime

    runtime = SandboxRuntime.create_session(owner="alice")
    runtime.write_component("my_demo.yaml", "...")
    summary = runtime.load()
    runtime.execute()  # streams AssetMaterialization events
    runtime.teardown()

Narrative: :file:`aqp_docs/dagster-sandbox.md`. Phase plan:
:file:`.cursor/plans/data-self-service-phase-3.plan.md`.
"""
from __future__ import annotations

from aqp.dagster.sandbox.env_resolver import (
    SandboxEnvResolver,
    enter_sandbox_env,
    sandbox_env_active,
)
from aqp.dagster.sandbox.executor import SandboxExecutor
from aqp.dagster.sandbox.redis_isolation import SandboxRedisNamespace
from aqp.dagster.sandbox.runtime import SandboxRuntime, SandboxSession

__all__ = [
    "SandboxEnvResolver",
    "SandboxExecutor",
    "SandboxRedisNamespace",
    "SandboxRuntime",
    "SandboxSession",
    "enter_sandbox_env",
    "sandbox_env_active",
]
