"""DuckDB query tool — lets agents execute analytical SQL on the Parquet lake."""
from __future__ import annotations

import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aqp.data.duckdb_engine import DuckDBHistoryProvider, get_connection

logger = logging.getLogger(__name__)

_SELECT_ONLY_PREFIXES = ("select", "with", "describe", "show", "explain", "pragma")


class DuckDBInput(BaseModel):
    sql: str = Field(..., description="A SELECT/WITH query against the `bars` view (read-only).")
    limit: int = Field(default=200, description="Cap the result set; forcibly rewritten if larger.")


class DuckDBQueryTool(BaseTool):
    name: str = "duckdb_query"
    description: str = (
        "Run an ad-hoc read-only DuckDB SQL query against the local Parquet lake. "
        "A `bars` view is pre-wired with columns: timestamp, vt_symbol, open, high, low, close, volume. "
        "Use this to check row counts, date ranges, distributions, or compute ad-hoc features."
    )
    args_schema: type[BaseModel] = DuckDBInput

    def _run(self, sql: str, limit: int = 200) -> str:  # type: ignore[override]
        cleaned = sql.strip().rstrip(";")
        lower = cleaned.lower()
        if not lower.startswith(_SELECT_ONLY_PREFIXES):
            return f"ERROR: only read queries are allowed; got {cleaned[:40]!r}"
        if "limit" not in lower:
            cleaned = f"{cleaned} LIMIT {limit}"
        conn = get_connection()
        try:
            plan = conn.execute(f"EXPLAIN {cleaned}").fetchall()
            df = conn.execute(cleaned).fetchdf()
            head = df.head(limit)
            return (
                f"Plan (first line): {plan[0][1] if plan else 'n/a'}\n"
                f"Rows returned: {len(head)} (of up to {limit})\n\n"
                f"{head.to_csv(index=False)}"
            )
        except Exception as e:
            logger.exception("DuckDB tool error")
            return f"ERROR: {e}"
        finally:
            conn.close()


class DescribeBarsTool(BaseTool):
    """Return per-symbol bar coverage (Data Scout's bread and butter)."""

    name: str = "describe_bars"
    description: str = "List every symbol in the Parquet lake with its first/last bar and row count."

    def _run(self) -> str:  # type: ignore[override]
        provider = DuckDBHistoryProvider()
        df = provider.describe_bars()
        if df.empty:
            return "No data. Run `make ingest` first."
        return df.to_csv(index=False)
