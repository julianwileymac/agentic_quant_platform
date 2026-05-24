"""Command-line entrypoint for pipeline tasks."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any

from .config import PipelineConfig
from .tasks import run_cdc_sync, run_heavy_transform, run_minio_to_postgres, run_raw_ingest, run_vector_sync


def _print_result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pipeline task runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    raw = subparsers.add_parser("raw-ingest", help="Ingest raw data into MinIO")
    raw.add_argument("--source-type", required=True, choices=["http", "rest", "s3", "filesystem"])
    raw.add_argument("--source-name", required=True)
    raw.add_argument("--source-uri", required=True)
    raw.add_argument("--output-prefix", default="raw")
    raw.add_argument("--target-bucket", default=None)
    raw.add_argument("--rest-method", default="GET")
    raw.add_argument("--rest-body-json", default=None)

    transform = subparsers.add_parser("heavy-transform", help="Run heavy transform and stage output")
    transform.add_argument("--source-key", required=True)
    transform.add_argument("--source-bucket", default=None)
    transform.add_argument("--target-bucket", default=None)
    transform.add_argument("--output-prefix", default="processed")
    transform.add_argument("--transform-mode", default="normalize-json")
    transform.add_argument("--target-table", default=None)

    load_pg = subparsers.add_parser("minio-to-postgres", help="Load MinIO object into PostgreSQL")
    load_pg.add_argument("--source-key", required=True)
    load_pg.add_argument("--source-bucket", default=None)
    load_pg.add_argument("--target-table", default="pipeline_curated_records")

    vector = subparsers.add_parser("vector-sync", help="Chunk/embed and write to Milvus + ChromaDB")
    vector.add_argument("--source-key", required=True)
    vector.add_argument("--source-bucket", default=None)
    vector.add_argument("--collection-name", default="pipeline_documents")
    vector.add_argument("--pipeline-name", default="vector-sync")
    vector.add_argument("--text-field", default="text")

    cdc = subparsers.add_parser("cdc-sync", help="Run incremental sync from PostgreSQL source")
    cdc.add_argument("--pipeline-name", required=True)
    cdc.add_argument("--source-table", required=True)
    cdc.add_argument("--primary-key", default="id")
    cdc.add_argument("--updated-at-column", default="updated_at")
    cdc.add_argument("--batch-size", type=int, default=500)
    cdc.add_argument("--output-prefix", default="cdc")
    cdc.add_argument("--output-bucket", default=None)

    av = subparsers.add_parser(
        "alphavantage-bulk",
        help="Bulk-load Alpha Vantage data into MinIO via the custom client engine.",
    )
    av.add_argument("--category", required=True,
                    help="timeseries|intraday-backfill|fundamentals|universe|news|earnings|"
                         "fx|crypto|commodities|economics|technicals|bulk")
    av.add_argument("--symbols", default="",
                    help="Comma-separated tickers / commodity names / indicators.")
    av.add_argument("--start-date", default=None, help="YYYY-MM-DD or YYYY-MM")
    av.add_argument("--end-date", default=None, help="YYYY-MM-DD or YYYY-MM")
    av.add_argument("--target-bucket", default="av-raw")
    av.add_argument("--target-prefix", default="")
    av.add_argument("--extra-params", default=None,
                    help="JSON-encoded extra parameters passed to the loader.")
    av.add_argument("--api-key-file", default=None)
    av.add_argument("--cache-backend", default="memory",
                    choices=("memory", "sqlite", "redis", "none"))

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = PipelineConfig()

    if args.command == "raw-ingest":
        _print_result(
            run_raw_ingest(
                config=config,
                source_type=args.source_type,
                source_name=args.source_name,
                source_uri=args.source_uri,
                output_prefix=args.output_prefix,
                target_bucket=args.target_bucket,
                rest_method=args.rest_method,
                rest_body_json=args.rest_body_json,
            )
        )
        return

    if args.command == "heavy-transform":
        _print_result(
            run_heavy_transform(
                config=config,
                source_key=args.source_key,
                source_bucket=args.source_bucket,
                target_bucket=args.target_bucket,
                output_prefix=args.output_prefix,
                transform_mode=args.transform_mode,
                target_table=args.target_table,
            )
        )
        return

    if args.command == "minio-to-postgres":
        _print_result(
            run_minio_to_postgres(
                config=config,
                source_key=args.source_key,
                source_bucket=args.source_bucket,
                target_table=args.target_table,
            )
        )
        return

    if args.command == "vector-sync":
        _print_result(
            run_vector_sync(
                config=config,
                source_key=args.source_key,
                source_bucket=args.source_bucket,
                collection_name=args.collection_name,
                pipeline_name=args.pipeline_name,
                text_field=args.text_field,
            )
        )
        return

    if args.command == "cdc-sync":
        _print_result(
            run_cdc_sync(
                config=config,
                pipeline_name=args.pipeline_name,
                source_table=args.source_table,
                primary_key=args.primary_key,
                updated_at_column=args.updated_at_column,
                batch_size=args.batch_size,
                output_prefix=args.output_prefix,
                output_bucket=args.output_bucket,
            )
        )
        return

    if args.command == "alphavantage-bulk":
        from .alphavantage_io import run_bulk_load

        symbols = [s.strip() for s in (args.symbols or "").split(",") if s.strip()]
        extra = json.loads(args.extra_params) if args.extra_params else {}
        date_range: dict[str, str] = {}
        if args.start_date:
            date_range["start"] = args.start_date
        if args.end_date:
            date_range["end"] = args.end_date
        result = run_bulk_load(
            config=config,
            category=args.category,
            symbols=symbols,
            date_range=date_range or None,
            extra_params=extra,
            target_bucket=args.target_bucket,
            target_prefix=args.target_prefix,
            api_key_file=args.api_key_file,
            cache_backend=args.cache_backend,
        )
        _print_result(asdict(result))
        return

    raise RuntimeError(f"Unknown command {args.command}")


if __name__ == "__main__":
    main()

