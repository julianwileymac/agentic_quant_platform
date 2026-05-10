# Data discovery (active catalog browser)

> Phase 1 of the self-service data fabric expansion. The discovery
> surface unifies four sources into a single browser so quantitative
> researchers can see ingested datasets and uningested external
> sources side-by-side, edit pending entries, and promote them into
> the Airbyte builder with one click.

The phase plan is
[`.cursor/plans/data-self-service-phase-1.plan.md`](../.cursor/plans/data-self-service-phase-1.plan.md);
the master plan is in `~/.cursor/plans/`.

## What gets merged

[`DiscoveryService.list`](../aqp/data/discovery/service.py) merges
the four sources into one paged stream of
[`DiscoveryEntry`](../aqp/data/discovery/types.py) records, dedup'd
by `(provider, name)`:

1. `dataset_catalogs` (Postgres) — ingested + pending +
   external-only entries.
2. `source_library_entries` (Postgres) — pending external sources
   with import URI / docs URL but no `DatasetCatalog` row yet.
3. `airbyte_connections` (Postgres) — connection inventory; lifecycle
   = `ingested` once `last_sync_status='succeeded'`, else `pending`.
4. Iceberg orphans — tables present in the catalog but missing from
   Postgres. Surfaced as `lifecycle_state='orphan'` so the operator
   can either re-register or drop them.

## Lifecycle vocabulary

| State | Meaning |
| --- | --- |
| `ingested` | Has a materialised payload (Iceberg table or completed Airbyte sync). |
| `pending` | Configured but not yet materialised (e.g. an Airbyte connection awaiting first run, or a placeholder catalog row). |
| `orphan` | Iceberg table present without a Postgres row. Promote to register, or drop to clean up. |
| `external_only` | A `SourceLibraryEntry` or external descriptor that hasn't been promoted yet. |

## REST surface

[`/discovery/*`](../aqp/api/routes/discovery.py):

- `GET /discovery/entries?lifecycle=&provider=&kind=&search=&cursor=&limit=`
- `GET /discovery/entries/{id}`
- `POST /discovery/entries` — register a new external source (creates
  a `DatasetCatalog` row with `is_ingested=False`,
  `dataset_kind="external"`, `external_spec_json` populated).
- `PATCH /discovery/entries/{id}` — edit description, tags, source
  URI, docs URL, suggested connector / kind.
- `DELETE /discovery/entries/{id}` — remove pending / external rows
  (refuses ingested rows with HTTP 409).
- `POST /discovery/entries/{id}/promote` — emits a
  `LineageEvent(transform_kind="discovery.promoted")` and returns
  the `redirect_url` the frontend follows. Phase 2's Airbyte builder
  consumes the `?from=discovery&entry_id=…` deep-link.
- `GET /discovery/entries/{id}/lineage` — reuses the existing
  metadata catalog lineage walker.

## DataMCPTools

[`aqp/data/mcp/tools/discovery.py`](../aqp/data/mcp/tools/discovery.py):

- `data.discovery.browse` — inventory query with the same filters as
  the REST surface.
- `data.discovery.describe` — fetch one entry's full payload.
- `data.discovery.promote` — mutating; returns the deep-link URL.

Agents call these tools through the standard MCP bridge so AGENTS
rule 22 (no direct Postgres / Iceberg from agent code) keeps holding.

## Lineage events emitted

| `transform_kind` | When | Source / target | Used by |
| --- | --- | --- | --- |
| `discovery.created` | `POST /discovery/entries` | target = new `DatasetCatalog.id` | catalog timeline, audit |
| `discovery.promoted` | `POST /discovery/entries/{id}/promote` | target = entry id | catalog timeline, "what came from where" graph |

## Frontend

[`/data/discovery`](../frontend/src/routes/data/discovery/page.tsx)
mounts [`DiscoveryBrowser`](../frontend/src/components/data/DiscoveryBrowser.tsx).
The component is built on the Phase 0 primitives:

- Filter chips for `lifecycle` driven by counts from the cache.
- Provider / kind dropdowns are
  [`<EntityPicker kind="datasets" />`](../frontend/src/components/common/EntityPicker.tsx)
  / `<EntityPicker kind="dataset_kinds" />` — never free-text.
- Detail drawer surfaces description, tags, suggested connector, and
  the two promote buttons. The "Promote to Airbyte builder" path
  navigates to `/airbyte/builder?from=discovery&entry_id=<uuid>`
  which Phase 2 will pre-fill.

## Don't

- **Don't** mutate ingested rows through `/discovery/entries`. Use
  `/metadata-catalog/datasets` (which has its own validation +
  audit). Discovery is for the uningested half of the catalog.
- **Don't** edit a virtual entry id (one starting with `orphan:`,
  `library:`, or `airbyte:`). They're synthesised at read time —
  promote first, edit afterward.
- **Don't** bypass `cache_write_through` from a discovery mutation.
  Frontend dropdowns rely on the write-through to see the new
  entry without waiting for the next prefetch cycle.
