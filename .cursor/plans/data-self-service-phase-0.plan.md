# Phase 0 — Foundation: BaseDataset + MetadataCache + EntityPicker

Companion to the master plan at
`~/.cursor/plans/self-service_data_fabric_phased_a38813ba.plan.md`.
This phase ships the primitives that phases 1-3 depend on:

1. A Kedro-style `BaseDataset` abstraction so every readable / writable
   thing in the platform — Iceberg table, parquet path, REST API,
   partitioned blob, Redis key — has a uniform `_load` / `_save` /
   `_describe` surface and a serialisable `DatasetSpec`.
2. A Redis metadata-prefetch cache (`MetadataCache`) so the UI can
   render entity dropdowns from sub-millisecond `ZRANGEBYLEX` calls
   instead of free-text inputs. Write-through invalidation keeps it
   consistent with Postgres.
3. An `EntityPicker` React component that's the only sanctioned input
   for an entity-name field anywhere in the frontend.

Acceptance: every dropdown in the AQP frontend that names a dataset,
namespace, sink kind, project, or Airbyte connector reads from the
cache; the master plan's "no free-text entity input" rule is
enforceable from this phase forward.

## File-by-file checklist

### Backend — `aqp/data/datasets/` (new package)

- [`aqp/data/datasets/__init__.py`](../../aqp/data/datasets/__init__.py)
  re-exports `BaseDataset`, `DatasetSpec`, `register_dataset_kind`,
  `get_dataset_kind`, `build_dataset`, and the bundled kinds.
- [`aqp/data/datasets/base.py`](../../aqp/data/datasets/base.py)
  `BaseDataset` ABC with class attribute `kind: ClassVar[str]`,
  hashable `DatasetSpec`, and abstract `_load(...)` / `_save(...)` /
  `_describe()` / `exists()` / `release()` methods. `__init_subclass__`
  hook calls `register_dataset_kind(cls.kind, cls)` so subclasses
  self-register.
- [`aqp/data/datasets/spec.py`](../../aqp/data/datasets/spec.py)
  Pydantic `DatasetSpec` with `kind`, `config: dict`,
  `medallion_layer: MedallionLayer | None`,
  `business_metadata: dict`, `data_contract: dict`, plus
  `compute_hash()` returning a sha256 over canonical JSON for the
  `dataset_catalogs.spec_hash` column.
- [`aqp/data/datasets/registry.py`](../../aqp/data/datasets/registry.py)
  thread-safe registry. `@register_dataset_kind("iceberg")`,
  `get_dataset_kind("iceberg")`, `list_dataset_kinds()`,
  `build_dataset(spec_or_dict) -> BaseDataset`. Mirrors the existing
  `aqp/core/registry.py` shape but scoped to dataset kinds so we can
  enumerate from the cache without colliding with strategies / engines.
- `aqp/data/datasets/kinds/`:
  - [`iceberg.py`](../../aqp/data/datasets/kinds/iceberg.py)
    `IcebergDataset` wrapping `iceberg_catalog.append_arrow` /
    `read_arrow`. `kind = "iceberg"`. Validates medallion namespace via
    `validate_layer_for_namespace` on `_save`.
  - [`parquet.py`](../../aqp/data/datasets/kinds/parquet.py)
    `ParquetDataset` (`kind = "parquet"`) — fsspec-backed read/write.
  - [`partitioned.py`](../../aqp/data/datasets/kinds/partitioned.py)
    Kedro `PartitionedDataset` analogue (`kind = "partitioned"`).
  - [`api.py`](../../aqp/data/datasets/kinds/api.py)
    `APIDataset` (`kind = "api"`) — HTTP/REST with credentials
    resolved through `aqp.credentials.CredentialResolver`. Read-only
    by default; `_save` raises unless explicitly enabled. Supports
    pagination + auth strategies declared in `spec.config`.
  - [`csv.py`](../../aqp/data/datasets/kinds/csv.py)
    Pandas-backed CSV (`kind = "csv"`).
  - [`sql.py`](../../aqp/data/datasets/kinds/sql.py)
    `SQLDataset` (`kind = "sql"`) — round-trips through
    `get_session` for read; raises on `_save` (writes go through
    LedgerWriter / migrations).
  - [`redis_kv.py`](../../aqp/data/datasets/kinds/redis_kv.py)
    `RedisKVDataset` (`kind = "redis_kv"`) — read/write a single Redis
    key (string / hash / json).
  - [`external.py`](../../aqp/data/datasets/kinds/external.py)
    `ExternalDataset` (`kind = "external"`) — sentinel for the
    "uningested but discoverable" entries Phase 1 introduces.
    `_load` raises with a hint to promote via the discovery browser.
