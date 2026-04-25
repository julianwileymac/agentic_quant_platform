"""Feature loaders — how a ``DataHandler`` pulls raw data from storage.

``AQPDataLoader`` is the native workhorse: it takes a dict of
``{field_name: "expression"}`` plus a dict of label expressions, evaluates
them via :mod:`aqp.data.expressions` against DuckDB-backed bars, and
returns a flat long-format DataFrame.

Reference: ``inspiration/qlib-main/qlib/data/dataset/loader.py``.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract contract.
# ---------------------------------------------------------------------------


class DataLoader(ABC):
    """Abstract data loader — all concrete loaders implement ``load``."""

    @abstractmethod
    def load(
        self,
        instruments: list[str] | None,
        start_time: pd.Timestamp | str | None = None,
        end_time: pd.Timestamp | str | None = None,
    ) -> pd.DataFrame:
        """Return a long-format frame with columns ``timestamp``, ``vt_symbol``,
        plus one column per feature/label expression."""


class DLWParser(DataLoader, ABC):
    """Feature-expression loader intermediate — mirrors qlib's ``DLWParser``."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        swap_level: bool = True,
        freq: str = "day",
    ) -> None:
        self.config = dict(config or {})
        self.swap_level = bool(swap_level)
        self.freq = freq

    @abstractmethod
    def load_group_df(
        self,
        instruments: list[str] | None,
        exprs: list[str],
        names: list[str],
        start_time: pd.Timestamp | None,
        end_time: pd.Timestamp | None,
        gp_name: str,
    ) -> pd.DataFrame:
        """Evaluate the expressions and return a long-format DataFrame with
        ``timestamp, vt_symbol, <name1>, <name2>, ...``."""

    def load(
        self,
        instruments: list[str] | None,
        start_time: pd.Timestamp | str | None = None,
        end_time: pd.Timestamp | str | None = None,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for group_name, group_cfg in self.config.items():
            exprs, names = _unpack_group_cfg(group_cfg)
            if not exprs:
                continue
            df = self.load_group_df(
                instruments=instruments,
                exprs=exprs,
                names=names,
                start_time=pd.Timestamp(start_time) if start_time else None,
                end_time=pd.Timestamp(end_time) if end_time else None,
                gp_name=group_name,
            )
            if not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        merged = frames[0]
        for f in frames[1:]:
            merged = merged.merge(f, on=["timestamp", "vt_symbol"], how="outer")
        return merged.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)


def _unpack_group_cfg(cfg: Any) -> tuple[list[str], list[str]]:
    """Accept multiple styles: ``{'Close': '$close'}`` or ``['$close','$open']``
    or ``(['$close'], ['close_px'])``."""
    if isinstance(cfg, dict):
        return list(cfg.values()), list(cfg.keys())
    if isinstance(cfg, (list, tuple)) and len(cfg) == 2 and all(
        isinstance(x, (list, tuple)) for x in cfg
    ):
        return list(cfg[0]), list(cfg[1])
    if isinstance(cfg, (list, tuple)):
        exprs = [str(x) for x in cfg]
        return exprs, exprs
    raise ValueError(f"Unsupported group config: {type(cfg).__name__}")


# ---------------------------------------------------------------------------
# AQPDataLoader — evaluates our expression DSL over DuckDB bars.
# ---------------------------------------------------------------------------


