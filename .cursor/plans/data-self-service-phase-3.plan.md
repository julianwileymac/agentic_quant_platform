# Phase 3 — Interactive Dagster + Airbyte Sandbox

Companion to the master plan and to phase plans 0–2. The sandbox is
an ephemeral, per-session Dagster definitions environment that loads
a user-supplied component (or an Airbyte connection authored in
Phase 2) and streams logs back to the UI without polluting
production state.

## Backend

- `aqp/dagster/sandbox/` (new package):
  - `runtime.py` — wraps Dagster's
    `create_defs_folder_sandbox` context manager when available.
    Falls back to a plain `tempfile.mkdtemp` directory + manual
    component file write so the sandbox still works on the API
    process even when the Dagster code-server isn't running.
  - `airbyte_bridge.py` — translates an `AirbyteConnectionSpec`
    (Phase 2 output) into a Dagster component config seeded into
    the sandbox folder.
  - `redis_isolation.py` — re-uses Phase 0's `MetadataCache`
    keyed under `aqp:sandbox:<session_id>:*`. Sandbox writes never
    touch the production prefix.
  - `env_resolver.py` — `ContextVar`-based environment substitution
    that swaps production endpoints (Iceberg REST URI, AV API URL,
    etc.) for safe / mocked alternatives inside a session.
  - `executor.py` — `load_component_and_build_defs(...)` plus a
    log iterator that streams `AssetMaterialization` events.

- `aqp/api/routes/dagster_sandbox.py`:
  - `POST /dagster/sandbox/sessions` — create session, return
    `session_id`.
  - `GET /dagster/sandbox/sessions/{id}` — status.
  - `POST /dagster/sandbox/sessions/{id}/components` — write a
    component config to the sandbox folder.
  - `POST /dagster/sandbox/sessions/{id}/load` — call
    `load_component_and_build_defs`, return asset key tree.
  - `POST /dagster/sandbox/sessions/{id}/execute` — kick off
    Celery task, return `TaskAccepted`.
  - `DELETE /dagster/sandbox/sessions/{id}` — tear down folder +
    Redis namespace + DB row.
  - `GET /dagster/sandbox/sessions` — list active sessions.

- `aqp/tasks/dagster_sandbox_tasks.py` — Celery task emitting
  through `_progress.emit / emit_done / emit_error` with the
  canonical `{task_id, stage, message, timestamp, **extras}` frame
  (AGENTS rule 4).

- Alembic 0034 — `dagster_sandbox_sessions(id, project_id, owner_id,
  status, created_at, expires_at, components_json, last_run_id,
  log_summary)`.

## Frontend

- `frontend/src/routes/data/sandbox/page.tsx` + `SandboxConsole.tsx`
  three-pane layout (component editor, asset graph preview,
  streaming log console).
- Amber outline + `[SANDBOX]` tab title prefix mirroring the paper-
  mode guardrail in `frontend.mdc`.
- Airbyte connection picker uses `<EntityPicker kind="airbyte_connectors" />`.

## Tests + docs + rules

- `tests/dagster/test_sandbox_runtime.py` — tempdir lifecycle,
  Redis namespacing.
- `tests/dagster/test_env_resolver.py` — ContextVar substitution.
- `docs/dagster-sandbox.md` — narrative.
- `.cursor/rules/dagster-sandbox.mdc` — AGENTS rule 32 scope.
