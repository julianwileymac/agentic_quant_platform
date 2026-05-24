"""Data pipeline contract — FinRL ``DataProcessor`` parity, AQP-native.

A :class:`BaseDataPipeline` covers the canonical FinRL ingestion path:

1. :meth:`download_data(ticker_list, start, end, time_interval)` —
   pull raw bars from a vendor (Iceberg, Yahoo, Alpaca, WRDS, Kafka).
2. :meth:`clean_data(df)` — forward-fill, drop NaNs, harmonise schema.
3. :meth:`add_indicators(df, tech_indicator_list)` — stockstats + custom
   features (FinRL's ``add_technical_indicator``).
4. :meth:`add_risk_features(df, *, use_vix, use_turbulence)` — VIX merge
   + Mahalanobis turbulence (FinRL's ``add_vix`` / ``add_turbulence``).
5. :meth:`df_to_array(df, tech_indicator_list, *, if_vix)` — produce the
   ``(price_array, tech_array, risk_array)`` numpy bundle consumed by
   the array-backed envs (FinRL ``env_stocktrading_np`` / ``env_multiple_crypto``).
6. :meth:`time_split(df, start, end)` — FinRL's ``data_split`` walk-forward
   helper.

Returning a long-format pandas dataframe with columns ``date``, ``tic``,
``open / high / low / close / volume`` (+ indicators + risk) is the
canonical contract — every concrete pipeline downstream can dispatch on
it.
"""
from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from aqp_rl.core.base import RL_KIND_DATA, RLComponent


@dataclass
class DataPipelineResult:
    """Canonical bundle returned by :meth:`BaseDataPipeline.run_full`.

    ``df`` is the long-format pandas frame (FinRL convention); the three
    arrays are the numpy bundle the FinRL ``env_stocktrading_np`` /
    ``env_multiple_crypto`` envs consume directly.
    """

    df: pd.DataFrame
    price_array: np.ndarray
    tech_array: np.ndarray
    risk_array: np.ndarray
    tickers: list[str]
    indicators: list[str]
    use_vix: bool = False
    use_turbulence: bool = False


class BaseDataPipeline(RLComponent):
    """Abstract data pipeline. Concrete classes ship in :mod:`aqp_rl.data_pipelines`."""

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_DATA

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------ stages

    @abstractmethod
    def download_data(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        time_interval: str = "1D",
    ) -> pd.DataFrame:  # pragma: no cover - abstract
        """Return long-format ``date / tic / open / high / low / close / volume`` frame."""

    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sort + forward-fill + drop NaNs. Default ports FinRL's clean step."""
        if df is None or df.empty:
            return df
        df = df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["date", "tic"]).reset_index(drop=True)
        df = df.ffill().bfill().dropna()
        return df

    def add_indicators(
        self,
        df: pd.DataFrame,
        tech_indicator_list: list[str] | None,
    ) -> pd.DataFrame:
        """Default: delegate to :class:`aqp.data.feature_engineer.FeatureEngineer`.

        Concrete pipelines may override to use stockstats directly (FinRL
        parity) or any other library.
        """
        if not tech_indicator_list:
            return df
        try:
            from aqp.data.feature_engineer import FeatureEngineer
        except Exception:  # pragma: no cover
            return df
        bars = df.rename(columns={"date": "timestamp", "tic": "vt_symbol"})
        out = FeatureEngineer(indicators=tech_indicator_list).transform(bars)
        return out.rename(columns={"timestamp": "date", "vt_symbol": "tic"})

    def add_risk_features(
        self,
        df: pd.DataFrame,
        *,
        use_vix: bool = False,
        use_turbulence: bool = True,
    ) -> pd.DataFrame:
        """Default no-op; concrete pipelines (Yahoo / Iceberg) override."""
        return df

    def df_to_array(
        self,
        df: pd.DataFrame,
        tech_indicator_list: list[str],
        *,
        if_vix: bool = False,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """FinRL fast path: ``df`` → ``(price_array, tech_array, risk_array)``.

        Default implementation (mirrors FinRL's
        ``YahooFinanceProcessor.df_to_array``):

        - ``price_array``: per-tic close column-stacked (shape ``[T, n_tic]``).
        - ``tech_array``: per-tic indicator block column-stacked
          (shape ``[T, n_tic * len(indicators)]``).
        - ``risk_array``: VIX series (if ``if_vix``) else turbulence
          (shape ``[T]`` or ``[T, 1]``).
        """
        if df is None or df.empty:
            empty = np.zeros((0,), dtype=np.float32)
            return empty, empty, empty
        unique_ticker = list(df["tic"].unique())
        first = True
        price_array = np.zeros(0)
        tech_array = np.zeros(0)
        risk_array = np.zeros(0)
        for tic in unique_ticker:
            sub = df[df["tic"] == tic]
            close = sub[["close"]].values
            tech = sub[tech_indicator_list].values if tech_indicator_list else np.zeros((len(sub), 0))
            if first:
                price_array = close
                tech_array = tech
                if if_vix and "vix" in df.columns:
                    risk_array = sub["vix"].values
                elif "turbulence" in df.columns:
                    risk_array = sub["turbulence"].values
                else:
                    risk_array = np.zeros(len(sub), dtype=np.float32)
                first = False
            else:
                price_array = np.hstack([price_array, close])
                tech_array = np.hstack([tech_array, tech])
        return (
            price_array.astype(np.float32, copy=False),
            tech_array.astype(np.float32, copy=False),
            np.asarray(risk_array, dtype=np.float32),
        )

    @staticmethod
    def time_split(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        """FinRL's ``data_split`` — slice ``df`` by ISO date strings (inclusive lower, exclusive upper)."""
        if df is None or df.empty:
            return df
        d = pd.to_datetime(df["date"]) if "date" in df.columns else pd.to_datetime(df.index)
        mask = (d >= pd.Timestamp(start)) & (d < pd.Timestamp(end))
        out = df.loc[mask].copy()
        if "date" in out.columns:
            out = out.sort_values(["date", "tic"], ignore_index=True)
            out.index = out["date"].factorize()[0]
        return out

    # ------------------------------------------------------------------ orchestration

    def run_full(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        *,
        tech_indicator_list: list[str] | None = None,
        time_interval: str = "1D",
        use_vix: bool = False,
        use_turbulence: bool = True,
    ) -> DataPipelineResult:
        """One-call FinRL-style pipeline: download → clean → indicators → risk → array."""
        df = self.download_data(ticker_list, start, end, time_interval)
        df = self.clean_data(df)
        df = self.add_indicators(df, tech_indicator_list or [])
        df = self.add_risk_features(df, use_vix=use_vix, use_turbulence=use_turbulence)
        price_array, tech_array, risk_array = self.df_to_array(
            df, tech_indicator_list or [], if_vix=use_vix
        )
        return DataPipelineResult(
            df=df,
            price_array=price_array,
            tech_array=tech_array,
            risk_array=risk_array,
            tickers=list(ticker_list),
            indicators=list(tech_indicator_list or []),
            use_vix=use_vix,
            use_turbulence=use_turbulence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "name": self.name}


__all__ = [
    "BaseDataPipeline",
    "DataPipelineResult",
]
