"""Run the AQP ingestion pipeline against a single source path.

Designed to be invoked as a subprocess by ``scripts/ingest_regulatory.py``
so each regulatory corpus runs in a fresh Python interpreter, isolating
memory pressure.

Writes a JSON :class:`IngestionReport` payload to the path supplied by
``--report`` (default: stdout). Exits non-zero on uncaught exceptions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aqp.data.pipelines import IngestionPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--report", default="-")
    parser.add_argument("--annotate", action="store_true", default=False)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--chunk-rows", type=int, default=10_000)
    parser.add_argument("--no-director", action="store_true", default=False)
    parser.add_argument(
        "--allowed-namespace",
        action="append",
        default=None,
        help="Repeatable; passed to the Director's allowed-namespace allow-list.",
    )
    args = parser.parse_args()

    def _progress(phase: str, message: str) -> None:
        print(f"[{phase}] {message}", flush=True)

    pipe = IngestionPipeline(
        progress_cb=_progress,
        max_rows_per_dataset=args.max_rows,
        max_files_per_dataset=args.max_files,
        chunk_rows=int(args.chunk_rows),
        director_enabled=False if args.no_director else None,
        allowed_namespaces=args.allowed_namespace,
    )
    report = pipe.run_path(
        path=args.path,
        namespace=args.namespace,
        annotate=bool(args.annotate),
    )
    payload = report.to_dict()
    serialised = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.report == "-":
        print(serialised)
    else:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(serialised, encoding="utf-8")
        print(f"[ok] report → {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
