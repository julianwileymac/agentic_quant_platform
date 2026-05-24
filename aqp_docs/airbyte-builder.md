# Graphical Airbyte connector builder (AQP-native)

> Phase 2 of the self-service data fabric. The builder replaces the
> JSON editor in
> [`AirbyteWorkspace.tsx`](../aqp_client/src/components/airbyte/AirbyteWorkspace.tsx)
> with a schema-driven form that emits either a low-code Airbyte YAML
> manifest **or** an AQP-native
> [`Fetcher`](../aqp/data/fetchers/base.py) stub under
> [`aqp/data/fetchers/userland/`](../aqp/data/fetchers/userland).

The phase plan is
[`.cursor/plans/data-self-service-phase-2.plan.md`](../.cursor/plans/data-self-service-phase-2.plan.md).

## Why AQP-native and not unsafe code

The original prompt called for setting `AIRBYTE_ENABLE_UNSAFE_CODE=true`
on the Airbyte cluster so the builder could inject custom Python
paginators and extractors. We deliberately rejected that path:

- It runs untrusted Python inside Airbyte's worker container —
  outside AQP's lineage, credential, and DataMCPTool guardrails.
- Secrets would have to be passed through Airbyte's config-based
  authenticator, side-stepping
  [`aqp.credentials.CredentialResolver`](../aqp/credentials/resolver.py)
  (AGENTS rule 26).
- Updates to custom logic would land outside `git`, breaking the
  hash-locked spec story that AQP relies on for every other runtime.

Instead the builder ships two outputs:

1. **Low-code YAML manifest** for the easy case — declarative
   pagination, REST authenticator, JSON extractor. Stored on
   `airbyte_connectors.manifest_yaml` and round-trippable.
2. **AQP-native Fetcher stub** for the hard case — generated under
   `aqp/data/fetchers/userland/<slug>.py`, registered via
   `@register_source_fetcher`, credentials resolved through
   `CredentialResolver`. Custom Python lives in our codebase under
   normal review.

## REST surface

[`/airbyte/builder/*`](../aqp/api/routes/airbyte_builder.py):

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/airbyte/builder/cdk-schema` | Parsed `BuilderSection[]` for the form generator. |
| `POST` | `/airbyte/builder/manifest/draft` | State → canonical YAML + validation. |
| `POST` | `/airbyte/builder/manifest/validate` | Structured `errors` / `warnings`. |
| `POST` | `/airbyte/builder/streams/infer` | Probe request + response field inference. |
| `POST` | `/airbyte/builder/codegen/fetcher` | Render AQP Fetcher stub (dry-run). |
| `POST` | `/airbyte/builder/codegen/fetcher` (`commit=true`) | Write to `aqp/data/fetchers/userland/<slug>.py`. |
| `GET` | `/airbyte/builder/state/{id}` | Round-trip persisted form state. |
| `PUT` | `/airbyte/builder/state/{id}` | Save form state + manifest YAML. |

## Form schema

[`aqp.data.airbyte.builder.schema.BUILDER_SCHEMA`](../aqp/data/airbyte/builder/schema.py)
ships an opinionated subset of the Airbyte Low-Code CDK — auth,
requester, paginator, record selector, streams. The frontend
consumes the schema verbatim so adding a field requires updating
the Python definition, not the React component.

## Frontend

[`ConnectorBuilderForm.tsx`](../aqp_client/src/components/airbyte/builder/ConnectorBuilderForm.tsx):

- Schema-driven form generator from `/airbyte/builder/cdk-schema`.
- Authentication block uses `<EntityPicker kind="credentials" />` —
  the form NEVER carries raw secrets.
- "Infer streams" issues the probe request and shows inferred
  fields per stream.
- "Preview AQP Fetcher" generates the stub diff; "Commit" writes the
  file (gated on `AQP_AIRBYTE_BUILDER_CODEGEN_ENABLED`,
  default `true`, plus `AQP_AIRBYTE_BUILDER_OVERWRITE` to overwrite
  an existing file).
- Honours `?from=discovery&entry_id=<uuid>` from Phase 1's promote
  handoff and pre-fills metadata + base URL.

## Persistence

Alembic 0033 adds three columns on `airbyte_connectors`:

- `manifest_yaml` (TEXT) — round-tripped Low-Code CDK YAML.
- `aqp_fetcher_path` (STRING(240)) — dotted module path of the
  generated AQP Fetcher when "Commit" was used.
- `builder_state_json` (JSONB) — raw form state for re-edit.

## Don't

- **Don't** enable `AIRBYTE_ENABLE_UNSAFE_CODE`. Custom Python lives
  under `aqp/data/fetchers/userland/` and runs inside AQP, not
  inside Airbyte's worker.
- **Don't** ship a free-text password / API key field in the
  builder. Credentials always resolve through `CredentialResolver`
  references picked via `EntityPicker`.
- **Don't** edit the generated stubs by hand and re-commit through
  the builder — re-running the generator overwrites the file. Move
  manual edits to a sibling module that imports / extends the stub.
- **Don't** persist `manifest_yaml` outside the `airbyte_connectors`
  row. The frontend reads from `/airbyte/builder/state/{id}`; never
  cache YAML in localStorage.
