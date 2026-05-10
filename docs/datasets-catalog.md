# Datasets catalog (Kedro lens)

> Phase 0 of the self-service data fabric expansion. Every readable
> or writable thing in the platform — Iceberg table, parquet path,
> REST API, partitioned blob, Redis key, plain CSV / SQL queries — is
> a typed [`BaseDataset`](../aqp/data/datasets/base.py) subclass with
> a hashable [`DatasetSpec`](../aqp/data/datasets/spec.py).

The shape is intentionally close to
[`kedro_datasets`](https://docs.kedro.org/projects/kedro-datasets/en/stable/)
so engineers familiar with Kedro can map ideas across without
relearning the abstraction. AQP keeps its existing `Fetcher` /
`SourceNode` / `SinkNode` manifest plumbing intact and adds a
catalog-centric abstraction *on top* so the discovery browser
(Phase 1), the metadata cache (Phase 0), the Airbyte builder codegen
(Phase 2), and the Dagster sandbox (Phase 3) all speak one language.

## The contract

```python
from aqp.data.datasets import BaseDataset, DatasetSpec, build_dataset

spec = DatasetSpec(
    kind="iceberg",
    config={"identifier": "aqp_bronze_demo.bars", "limit": 1000},
    medallion_layer="bronze",
)

dataset = build_dataset(spec)   # -> IcebergDataset instance
table   = dataset.load()         # -> pyarrow.Table
dataset.save(updated_table)      # -> routes through iceberg_catalog.append_arrow
```

Every kind exposes:

- `load()` — return the dataset payload.
- `save(payload)` — persist (raises `DatasetSaveDisabled` for
  read-only kinds like `api`, `sql`, `external`).
- `describe()` — kind-specific descriptor (paths, sizes, schema
  preview).
- `exists()` — cheap probe.
- `release()` — optional teardown hook.

## Bundled kinds

Subclasses self-register through the metaclass
([`BaseDataset.__init_subclass__`](../aqp/data/datasets/base.py)):

| `kind` | Module | Use |
| --- | --- | --- |
| `iceberg` | [`kinds/iceberg.py`](../aqp/data/datasets/kinds/iceberg.py) | The canonical AQP write target. Wraps `iceberg_catalog.append_arrow` so AGENTS rule 3 + rule 21 (medallion namespace) hold. |
| `parquet` | [`kinds/parquet.py`](../aqp/data/datasets/kinds/parquet.py) | Read / write a parquet path via fsspec. |
| `partitioned` | [`kinds/partitioned.py`](../aqp/data/datasets/kinds/partitioned.py) | Kedro `PartitionedDataset` analogue for hive / date / vendor folders. |
| `api` | [`kinds/api.py`](../aqp/data/datasets/kinds/api.py) | HTTP / REST. All credentials resolve through `aqp.credentials.CredentialResolver` (AGENTS rule 26). |
| `csv` | [`kinds/csv.py`](../aqp/data/datasets/kinds/csv.py) | pandas-backed CSV. |
| `sql` | [`kinds/sql.py`](../aqp/data/datasets/kinds/sql.py) | Read-only SQL queries — writes go through Alembic + `LedgerWriter`. |
| `redis_kv` | [`kinds/redis_kv.py`](../aqp/data/datasets/kinds/redis_kv.py) | Single Redis key (string / hash / json). Distinct from `aqp.cache` (which is the metadata-prefetch layer). |
| `external` | [`kinds/external.py`](../aqp/data/datasets/kinds/external.py) | Sentinel for "discoverable but not yet ingested" entries. `load()` raises `DatasetNotMaterialized` so the discovery browser can offer a promote handoff instead of a stack trace. |

## Adding a new kind

1. Subclass `BaseDataset` and set `kind = "your_alias"`.
2. Implement `_load`. Implement `_save` if writable; otherwise set
   `writable = False` and let the base class raise.
3. Optional: implement `_validate_spec` to fail-fast on bad config.
4. Place the file under `aqp/data/datasets/kinds/`.
5. Re-export in `aqp/data/datasets/kinds/__init__.py` so import
   triggers metaclass registration.
6. Mention the alias in this doc table.
7. Add a smoke test under `tests/data/datasets/`.

## How this composes

- **`DatasetCatalog` rows** carry a `dataset_kind` discriminator
  (Alembic 0032) so existing rows can map back to a `DatasetSpec`
  without refactoring everything at once.
- **Phase 0 metadata cache** prefetches the kind registry as a
  whitelist so the `EntityPicker` dropdown in the frontend renders
  the eight kinds without a free-text input.
- **Phase 1 discovery browser** flags rows by `is_ingested`. External
  / pending entries instantiate `ExternalDataset` until they're
  promoted.
- **Phase 2 Airbyte builder** emits a stub `aqp.data.fetchers.Fetcher`
  whose seed config is exactly an `APIDataset` spec.
- **Phase 3 Dagster sandbox** loads `BaseDataset` subclasses inside
  ephemeral defs folders so a researcher can iterate without
  polluting prod state.

## Don't

- Don't open-code Iceberg writes in a custom kind. Use
  `IcebergDataset` and let it call `append_arrow`.
- Don't read `os.environ` for credentials inside `_load` — go through
  `aqp.credentials.CredentialResolver`.
- Don't pickle a `BaseDataset` instance across Celery workers — pass
  the `DatasetSpec` (which is just JSON) and rebuild on the worker.
- Don't bypass `register_dataset_kind` by manipulating the registry
  directly. Use the decorator or rely on the metaclass.
