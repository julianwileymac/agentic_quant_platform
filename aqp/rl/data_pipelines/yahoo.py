"""``YahooFinanceRLDataPipeline`` — FinRL ``YahooFinanceProcessor`` parity.

Lazy-imports ``yfinance`` so the dependency stays optional.
"""
from __future__ import annotations

import logging
from typing import ClassVar

import pandas as pd

from aqp.rl.core.data import BaseDataPipeline

logger = logging.getLogger(__name__)


class YahooFinanceRLDataPipeline(BaseDataPipeline):
    """Yahoo Finance loader (FinRL ``DataProcessor(data_source="yahoofinance")`` analogue)."""

    rl_alias: ClassVar[str] = "YahooFinanceRLDataPipeline"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "yahoo"
    rl_tags: ClassVar[tuple[str, ...]] = ("yahoo", "yfinance")

    def __init__(self, *, auto_adjust: bool = True, name: str | None = None) -> None:
        super().__init__(name=name)
        self.auto_adjust = bool(auto_adjust)

    def download_data(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        time_interval: str = "1d",
    ) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "yfinance not installed. `pip install yfinance` to use YahooFinanceRLDataPipeline."
            ) from exc
        frames: list[pd.DataFrame] = []
        for tic in ticker_list:
            df = yf.download(
                tic,
                start=start,
                end=end,
                interval=time_interval,
                auto_adjust=self.auto_adjust,
                progress=False,
            )
            if df is None or df.empty:
                continue
            df = df.reset_index().rename(
                columns={
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "close",
                    "Volume": "volume",
                }
            )
            df["tic"] = tic
            frames.append(df[["date", "tic", "open", "high", "low", "close", "volume"]])
        if not frames:
            return pd.DataFrame(columns=["date", "tic", "open", "high", "low", "close", "volume"])
        return pd.concat(frames, ignore_index=True).sort_values(["date", "tic"], ignore_index=True)

    def add_risk_features(
        self,
        df: pd.DataFrame,
        *,
        use_vix: bool = False,
        use_turbulence: bool = True,
    ) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        if use_vix:
            try:
                vix = self.download_data(["^VIX"], df["date"].min(), df["date"].max(), "1d")[
                    ["date", "close"]
                ].rename(columns={"close": "vix"})
                df = df.merge(vix, on="date", how="left")
            except Exception:  # noqa: BLE001
                logger.exception("Yahoo VIX download failed; skipping")
        if use_turbulence:
            try:
                df = self._add_turbulence(df)
            except Exception:  # noqa: BLE001
                logger.exception("turbulence calculation failed; skipping")
        return df.ffill().bfill()

    @staticmethod
    def _add_turbulence(df: pd.DataFrame) -> pd.DataFrame:
        import numpy as np

        pivot = df.pivot(index="date", columns="tic", values="close").pct_change().dropna()
        if pivot.empty:
            df = df.copy()
            df["turbulence"] = 0.0
            return df
        unique_dates = list(pivot.index)
        start = min(252, len(unique_dates) - 1)
        out: list[float] = [0.0] * (start + 1)
        for i in range(start + 1, len(unique_dates)):
            current = pivot.iloc[i].values
            history = pivot.iloc[: i].values
            cov = np.cov(history.T)
            try:
                inv = np.linalg.pinv(cov)
                centered = current - history.mean(axis=0)
                value = float(centered @ inv @ centered.T)
            except Exception:  # noqa: BLE001
                value = 0.0
            out.append(max(0.0, value))
        out_dict = {date: val for date, val in zip(unique_dates, out)}
        df = df.copy()
        df["turbulence"] = df["date"].map(out_dict).fillna(0.0)
        return df


__all__ = ["YahooFinanceRLDataPipeline"]
