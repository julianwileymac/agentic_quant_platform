"""``snippet.sql`` executor — user-authored SQL over upstream Arrow / DuckDB.

Phase 1 wires a thin DuckDB wrapper so SQL cells promoted from the
EDA notebook can run as Testing-mode nodes. Upstream FRAME locators
are registered as DuckDB views before the SQL runs; downstream nodes
receive an Arrow handle via the shared-extras path used by
:mod:`aqp.lab.executors.snippet_python`.

The executor does NOT route through DuckDB's vector cache (it shares
the per-process connection used by :func:`data.duckdb_sql`'s executor
when available) so query plan stats stay in one place. Credentials
are never inlined — anything that needs an authenticated remote read
must go through ``data.iceberg_scan`` / ``data.hudi_scan`` upstream
and pass an in-memory frame down.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:  # noqa: D401
    params = dict(getattr(node, "params", {}) or {})
    snippet_id = params.get("snippet_id")
    sql = params.get("sql") or params.get("source")
    if not sql and snippet_id:
        sql = _load_snippet_sql(str(snippet_id))
    if not sql:
        return NodeResult(
            status="error",
            error="snippet.sql requires either params.sql / params.source or params.snippet_id",
            log_label="snippet.sql:missing_source",
        )

    started = time.perf_counter()
    try:
        import duckdb  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"duckdb not installed: {exc}",
            log_label="snippet.sql:no_duckdb",
        )

    con = duckdb.connect()
    registered: list[str] = []
    # Register upstream frames as views so the SQL can reference them by
    # input port name (e.g. ``SELECT * FROM in WHERE ...``).
    upstream = dict(ctx.upstream or {})
    for port_name, value in upstream.items():
        primary = _resolve_primary(value, ctx)
        if primary is None:
            continue
        try:
            con.register(port_name, primary)
            registered.append(port_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "snippet.sql register %s failed: %s", port_name, exc, exc_info=True
            )

    try:
        arrow_table = con.execute(str(sql)).fetch_arrow_table()
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"sql exec failed: {exc}",
            log_label="snippet.sql:exec_fail",
        )
    finally:
        for name in registered:
            try:
                con.unregister(name)
            except Exception:  # noqa: BLE001
                pass

    duration_ms = (time.perf_counter() - started) * 1000.0
    n_rows = int(arrow_table.num_rows)
    # Stash the Arrow table on shared extras so downstream Frame nodes
    # can pick it up via the inline canvas extras passthrough.
    ctx.extras.setdefault("snippet_outputs", {})[ctx.node_id] = arrow_table
    return NodeResult(
        status="done",
        output_locator={
            "kind": "snippet_inline",
            "tier": "tier1",
            "snippet_id": snippet_id,
            "primary_in_extras": True,
            "rows": n_rows,
            "columns": list(arrow_table.column_names)[:64],
        },
        metrics={
            "duration_ms": float(round(duration_ms, 3)),
            "rows": n_rows,
            "tier": "tier1",
        },
        log_label="snippet.sql:tier1:done",
    )


def _resolve_primary(value: Any, ctx: NodeContext) -> Any:
    """Resolve an upstream locator into a DuckDB-registerable object.

    The inline canvas wires extras across executor calls; when the
    upstream wrote a primary output (Arrow table / pandas DataFrame),
    we look it up by node_id. Otherwise we fall back to whatever the
    locator carries directly (which DuckDB may or may not register).
    """
    if isinstance(value, dict) and value.get("primary_in_extras"):
        node_id = value.get("node_id")
        if not node_id:
            return None
        outputs = ctx.extras.get("snippet_outputs") if ctx.extras else None
        if isinstance(outputs, dict):
            return outputs.get(node_id)
    return value


def _load_snippet_sql(snippet_id: str) -> str | None:
    try:
        from aqp.lab.snippets import describe_snippet
    except Exception:  # noqa: BLE001
        return None
    descriptor = describe_snippet(snippet_id)
    if descriptor is None:
        return None
    if descriptor.language != "sql":
        return None
    return descriptor.source


__all__ = ["execute"]