- [`aqp/data/datasets/exceptions.py`](../../aqp/data/datasets/exceptions.py)
  `DatasetNotMaterialized`, `DatasetKindUnknown`, `DatasetSaveDisabled`.

### Backend — `aqp/cache/` (new package)

- [`aqp/cache/__init__.py`](../../aqp/cache/__init__.py)
  re-exports `MetadataCache`, `cache_write_through`,
  `cache_invalidate`, `MetadataPrefetcher`, `get_cache`.
- [`aqp/cache/client.py`](../../aqp/cache/client.py)
  thin wrapper over `redis.from_url(settings.redis_url)`. `MetadataCache`
  exposes `zadd`, `zrange_lex`, `zrem`, `hset`, `hget`, `hdel`,
  `pipeline()`, `search(prefix)` (FT-or-fallback). Uses the existing
  redis-py with `decode_responses=True` for cache reads (different from
  `redis_store.py` which keeps raw bytes for vectors).
  In-memory fallback when redis-py / Redis unavailable so unit tests +
  the local dev loop never hard-fail.
- [`aqp/cache/keys.py`](../../aqp/cache/keys.py)
  every cache key as a constant. Single source of truth so other
  modules never hand-construct prefixes:
  `aqp:cache:datasets:names`, `aqp:cache:datasets:by_id:{id}`,
  `aqp:cache:namespaces:names`, `aqp:cache:sinks:kinds`,
  `aqp:cache:sinks:names`, `aqp:cache:airbyte:connectors:names`,
  `aqp:cache:projects:names`, `aqp:cache:credentials:names`,
  `aqp:cache:dataset_kinds:names`. Each helper returns the
  fully-qualified key for a `(category, scope)` pair.
- [`aqp/cache/prefetch.py`](../../aqp/cache/prefetch.py)
  `MetadataPrefetcher.run_full(session)` walks Postgres and dataset-kind
  registry, populating ZSETs and HASHes via Redis pipelines (Redis
  `conn-pipelining` rule). `MetadataPrefetcher.run_incremental(...)`
  for the periodic Celery refresh.
- [`aqp/cache/invalidation.py`](../../aqp/cache/invalidation.py)
  `cache_write_through(category, payload)` and
  `cache_invalidate(category, identifier)`. Idempotent. Failures log a
  warning but never raise into mutation routes — staleness is preferred
  to write failure.
- [`aqp/cache/search.py`](../../aqp/cache/search.py)
  `try_create_full_text_index()` attempts `FT.CREATE` for the dataset
  hash; falls back to `ZRANGEBYLEX` + manual filter. Same pattern as
  `aqp/rag/redis_store.py`.
- [`aqp/cache/lifespan.py`](../../aqp/cache/lifespan.py)
  `prefetch_at_startup(app)` — async function called from
  `aqp/api/main.py` lifespan. Logs but never raises.

### Backend — settings

- Append to [`aqp/config/settings.py`](../../aqp/config/settings.py)
  new `# --- Metadata cache (data fabric phase 0) ---` block:
  - `cache_enabled: bool = True`
  - `cache_redis_url: str = ""` (empty falls back to `redis_url`)
  - `cache_redis_db: int = 2`
  - `cache_key_prefix: str = "aqp:cache"`
  - `cache_refresh_interval_s: int = 300`
  - `cache_master_ttl_s: int = 86400`
  - `cache_instance_ttl_s: int = 900`
  - `cache_fulltext_index: bool = True`

### Backend — Alembic migration

