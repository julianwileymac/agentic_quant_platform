"""Bounded health and inventory probe for the Iceberg catalog engine.

Run as ``python -m aqp.data.iceberg_diag`` to get an immediate read-only
status report. Used to disambiguate "Iceberg is down" from "Iceberg is up
but the table is empty" without ever scanning row data.

Exit codes:
- 0: catalog reachable, probe succeeded
- 1: catalog unreachable or probe raised
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from aqp.data import iceberg_catalog


logger = logging.getLogger("aqp.data.iceberg_diag")


def collect_status(
    *,
    timeout: float | None = None,
    namespaces: list[str] | None = None,
    show_metadata_for: list[str] | None = None,
    table_limit_per_namespace: int = 50,
) -> dict[str, Any]:
    """Return a JSON-friendly status dict for the catalog engine.

    Never raises — failures are recorded in the returned ``error`` fields so
    callers (CLI, dashboards, alerts) get a uniform shape even when the
    catalog is wedged.
    """
    health = iceberg_catalog.health_check(timeout=timeout)
    status: dict[str, Any] = {
        "health": health,
        "namespaces": [],
        "tables_by_namespace": {},
        "table_metadata": {},
    }
    if not health.get("ok"):
        return status

    try:
        ns_list = [str(ns) for ns in iceberg_catalog.list_namespaces()]
    except Exception as exc:  # noqa: BLE001
        status["error"] = f"list_namespaces failed: {type(exc).__name__}: {exc}"
        return status
    status["namespaces"] = ns_list

    target_namespaces = list(namespaces) if namespaces else ns_list
    tables_by_ns: dict[str, list[str]] = {}
    for ns in target_namespaces:
        try:
            tables = iceberg_catalog.list_tables(ns)
        except Exception as exc:  # noqa: BLE001
            tables_by_ns[ns] = [f"<error: {type(exc).__name__}: {exc}>"]
            continue
        if table_limit_per_namespace > 0:
            tables = tables[:table_limit_per_namespace]
        tables_by_ns[ns] = tables
    status["tables_by_namespace"] = tables_by_ns

    if show_metadata_for:
        meta_section: dict[str, Any] = {}
        for identifier in show_metadata_for:
            try:
                meta_section[identifier] = iceberg_catalog.table_metadata(identifier)
            except Exception as exc:  # noqa: BLE001
                meta_section[identifier] = {
                    "error": f"{type(exc).__name__}: {exc}",
                }
        status["table_metadata"] = meta_section

    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AQP Iceberg catalog health probe")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Bounded timeout for the catalog probe (seconds; defaults to settings).",
    )
    parser.add_argument(
        "--namespace",
        action="append",
        default=None,
        help="Restrict the probe to a single namespace (repeatable).",
    )
    parser.add_argument(
        "--metadata-for",
        action="append",
        default=None,
        help="Fully qualified table identifier(s) to fetch metadata for (repeatable).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum tables to list per namespace (0 disables the cap).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    status = collect_status(
        timeout=args.timeout,
        namespaces=args.namespace,
        show_metadata_for=args.metadata_for,
        table_limit_per_namespace=int(args.limit),
    )
    print(json.dumps(status, default=str, indent=2, sort_keys=True))
    health = status.get("health") or {}
    return 0 if health.get("ok") else 1


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
