"""``data.duckdb_sql`` — ad-hoc SQL via DuckDB over Iceberg / Parquet.

Phase 2 wires DuckDB in-process; the SQL can reference any upstream
node's frame by alias (e.g. ``SELECT * FROM upstream_a JOIN upstream_b
USING (timestamp)``).
"""
from __future__ import annotations

import logging

import pandas as pd

from aqp.lab.executors._helpers import base_locator, stash_arrow_output
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    sql = str(params.get("sql") or "").strip()
    if not sql:
        return NodeResult(status="error", error="data.duckdb_sql needs non-empty 'sql'")
    try:
        import duckdb
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"duckdb unavailable: {exc}")

    con = duckdb.connect()
    # Register every upstream frame as a DuckDB view named after the
    # upstream port (so the SQL can refer to e.g. ``SELECT * FROM bars``).
    arrow = ctx.extras.get("_arrow_outputs", {}) if ctx.extras else {}
    for port, locator in (ctx.upstream or {}).items():
        if not isinstance(locator, dict):
            continue
        node_id = locator.get("node_id")
        if node_id in arrow:
            con.register(port, arrow[node_id])
    try:
        result = con.execute(sql).fetchdf()
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"duckdb SQL failed: {exc}")
    if not isinstance(result, pd.DataFrame):
        result = pd.DataFrame(result)
    stash_arrow_output(ctx, node.id, result)
    return NodeResult(
        status="done",
        output_locator={**base_locator(node.id, result), "sql_first_64": sql[:64]},
        metrics={"rows": int(len(result))},
        log_label=f"duckdb:{len(result)} rows",
    )