- [`alembic/versions/0032_dataset_kind_ingestion_flag.py`](../../alembic/versions/0032_dataset_kind_ingestion_flag.py)
  `revision = "0032_dataset_kind_ingestion_flag"`,
  `down_revision = "0031_analysis_layer"`. Add to
  `dataset_catalogs`:
  - `dataset_kind STRING(64)` nullable, indexed
  - `is_ingested BOOLEAN` nullable, indexed
  - `spec_hash STRING(64)` nullable, indexed
  - `external_spec_json JSONB` nullable
  Backfill: rows with `iceberg_identifier IS NOT NULL` get
  `dataset_kind='iceberg'`, `is_ingested=true`. SQLite-friendly: use
  `sa.JSON` not `sa.dialects.postgresql.JSONB` (Pydantic handles
  conversion in the read path; mirrors `models_analysis.py`).

### Backend — ORM update

- Append to [`aqp/persistence/models.py::DatasetCatalog`](../../aqp/persistence/models.py)
  the four new columns (mirroring the migration). No new model file —
  this is a column-only extension of the existing primitive.

### Backend — API route

- [`aqp/api/routes/cache.py`](../../aqp/api/routes/cache.py)
  thin read-only router prefix `/cache`:
  - `GET /cache/datasets?prefix=&limit=&cursor=` — `ZRANGEBYLEX` page
  - `GET /cache/datasets/{id}` — hash fetch
  - `GET /cache/namespaces`
  - `GET /cache/sinks/kinds`
  - `GET /cache/sinks/names`
  - `GET /cache/airbyte/connectors`
  - `GET /cache/projects`
  - `GET /cache/credentials`
  - `GET /cache/dataset-kinds`
  - `POST /cache/refresh` — admin-only: triggers full prefetch
- Wire the new router in
  [`aqp/api/main.py`](../../aqp/api/main.py) (added to imports + `include_router`)
  and call `prefetch_at_startup` in the existing `lifespan`
  context manager.

### Backend — write-through hooks

Wire `cache_write_through` into the existing mutation paths so the
cache stays consistent without a full prefetch cycle:

- [`aqp/services/metadata_catalog_service.py`](../../aqp/services/metadata_catalog_service.py)
  `patch_dataset` and the `create_metadata_dataset` route handler in
  [`aqp/api/routes/metadata_catalog.py`](../../aqp/api/routes/metadata_catalog.py)
  call `cache_write_through("datasets", payload)` after `commit`.
- [`aqp/api/routes/airbyte.py`](../../aqp/api/routes/airbyte.py)
  `create_connection` calls `cache_write_through("airbyte_connectors",
  payload)`.
- [`aqp/api/routes/sinks.py`](../../aqp/api/routes/sinks.py) (existing)
  `create_sink` / `update_sink` call
  `cache_write_through("sinks", payload)`.

### Frontend — `EntityPicker`

- [`frontend/src/lib/api/cache.ts`](../../frontend/src/lib/api/cache.ts)
  typed client for `/cache/*` endpoints.
- [`frontend/src/components/common/EntityPicker.tsx`](../../frontend/src/components/common/EntityPicker.tsx)
  async, searchable, virtualised dropdown. Variants:
  `kind: "dataset" | "namespace" | "sink-kind" | "sink-name" | "airbyte-connector" | "project" | "credential" | "dataset-kind"`.
  Backed by `useApiQuery` against the matching `/cache/...` endpoint
  with `staleTime: 5_000`. Emits `value: string`. Disables typing for
  values not in the cache; allows free-text only when the variant is
  explicitly `allowCustom`.
- [`frontend/src/components/common/EntityPicker.test.tsx`](../../frontend/src/components/common/EntityPicker.test.tsx)
  renders, searches, selects.

### Frontend — wire into existing forms

Replace top-priority free-text entity inputs with `EntityPicker`. We
do not boil the ocean here — pick the loudest five surfaces:

- [`frontend/src/components/airbyte/AirbyteWorkspace.tsx`](../../frontend/src/components/airbyte/AirbyteWorkspace.tsx)
  the existing `<select>` for connectors becomes
  `<EntityPicker kind="airbyte-connector" />`.
