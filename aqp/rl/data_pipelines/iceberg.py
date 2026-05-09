"""Default RL data pipeline — reads bars from the AQP Iceberg catalog.

Uses :class:`aqp.data.duckdb_engine.DuckDBHistoryProvider` for the
local-first path (parquet under ``settings.parquet_dir``) and
:class:`aqp.data.feature_engineer.FeatureEngineer` for indicators.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import pandas as pd

from aqp.config import settings
from aqp.rl.core.data import BaseDataPipeline

logger = logging.getLogger(__name__)


class IcebergRLDataPipeline(BaseDataPipeline):
    """Iceberg / parquet-backed FinRL ``DataProcessor`` analogue.

    Mirrors FinRL's three-stage download → indicators → array path but
    sources bars from the AQP data plane:

    1. :class:`DuckDBHistoryProvider` (parquet snapshots).
    2. :class:`FeatureEngineer` for indicators / turbulence.
    3. :meth:`df_to_array` (inherited) for the FinRL fast path.
    """

    rl_alias: ClassVar[str] = "IcebergRLDataPipeline"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "iceberg"
    rl_tags: ClassVar[tuple[str, ...]] = ("default", "iceberg", "duckdb")

    def __init__(
        self,
        *,
        indicators: list[str] | None = None,
        use_vix: bool = False,
        use_turbulence: bool = True,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.indicators = list(indicators or [])
        self.use_vix = bool(use_vix)
        self.use_turbulence = bool(use_turbulence)

    def download_data(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        time_interval: str = "1D",
    ) -> pd.DataFrame:
        from pathlib import Path

        from aqp.core.types import Symbol
        from aqp.data.duckdb_engine import DuckDBHistoryProvider

        sym_objs = [Symbol.parse(s) if "." in s else Symbol(ticker=s) for s in ticker_list]
        provider = DuckDBHistoryProvider(Path(settings.parquet_dir))
        bars = provider.get_bars(sym_objs, pd.Timestamp(start), pd.Timestamp(end))
        if bars is None or bars.empty:
            return pd.DataFrame(columns=["date", "tic", "open", "high", "low", "close", "volume"])
        bars = bars.copy()
        bars["timestamp"] = pd.to_datetime(bars["timestamp"])
        # FinRL convention: long format with "date" + "tic" columns.
        bars = bars.rename(columns={"timestamp": "date", "vt_symbol": "tic"})
        return bars.sort_values(["date", "tic"]).reset_index(drop=True)

    def add_risk_features(
        self,
        df: pd.DataFrame,
        *,
        use_vix: bool = False,
        use_turbulence: bool = True,
    ) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        try:
            from aqp.data.feature_engineer import FeatureEngineer
        except Exception:  # pragma: no cover
            return df
        wanted: list[str] = list(self.indicators)
        if use_turbulence and "turbulence" not in wanted:
            wanted.append("turbulence")
        if use_vix and "vix" not in wanted:
            wanted.append("vix")
        bars = df.rename(columns={"date": "timestamp", "tic": "vt_symbol"})
        out = FeatureEngineer(indicators=wanted).transform(bars)
        return out.rename(columns={"timestamp": "date", "vt_symbol": "tic"})


__all__ = ["IcebergRLDataPipeline"]
