"""End-to-end smoke test for the host-persisted Iceberg catalog.

Run inside the api/worker container (or natively when ``AQP_ICEBERG_*`` env
variables are pointed at the host warehouse):

    python -m scripts.iceberg_smoke

The script:

1. Resolves the configured catalog (PyIceberg SQL mode by default).
2. Creates / refreshes the ``aqp.smoke_test`` table from a 3-row Arrow
   table.
3. Appends a second batch.
4. Lists tables, snapshots, and the underlying Parquet files.
5. Reads the table back and prints it.

Run it once, ``docker compose down`` the api+worker, ``docker compose up
-d api worker`` again, and re-run with ``--inspect-only`` to confirm the
catalog state survived the container teardown.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow as pa

from aqp.config import settings
from aqp.data import iceberg_catalog


SMOKE_NAMESPACE = "aqp_smoke"
SMOKE_TABLE = "smoke_test"
SMOKE_IDENT = f"{SMOKE_NAMESPACE}.{SMOKE_TABLE}"


def _make_batch(start: int, n: int) -> pa.Table:
    return pa.table(
        {
            "id": pa.array(list(range(start, start + n)), type=pa.int64()),
            "label": pa.array([f"row_{i}" for i in range(start, start + n)], type=pa.string()),
            "score": pa.array([float(i) * 0.5 for i in range(start, start + n)], type=pa.float64()),
        }
    )


def _print_header(title: str) -> None:
    print()
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def _print_catalog_summary() -> None:
    _print_header("Catalog summary")
    print(f"warehouse:    {Path(settings.iceberg_warehouse).resolve()}")
    print(f"staging dir:  {Path(settings.iceberg_staging_dir).resolve()}")
    print(f"rest uri:     {settings.iceberg_rest_uri or '(SQL mode)'}")
    print(f"catalog name: {settings.iceberg_catalog_name}")
    print(f"namespaces:   {iceberg_catalog.list_namespaces() or '(none)'}")


def run(*, inspect_only: bool) -> int:
    _print_catalog_summary()

    if not inspect_only:
        _print_header("Writing smoke batches")
        iceberg_catalog.ensure_namespace(SMOKE_NAMESPACE)
        first = _make_batch(0, 3)
        second = _make_batch(3, 2)
        iceberg_catalog.create_or_replace_table(SMOKE_IDENT, first.schema)
        iceberg_catalog.append_arrow(SMOKE_IDENT, first)
        iceberg_catalog.append_arrow(SMOKE_IDENT, second)
        print(f"wrote {first.num_rows + second.num_rows} rows to {SMOKE_IDENT}")

    _print_header(f"Inspecting {SMOKE_IDENT}")
    table = iceberg_catalog.load_table(SMOKE_IDENT)
    if table is None:
        print(f"[FAIL] table {SMOKE_IDENT} not found in the catalog")
        return 1

    metadata = iceberg_catalog.table_metadata(SMOKE_IDENT)
    print(f"location: {metadata.get('location')}")
    print(f"fields:   {[f['name'] for f in metadata.get('fields', [])]}")
    snapshots = iceberg_catalog.snapshot_history(SMOKE_IDENT)
    print(f"snapshots ({len(snapshots)}):")
    for snap in snapshots:
        print(
            f"  - id={snap['snapshot_id']} parent={snap['parent_snapshot_id']} "
            f"op={snap['operation']} ts={snap['timestamp_ms']}"
        )

    arrow = iceberg_catalog.read_arrow(SMOKE_IDENT)
    if arrow is None:
        print("[FAIL] read_arrow returned None")
        return 1
    df = arrow.to_pandas()
    print(f"row count: {len(df)}")
    print(df.head(20).to_string(index=False))

    location = metadata.get("location") or ""
    if location.startswith("file://"):
        location_path = Path(location[len("file://") :])
        if location_path.exists():
            data_files = sorted(p for p in location_path.rglob("*.parquet"))
            metadata_files = sorted(p for p in location_path.rglob("metadata/*.metadata.json"))
            print()
            print(f"data files on host ({len(data_files)}):")
            for p in data_files:
                print(f"  - {p}")
            print(f"metadata files on host ({len(metadata_files)}):")
            for p in metadata_files:
                print(f"  - {p}")

    print()
    print("[OK] smoke test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Skip the write step and only verify that an existing table is readable.",
    )
    args = parser.parse_args()
    return run(inspect_only=bool(args.inspect_only))


if __name__ == "__main__":
    sys.exit(main())
