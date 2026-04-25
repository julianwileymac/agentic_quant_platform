"""Shared helpers for FinRL-style gym environments."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.config import settings
from aqp.core.types import Symbol
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.data.feature_engineer import FeatureEngineer


def load_bars(
    symbols: list[str],
    start: str | datetime,
    end: str | datetime,
    indicators: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch bars, add indicators, return wide MultiIndex [timestamp] x features."""
    sym_objs = [Symbol.parse(s) if "." in s else Symbol(ticker=s) for s in symbols]
    provider = DuckDBHistoryProvider(Path(settings.parquet_dir))
    bars = provider.get_bars(sym_objs, pd.Timestamp(start), pd.Timestamp(end))
    if bars.empty:
        return bars
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    if indicators:
        bars = FeatureEngineer(indicators=indicators).transform(bars)
    bars = bars.dropna().sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)
    return bars


def pivot_features(
    bars: pd.DataFrame, feature_columns: list[str]
) -> dict[str, pd.DataFrame]:
    """Pivot long bars into {feature -> wide DataFrame(index=timestamp, cols=vt_symbol)}."""
    out: dict[str, pd.DataFrame] = {}
    for col in feature_columns:
        if col not in bars.columns:
            continue
        out[col] = bars.pivot(index="timestamp", columns="vt_symbol", values=col).ffill()
    return out


def default_reward(
    current_value: float,
    previous_value: float,
    turnover: float = 0.0,
    cost_pct: float = 0.001,
    drawdown: float = 0.0,
    drawdown_penalty: float = 0.1,
    scale: float = 1.0,
) -> float:
    pnl = current_value - previous_value
    cost = turnover * cost_pct
    dd = abs(min(drawdown, 0.0)) * drawdown_penalty
    return float((pnl - cost - dd) * scale)


def safe_array(values: Any, dtype=np.float32) -> np.ndarray:
    arr = np.asarray(values, dtype=dtype)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    return arr
