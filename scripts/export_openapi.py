"""Dump the FastAPI OpenAPI schema to JSON for the webui type generator.

Run from the repo root:

    python -m scripts.export_openapi

Writes ``data/openapi.json`` by default (so the relative path used by
``webui/package.json::scripts.gen:api`` resolves correctly). Override the
output path via ``--out path/to/openapi.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def export(out_path: Path) -> int:
    try:
        from aqp.api.main import app
    except Exception as exc:  # pragma: no cover - import errors surface to the user
        print(f"Failed to import FastAPI app: {exc}", file=sys.stderr)
        return 1

    schema = app.openapi()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")
    print(f"OpenAPI schema written to {out_path} ({out_path.stat().st_size} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI spec to JSON.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data") / "openapi.json",
        help="Destination JSON file (default: data/openapi.json)",
    )
    args = parser.parse_args(argv)
    return export(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
