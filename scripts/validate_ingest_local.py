"""Manual validation harness for the Iceberg ingestion pipeline.

Walks each of the user-supplied source directories
(CFPB / USPTO / FDA / SEC by default), runs
:class:`aqp.data.pipelines.IngestionPipeline.run_path` against each
with a configurable row cap, prints the resulting :class:`IngestionReport`,
and writes a JSON summary under ``data/ingest_reports/<source>.json``.

This is *not* a pytest run — it's an interactive harness intended to be
invoked once the platform side is up:

.. code-block:: powershell

    python scripts/validate_ingest_local.py `
        --source "C:/Users/Julian Wiley/Downloads/cfpb" `
        --source "C:/Users/Julian Wiley/Downloads/uspto" `
        --source "C:/Users/Julian Wiley/Downloads/fda" `
        --source "C:/Users/Julian Wiley/Downloads/sec" `
        --max-rows 200000

Add ``--no-annotate`` to skip the LLM annotation step.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("validate_ingest_local")


DEFAULT_SOURCES = [
    "C:/Users/Julian Wiley/Downloads/cfpb",
    "C:/Users/Julian Wiley/Downloads/uspto",
    "C:/Users/Julian Wiley/Downloads/fda",
    "C:/Users/Julian Wiley/Downloads/sec",
]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def _short(p: str | Path) -> str:
    pp = Path(p)
    return pp.name or str(pp)


def _progress(phase: str, message: str) -> None:
    logger.info("[%s] %s", phase, message)


def run_one(source: Path, *, namespace: str, max_rows: int | None, max_files: int | None,
            annotate: bool, output_dir: Path) -> dict:
    from aqp.data.pipelines import IngestionPipeline

    started = time.time()
    pipe = IngestionPipeline(
        progress_cb=_progress,
        max_rows_per_dataset=max_rows,
        max_files_per_dataset=max_files,
    )
    report = pipe.run_path(
        source,
        namespace=namespace,
        table_prefix=_short(source).lower(),
        annotate=annotate,
    )
    elapsed = time.time() - started
    payload = report.to_dict()
    payload["elapsed_seconds"] = elapsed

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{_short(source).lower()}.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("Report written → %s (%.1fs)", out_path, elapsed)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        help="Repeatable. Path to a CFPB/USPTO/FDA/SEC-style directory or single archive.",
    )
    parser.add_argument(
        "--namespace",
        default="aqp_ingest",
        help="Iceberg namespace to land tables under (default: aqp_ingest).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=200_000,
        help="Per-dataset row cap. 0 disables the cap.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=200,
        help="Per-dataset file cap. 0 disables the cap.",
    )
    parser.add_argument("--no-annotate", action="store_true", help="Skip LLM annotation.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/ingest_reports"),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    sources = [Path(s).expanduser() for s in (args.source or DEFAULT_SOURCES)]
    sources = [s for s in sources if s.exists()]
    if not sources:
        logger.error("No valid source paths found. Pass --source.")
        return 2

    summaries: dict[str, dict] = {}
    for src in sources:
        logger.info("─── Processing %s ───", src)
        try:
            payload = run_one(
                src,
                namespace=args.namespace,
                max_rows=(args.max_rows or None),
                max_files=(args.max_files or None),
                annotate=not args.no_annotate,
                output_dir=args.output_dir,
            )
            summaries[str(src)] = {
                "tables": len(payload.get("tables", [])),
                "rows_written": sum(int(t.get("rows_written", 0)) for t in payload.get("tables", [])),
                "errors": payload.get("errors", []),
                "elapsed_seconds": payload.get("elapsed_seconds"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline failed for %s", src)
            summaries[str(src)] = {"error": str(exc)}

    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2, default=str), encoding="utf-8")
    logger.info("Aggregate summary → %s", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
