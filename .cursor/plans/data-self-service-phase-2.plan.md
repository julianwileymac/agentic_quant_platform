# Phase 2 — Graphical Airbyte Connector Builder (AQP-native)

Companion to the master plan (`~/.cursor/plans/...`) and to
[`data-self-service-phase-0`](data-self-service-phase-0.plan.md) /
[`-phase-1`](data-self-service-phase-1.plan.md). Phase 2 replaces
the JSON editor in
[`AirbyteWorkspace.tsx`](../../frontend/src/components/airbyte/AirbyteWorkspace.tsx)
with a schema-driven form and a "AQP-native Fetcher stub" code path.

## Design decisions (locked from the master plan)

- **No `AIRBYTE_ENABLE_UNSAFE_CODE`.** Custom Python lives under
  [`aqp/data/fetchers/userland/`](../../aqp/data/fetchers/userland)
  with `@register_source_fetcher` and credentials resolved through
  [`aqp.credentials.CredentialResolver`](../../aqp/credentials/resolver.py).
- **Credentials picker uses EntityPicker, not a free-text password
  field.** All secret references resolve at runtime through the
  resolver chain.
- **Builder state round-trips to YAML.** The builder UI persists
  `builder_state_json` so re-opening an existing connector shows
  the same form values.

## Backend

### `aqp/data/airbyte/builder/`

- `__init__.py` — re-exports the public surface.
- `schema.py` — vendored, condensed Low-Code CDK field tree
  (`BuilderField`, `BuilderSection`). Phase 2 ships an opinionated
  subset (auth, requester, paginator, record selector, streams).
- `validate.py` — `validate_manifest(state)` returns structured
  errors / warnings.
- `codegen_yaml.py` — `state_to_yaml(state) -> str` produces the
  low-code YAML manifest from form state.
- `codegen_fetcher.py` — `state_to_fetcher_stub(state) -> str`
  produces an `aqp.data.fetchers.Fetcher` subclass body that uses
  `CredentialResolver` and registers via
  `@register_source_fetcher`. Stored under
  `aqp/data/fetchers/userland/<slug>.py` on commit.
- `inference.py` — `infer_streams(spec)` issues a single test
  request via httpx and returns inferred top-level fields.

### `aqp/api/routes/airbyte_builder.py`

- `GET /airbyte/builder/cdk-schema` — returns the parsed
  `BuilderField` tree.
- `POST /airbyte/builder/manifest/draft` — round-trip form state →
  canonical YAML.
- `POST /airbyte/builder/manifest/validate` — structured errors.
- `POST /airbyte/builder/streams/infer` — schema inference.
- `POST /airbyte/builder/codegen/fetcher` — generate stub (dry-run);
  returns diff preview.
- `POST /airbyte/builder/codegen/fetcher/commit` — write to
  `aqp/data/fetchers/userland/<slug>.py` (gated on env knob; default
  refuses to overwrite existing files).
- `GET /airbyte/builder/state/{connector_id}` /
  `PUT /airbyte/builder/state/{connector_id}` — persist
  `builder_state_json` on the connector row.

### Alembic 0033

- `airbyte_connectors.manifest_yaml TEXT NULL`
- `airbyte_connectors.aqp_fetcher_path STRING(240) NULL`
- `airbyte_connectors.builder_state_json JSONB NULL`

## Frontend

`frontend/src/components/airbyte/builder/`:

- `ConnectorBuilderForm.tsx` — schema-driven form generator from
  `/airbyte/builder/cdk-schema`.
- `AuthBlock.tsx` — `<EntityPicker kind="credentials" />` replaces
  every secret field.
- `PaginationBlock.tsx`, `RequestBlock.tsx`, `StreamPanel.tsx` —
  modular sections.
- `GeneratedFetcherPreview.tsx` — read-only CodeMirror diff of the
  generated AQP Fetcher.
- Replace lines 168-205 of
  [`AirbyteWorkspace.tsx`](../../frontend/src/components/airbyte/AirbyteWorkspace.tsx)
  with `<ConnectorBuilderForm />`.
- Honour `?from=discovery&entry_id=<id>` query string from Phase 1
  by pre-filling the form.

## Tests

- `tests/data/airbyte/builder/test_codegen_yaml.py` — round-trip
  state / yaml.
- `tests/data/airbyte/builder/test_codegen_fetcher.py` — generated
  stub imports cleanly + uses CredentialResolver.
- `tests/api/test_airbyte_builder_routes.py` — draft / validate /
  preview endpoints.

## Docs + rules

- `aqp_docs/airbyte-builder.md` — narrative, AQP-native vs Airbyte-native
  decision.
- `.cursor/rules/airbyte-builder.mdc` — rule 31 scope.
- `AGENTS.md` rule 31 — no `AIRBYTE_ENABLE_UNSAFE_CODE`; Fetcher
  stubs land under `aqp/data/fetchers/userland/`.