class AQPDataLoader(DLWParser):
    """Native data loader backed by :class:`aqp.data.duckdb_engine.DuckDBHistoryProvider`.

    YAML example::

        data_loader:
          class: AQPDataLoader
          module_path: aqp.ml.loader
          kwargs:
            config:
              feature:
                CLOSE:  "$close"
                OPEN:   "$open"
                ROC5:   "$close / Ref($close, 5) - 1"
              label:
                LABEL0: "Ref($close, -2) / Ref($close, -1) - 1"
    """

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        interval: str = "1d",
        swap_level: bool = True,
        history_provider: Any | None = None,
    ) -> None:
        super().__init__(config=config, swap_level=swap_level, freq=interval)
        self.interval = interval
        self._history_provider = history_provider

    def _provider(self):
        if self._history_provider is None:
            from aqp.data.duckdb_engine import DuckDBHistoryProvider

            self._history_provider = DuckDBHistoryProvider()
        return self._history_provider

    def _load_bars(
        self,
        instruments: list[str] | None,
        start_time: pd.Timestamp | None,
        end_time: pd.Timestamp | None,
    ) -> pd.DataFrame:
        from aqp.core.types import Symbol

        provider = self._provider()
        if instruments:
            symbols = [Symbol.parse(s) if "." in s else Symbol(ticker=s) for s in instruments]
        else:
            symbols = []
        return provider.get_bars(
            symbols,
            start=start_time or pd.Timestamp("2000-01-01"),
            end=end_time or pd.Timestamp("2100-01-01"),
            interval=self.interval,
        )

    def load_group_df(
        self,
        instruments: list[str] | None,
        exprs: list[str],
        names: list[str],
        start_time: pd.Timestamp | None,
        end_time: pd.Timestamp | None,
        gp_name: str,
    ) -> pd.DataFrame:
        from aqp.data.expressions import Expression

        bars = self._load_bars(instruments, start_time, end_time)
        if bars.empty:
            return pd.DataFrame(columns=["timestamp", "vt_symbol", *names])
        bars = bars.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)
        outs: dict[str, list[float]] = {n: [] for n in names}
        idx_ts: list[pd.Timestamp] = []
        idx_sym: list[str] = []

        # Group once, then evaluate each expression per group so we avoid
        # re-grouping for every feature.
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            sub = sub.reset_index(drop=True)
            per_name: dict[str, pd.Series] = {}
            for expr_str, name in zip(exprs, names, strict=False):
                try:
                    expr = Expression(expr_str)
                    vals = expr.evaluate(sub)
                except Exception:
                    logger.exception("expression %s failed on %s", expr_str, vt_symbol)
                    vals = pd.Series([float("nan")] * len(sub))
                if isinstance(vals, (int, float)):
                    vals = pd.Series([vals] * len(sub))
                per_name[name] = vals.reset_index(drop=True)
            # Stitch rows together.
            for i in range(len(sub)):
                idx_ts.append(sub["timestamp"].iloc[i])
                idx_sym.append(vt_symbol)
                for n in names:
                    outs[n].append(float(per_name[n].iloc[i]) if pd.notna(per_name[n].iloc[i]) else float("nan"))

        df = pd.DataFrame({"timestamp": idx_ts, "vt_symbol": idx_sym, **outs})
        # Promote column names with group prefix (feature/label) by column-level namespacing
        # downstream; loader stays flat here.
        df.attrs["group"] = gp_name
        return df


class StaticDataLoader(DataLoader):
    """DataLoader that simply returns a pre-computed long DataFrame — for
    testing, manual pipelines, or wrapping an Alpha158 feature panel built
    somewhere else."""

    def __init__(self, data: pd.DataFrame | str) -> None:
        if isinstance(data, str):
            self._data = pd.read_parquet(data) if data.endswith(".parquet") else pd.read_csv(data)
        else:
            self._data = data.copy()

    def load(
        self,
        instruments: list[str] | None = None,
        start_time: pd.Timestamp | str | None = None,
        end_time: pd.Timestamp | str | None = None,
    ) -> pd.DataFrame:
        df = self._data
        if "timestamp" in df.columns and start_time is not None:
            df = df[pd.to_datetime(df["timestamp"]) >= pd.Timestamp(start_time)]
        if "timestamp" in df.columns and end_time is not None:
            df = df[pd.to_datetime(df["timestamp"]) <= pd.Timestamp(end_time)]
        if instruments and "vt_symbol" in df.columns:
            df = df[df["vt_symbol"].isin(set(instruments))]
        return df.reset_index(drop=True)


__all__ = ["DLWParser", "DataLoader", "AQPDataLoader", "StaticDataLoader"]