- [`frontend/src/routes/airbyte/connectors/page.tsx`](../../frontend/src/routes/airbyte/connectors/page.tsx)
  if it has any free-text connector input, replace.
- The `MetadataDatasetCreateRequest` modal in any catalog page that
  takes a `provider` / `domain` / `namespace` free-text field —
  `provider` becomes `EntityPicker kind="dataset" allowCustom`,
  `namespace` becomes `EntityPicker kind="namespace"`.
- Sink registry forms — `kind` becomes `EntityPicker kind="sink-kind"`.
- Project / workspace selectors in the topbar — `EntityPicker kind="project"`.

Phases 1-3 will incrementally replace the rest as they touch each
form. There is no big-bang refactor required this phase.

### Tests

- [`tests/data/datasets/test_base.py`](../../tests/data/datasets/test_base.py)
  metaclass auto-registration, `DatasetSpec.compute_hash()` is stable.
- [`tests/data/datasets/test_iceberg_kind.py`](../../tests/data/datasets/test_iceberg_kind.py)
  `IcebergDataset._save` validates medallion namespace.
- [`tests/data/datasets/test_partitioned_kind.py`](../../tests/data/datasets/test_partitioned_kind.py)
  partitioned read returns sorted partition keys.
- [`tests/cache/test_client.py`](../../tests/cache/test_client.py)
  in-memory fallback round-trips ZADD/ZRANGEBYLEX/HSET/HGET.
- [`tests/cache/test_prefetch.py`](../../tests/cache/test_prefetch.py)
  monkeypatches the Postgres session and asserts the prefetcher
  populates the expected keys.
- [`tests/cache/test_invalidation.py`](../../tests/cache/test_invalidation.py)
  write-through after a dataset patch is reflected in the next
  ZRANGEBYLEX page.
- [`tests/api/test_cache_routes.py`](../../tests/api/test_cache_routes.py)
  the `/cache/*` endpoints return paged results.

### Docs

- [`aqp_docs/docs/concepts/data/datasets-catalog.md`](../../aqp_docs/docs/concepts/data/datasets-catalog.md)
  new — the Kedro lens, BaseDataset taxonomy, kind registry, when to
  add a new kind vs. a new manifest.
- [`aqp_docs/docs/concepts/data/metadata-cache.md`](../../aqp_docs/docs/concepts/data/metadata-cache.md)
  new — key naming, prefetch lifecycle, write-through, TTL strategy,
  fallback behaviour.
- [`.cursor/rules/datasets.mdc`](../../.cursor/rules/datasets.mdc)
  scopes the `BaseDataset` ABC + registry contract.
- [`.cursor/rules/cache.mdc`](../../.cursor/rules/cache.mdc)
  scopes the cache key namespace and write-through requirement.
- Update [`aqp_docs/docs/intro/index.md`](../../aqp_docs/docs/intro/index.md) to link the two new
  docs.
- Update [`AGENTS.md`](../../AGENTS.md):
  - Hard rule **29**: every catalog entry is a `BaseDataset`-derived
    spec; `MetadataCache` is the single read path for entity
    dropdowns.
  - Project map entry for `aqp/data/datasets/` and `aqp/cache/`.
  - "Where to look for X" entries: "Add a dataset kind",
    "Add a cached entity dropdown".
  - Quick reference entries for `BaseDataset`, `MetadataCache`,
    `cache_write_through`.

## Sequencing inside Phase 0

1. Settings + `aqp/cache/` package (so the dataset kinds can use
   `RedisKVDataset` if needed) + dataset kinds + `aqp/data/datasets/`.
2. ORM column extension + Alembic migration.
3. `aqp/api/routes/cache.py` + lifespan hook + write-through wiring.
4. `EntityPicker` + audit pass on the five priority forms.
5. Tests + docs + cursor rules + AGENTS.md update.

## Out of scope for Phase 0

- Migrating existing fetcher classes into `BaseDataset` retroactively
  (a separate plan after Phase 3 lands).
- The discovery browser (Phase 1).
- The Airbyte builder rewrite (Phase 2).
- The Dagster sandbox (Phase 3).
