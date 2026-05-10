# Phase 1 — Active Discovery Browser

Companion to the master plan
(`~/.cursor/plans/self-service_data_fabric_phased_*.plan.md`) and to
[`data-self-service-phase-0.plan.md`](data-self-service-phase-0.plan.md).
This phase delivers the unified discovery surface: a single browser
that lists ingested datasets, pending external sources, Iceberg
orphans, and Airbyte connection inventory in one place, with full
CRUD on the "uningested" entries plus a one-click handoff to the
Airbyte builder (which Phase 2 takes over).

Acceptance: `/data/catalog` shows `Ingested | Pending | Orphan | All`
toggles backed by the new `/discovery/*` REST surface; the Promote
button deep-links into `/airbyte/builder?from=discovery&entry_id=…`
with the discovery payload pre-filled into the builder state.

## Backend

### `aqp/data/discovery/` (new package)

- [`aqp/data/discovery/__init__.py`](../../aqp/data/discovery/__init__.py)
  re-exports the public surface (`DiscoveryEntry`,
  `DiscoveryService`, `DiscoveryLifecycleState`).
- [`aqp/data/discovery/types.py`](../../aqp/data/discovery/types.py)
  Pydantic `DiscoveryEntry` + `DiscoveryLifecycleState` literal
  (`ingested | pending | orphan | external_only`).
- [`aqp/data/discovery/service.py`](../../aqp/data/discovery/service.py)
  `DiscoveryService.list(...)`, `.get(id)`, `.create_external(...)`,
  `.patch(id, ...)`, `.delete(id)`, `.promote(id, target_kind)`.
  Merges four sources (in this order, dedupe by `(provider, name)`):
  1. `DatasetCatalog` rows — set `lifecycle_state=ingested` when
     `is_ingested=True OR iceberg_identifier IS NOT NULL`,
     else `pending`.
  2. `SourceLibraryEntry` rows that don't already match a
     `DatasetCatalog` row — `lifecycle_state=external_only`.
  3. Iceberg tables with no Postgres row —
     `lifecycle_state=orphan`.
  4. `AirbyteConnectionRow` entries surfaced as
     `lifecycle_state=pending` when no matching dataset exists yet.

### `aqp/api/routes/discovery.py` (new router)

- `GET /discovery/entries` — paged + filterable.
- `GET /discovery/entries/{id}` — single entry.
- `POST /discovery/entries` — create an external (uningested) entry.
  Backed by `DatasetCatalog` row with `is_ingested=False`,
  `dataset_kind="external"`, `external_spec_json` set.
  Calls `cache_write_through("datasets", payload)` after commit.
- `PATCH /discovery/entries/{id}` — edits description / tags / spec.
- `DELETE /discovery/entries/{id}` — removes external rows; refuses
  to delete `is_ingested=true` rows (returns 409).
- `POST /discovery/entries/{id}/promote` — emits a
  `LineageEvent(transform_kind="discovery.promoted")` and returns
  the deep-link URL for the frontend (Phase 2 reads it).
- `GET /discovery/entries/{id}/lineage` — reuses existing
  `MetadataCatalogService.lineage`.

### `aqp/data/mcp/tools/discovery.py`

`data.discovery.browse`, `data.discovery.describe`,
`data.discovery.promote` — DataMCPTool subclasses so AGENTS rule 22
(agent reads via DataMCPTool only) keeps holding.

### Lineage event additions

`LineageEvent.transform_kind` already accepts free-form strings; add
`"discovery.created"` and `"discovery.promoted"` to the doc list in
`docs/data-discovery.md` so reviewers can see the canonical
vocabulary, but no code change to `LINEAGE_TRANSFORM_KINDS` is
required.

## Frontend

### `frontend/src/components/data/DiscoveryBrowser.tsx` (new)

Three-pane layout:

- Left rail: filter chips (`Ingested | Pending | Orphan | External`),
  search input, kind picker (`<EntityPicker kind="dataset_kinds" />`).
- Center: virtualised data grid with the merged entries.
- Right drawer: detail view (description, tags, lineage graph),
  edit form, "Promote to Airbyte builder" button.

Wire it as the top section of `frontend/src/routes/data/catalog/page.tsx`
(extend, do not replace) so existing dataset detail flows still work.

### Deep-link handler

Phase 2 reads `?from=discovery&entry_id=<uuid>` query param in
`/airbyte/builder` and pre-fills the builder. Phase 1 only needs to
emit the URL.

## Tests

- `tests/data/discovery/test_service.py` — merge + lifecycle
  classification covers all four sources.
- `tests/api/test_discovery_routes.py` — CRUD + cache write-through.

## Docs + rules

- `docs/data-discovery.md` — narrative, the four-source merge, the
  promote handoff.
- `.cursor/rules/discovery.mdc` — AGENTS rule 30 scope.
- `AGENTS.md` rule 30 — discovery.* surfaces are the only operator
  surface for uningested entries; mutations call
  `cache_write_through`.
