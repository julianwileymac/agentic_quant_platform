"""DuckDB analytical engine — the lab's scratchpad brain for Parquet lakes.

DuckDB is zero-dep, embedded, columnar, and queries Parquet/HDF5/CSV in place.
This module exposes:

- :class:`DuckDBHistoryProvider` — implements ``IHistoryProvider`` for the
  backtest engine and RL envs.
- :func:`get_connection` — returns a short-lived in-memory connection pre-wired
  to the Parquet lake (for ad-hoc agent queries).

The connection wires a ``bars`` view over the main Parquet directory; extra
roots can be merged in with ``UNION ALL`` so users who keep vendor exports
on a mounted drive can point AQP at them without copying files.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from aqp.config import settings
from aqp.core.corporate_actions import AuxiliaryStore
from aqp.core.interfaces import IHistoryProvider
from aqp.core.registry import register
from aqp.core.types import DataNormalizationMode, Symbol

logger = logging.getLogger(__name__)


def _collect_bar_patterns(
    primary: Path,
    extras: Iterable[Path | str] | None,
) -> list[str]:
    """Resolve every ``*.parquet`` glob pattern that contains bar files."""
    patterns: list[str] = []

    def _add(path: Path) -> None:
        bars = path / "bars"
        if bars.exists() and any(bars.glob("*.parquet")):
            patterns.append(str(bars / "*.parquet"))
        elif path.exists() and any(path.glob("*.parquet")):
            patterns.append(str(path / "*.parquet"))

    _add(primary)
    for extra in extras or []:
        _add(Path(extra).expanduser().resolve())
    return patterns


def get_connection(
    parquet_dir: Path | str | None = None,
    read_only: bool = True,
    extra_parquet_paths: Iterable[Path | str] | None = None,
) -> duckdb.DuckDBPyConnection:
    """Return an in-memory DuckDB connection with ``bars`` view over the Parquet lake(s).

    ``extra_parquet_paths`` are merged via ``UNION ALL`` so users can keep
    vendor exports on an external drive without copying into AQP's lake.
    """
    del read_only  # kept for API compatibility; :memory: is always writable
    path = Path(parquet_dir or settings.parquet_dir)
    extras: list[Path | str] = list(extra_parquet_paths or [])
    extras.extend(settings.local_data_roots_list)

    conn = duckdb.connect(":memory:", read_only=False)
    conn.execute("PRAGMA threads=4")

    patterns = _collect_bar_patterns(path, extras)
    if not patterns:
        logger.warning(
            "No Parquet bars found under %s (extras: %s) — run `make ingest` or `aqp data load`",
            path,
            extras,
        )
        return conn

    selects = [
        f"SELECT * FROM read_parquet('{p}', union_by_name=true)" for p in patterns
    ]
    view_sql = "\nUNION ALL\n".join(selects)
    conn.execute(f"CREATE OR REPLACE VIEW bars AS {view_sql}")
    return conn


@register("DuckDBHistoryProvider")
class DuckDBHistoryProvider(IHistoryProvider):
    """Read-only Parquet-backed history provider.

    Supports both the canonical ``bars`` view (default) and external,
    user-managed roots that may be Hive-partitioned and use non-canonical
    column names. Pass ``hive_partitioning``, ``glob_pattern``, and
    ``column_map`` to opt into the latter mode.
    """

    supports_ticks: bool = False

    def __init__(
        self,
        parquet_dir: str | Path | None = None,
        extra_parquet_paths: Iterable[Path | str] | None = None,
        auxiliary_store: AuxiliaryStore | None = None,
        *,
        hive_partitioning: bool = False,
        glob_pattern: str | None = None,
        column_map: dict[str, str] | None = None,
    ) -> None:
        self.parquet_dir = Path(parquet_dir or settings.parquet_dir)
        self.extra_parquet_paths: list[Path] = [
            Path(p).expanduser().resolve() for p in (extra_parquet_paths or [])
        ]
        self.auxiliary = auxiliary_store or AuxiliaryStore()
        self.hive_partitioning = bool(hive_partitioning)
        self.glob_pattern = glob_pattern or None
        self.column_map: dict[str, str] = {
            k: str(v) for k, v in (column_map or {}).items() if v
        }

    # ----------------------------------------------------------- helpers --

    def _root_pattern(self) -> str | None:
        """Return the glob string for the primary parquet root (custom mode)."""
        if not self.parquet_dir.exists():
            return None
        if self.glob_pattern:
            return str(self.parquet_dir / self.glob_pattern)
        # If the user-managed mode is set without an explicit pattern,
        # default to recursive ``**/*.parquet`` for hive datasets, else
        # the previous flat ``*.parquet`` glob.
        return str(self.parquet_dir / ("**/*.parquet" if self.hive_partitioning else "*.parquet"))

    def _custom_query(
        self,
        vt_symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Issue a ``read_parquet(...)`` over ``parquet_dir`` honouring column_map."""
        pattern = self._root_pattern()
        if not pattern:
            return pd.DataFrame()

        ts = self.column_map.get("timestamp", "timestamp")
        sym = self.column_map.get("vt_symbol", "vt_symbol")
        open_c = self.column_map.get("open", "open")
        high_c = self.column_map.get("high", "high")
        low_c = self.column_map.get("low", "low")
        close_c = self.column_map.get("close", "close")
        vol_c = self.column_map.get("volume", "volume")

        select_cols = [
            f'"{ts}" AS timestamp',
            f'"{sym}" AS vt_symbol',
            f'"{open_c}" AS open',
            f'"{high_c}" AS high',
            f'"{low_c}" AS low',
            f'"{close_c}" AS close',
            f'"{vol_c}" AS volume',
        ]
        opts = "union_by_name=true"
        if self.hive_partitioning:
            opts += ", hive_partitioning=true"

        placeholders = ",".join(["?"] * len(vt_symbols)) if vt_symbols else ""
        sym_clause = f' AND "{sym}" IN ({placeholders})' if placeholders else ""
        sql = (
            f"SELECT {', '.join(select_cols)} "
            f"FROM read_parquet('{pattern}', {opts}) "
            f'WHERE "{ts}" >= ? AND "{ts}" <= ?{sym_clause} '
            f'ORDER BY "{ts}", "{sym}"'
        )
        args: list[Any] = [start, end, *vt_symbols]

        conn = duckdb.connect(":memory:", read_only=False)
        try:
            return conn.execute(sql, args).fetchdf()
        finally:
            conn.close()

    # -------------------------------------------------------------- bars --

    def get_bars(
        self,
        symbols: Iterable[Symbol],
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        vt_symbols = [s.vt_symbol if isinstance(s, Symbol) else str(s) for s in symbols]
        placeholders = ",".join(["?"] * len(vt_symbols))
        if not placeholders:
            return pd.DataFrame()

        # Custom-root mode: bypass the ``bars`` view and read the parquet
        # tree directly so hive-partitioned datasets work as data sources.
        if self.hive_partitioning or self.glob_pattern or self.column_map:
            df = self._custom_query(vt_symbols, start, end)
            if df.empty:
                logger.warning(
                    "DuckDB (custom root %s) returned no rows for %s between %s and %s",
                    self.parquet_dir,
                    vt_symbols,
                    start,
                    end,
                )
            return df

        conn = get_connection(self.parquet_dir, extra_parquet_paths=self.extra_parquet_paths)
        try:
            query = f"""
                SELECT timestamp, vt_symbol, open, high, low, close, volume
                FROM bars
                WHERE vt_symbol IN ({placeholders})
                  AND timestamp >= ?
                  AND timestamp <= ?
                ORDER BY timestamp, vt_symbol
            """
            df = conn.execute(
                query, [*vt_symbols, start, end]
            ).fetchdf()
        finally:
            conn.close()
        if df.empty:
            logger.warning("DuckDB returned no rows for %s between %s and %s", vt_symbols, start, end)
        return df

    def run_query(self, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
        """Ad-hoc SQL passthrough used by the :class:`DuckDBQueryTool`."""
        conn = get_connection(self.parquet_dir, extra_parquet_paths=self.extra_parquet_paths)
        try:
            return conn.execute(sql, params or []).fetchdf()
        finally:
            conn.close()

    def describe_bars(self) -> pd.DataFrame:
        """Return a summary of the Parquet lake — used by the Data Scout."""
        conn = get_connection(self.parquet_dir, extra_parquet_paths=self.extra_parquet_paths)
        try:
            return conn.execute(
                """
                SELECT vt_symbol,
                       MIN(timestamp) AS first_bar,
                       MAX(timestamp) AS last_bar,
                       COUNT(*)       AS n_bars
                FROM bars
                GROUP BY vt_symbol
                ORDER BY vt_symbol
                """
            ).fetchdf()
        except duckdb.Error:
            return pd.DataFrame()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Extended surface: normalization + higher-resolution data
    # ------------------------------------------------------------------

    def get_bars_normalized(
        self,
        symbols: Iterable[Symbol],
        start: datetime,
        end: datetime,
        interval: str = "1d",
        normalization: DataNormalizationMode | str = DataNormalizationMode.ADJUSTED,
    ) -> pd.DataFrame:
        """``get_bars`` + per-symbol corporate-action adjustment.

        ``normalization=RAW`` returns the bars unchanged. Otherwise, each
        symbol's ``FactorFile`` (if present under ``data/auxiliary``) is
        applied to scale OHLC / volume.
        """
        mode = (
            normalization.value
            if isinstance(normalization, DataNormalizationMode)
            else str(normalization)
        )
        df = self.get_bars(symbols, start, end, interval=interval)
        if df.empty or mode == "raw":
            return df
        adjusted: list[pd.DataFrame] = []
        for vt_symbol, sub in df.groupby("vt_symbol", sort=False):
            adjusted.append(self.auxiliary.apply_adjustments(sub, vt_symbol, mode=mode))
        return pd.concat(adjusted, ignore_index=True)

    def get_quotes(
        self,
        symbols: Iterable[Symbol],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Quote-bar query (``bid_*`` / ``ask_*`` columns).

        Uses the ``quotes`` view when present under ``data/parquet/quotes``.
        Returns an empty frame if no quote data is available.
        """
        vt_symbols = [s.vt_symbol if isinstance(s, Symbol) else str(s) for s in symbols]
        if not vt_symbols:
            return pd.DataFrame()
        conn = duckdb.connect(":memory:", read_only=False)
        pattern = str(self.parquet_dir / "quotes" / "*.parquet")
        quotes_dir = self.parquet_dir / "quotes"
        if not (quotes_dir.exists() and any(quotes_dir.glob("*.parquet"))):
            conn.close()
            return pd.DataFrame()
        try:
            conn.execute(
                f"CREATE OR REPLACE VIEW quotes AS SELECT * FROM read_parquet('{pattern}', union_by_name=true)"
            )
            placeholders = ",".join(["?"] * len(vt_symbols))
            return conn.execute(
                f"""
                SELECT timestamp, vt_symbol, bid_open, bid_high, bid_low, bid_close,
                       ask_open, ask_high, ask_low, ask_close, bid_size, ask_size
                FROM quotes
                WHERE vt_symbol IN ({placeholders})
                  AND timestamp >= ?
                  AND timestamp <= ?
                ORDER BY timestamp, vt_symbol
                """,
                [*vt_symbols, start, end],
            ).fetchdf()
        finally:
            conn.close()

    def get_ticks(
        self,
        symbols: Iterable[Symbol],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Tick-level query (``ticks`` parquet directory)."""
        vt_symbols = [s.vt_symbol if isinstance(s, Symbol) else str(s) for s in symbols]
        if not vt_symbols:
            return pd.DataFrame()
        conn = duckdb.connect(":memory:", read_only=False)
        pattern = str(self.parquet_dir / "ticks" / "*.parquet")
        ticks_dir = self.parquet_dir / "ticks"
        if not (ticks_dir.exists() and any(ticks_dir.glob("*.parquet"))):
            conn.close()
            return pd.DataFrame()
        try:
            conn.execute(
                f"CREATE OR REPLACE VIEW ticks AS SELECT * FROM read_parquet('{pattern}', union_by_name=true)"
            )
            placeholders = ",".join(["?"] * len(vt_symbols))
            return conn.execute(
                f"""
                SELECT timestamp, vt_symbol, bid, ask, last, volume, bid_size, ask_size
                FROM ticks
                WHERE vt_symbol IN ({placeholders})
                  AND timestamp >= ?
                  AND timestamp <= ?
                ORDER BY timestamp, vt_symbol
                """,
                [*vt_symbols, start, end],
            ).fetchdf()
        finally:
            conn.close()

    def gap_report(self, vt_symbol: str, start: datetime, end: datetime, interval: str = "1d") -> dict[str, Any]:
        """Detects missing bar days for data-quality dashboards."""
        placeholders = "?"
        conn = get_connection(self.parquet_dir, extra_parquet_paths=self.extra_parquet_paths)
        try:
            df = conn.execute(
                f"""
                SELECT timestamp, close FROM bars WHERE vt_symbol = {placeholders}
                  AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp
                """,
                [vt_symbol, start, end],
            ).fetchdf()
        finally:
            conn.close()
        if df.empty:
            return {"vt_symbol": vt_symbol, "bar_count": 0, "gaps": []}
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        expected = pd.bdate_range(df["timestamp"].min(), df["timestamp"].max())
        present = set(df["timestamp"].dt.normalize())
        gaps = [str(d.date()) for d in expected if d.normalize() not in present]
        return {
            "vt_symbol": vt_symbol,
            "bar_count": int(len(df)),
            "first_bar": str(df["timestamp"].min()),
            "last_bar": str(df["timestamp"].max()),
            "gaps": gaps[:200],  # cap for payload sanity
        }
