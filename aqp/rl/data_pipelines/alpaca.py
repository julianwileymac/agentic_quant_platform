"""``AlpacaRLDataPipeline`` — FinRL ``AlpacaProcessor`` + paper-trading bridge.

Reuses the existing AQP Alpaca integration in :mod:`aqp.streaming` /
:mod:`aqp.providers` so credentials are managed in one place.
"""
from __future__ import annotations

import logging
from typing import ClassVar

import pandas as pd

from aqp.config import settings
from aqp.rl.core.data import BaseDataPipeline

logger = logging.getLogger(__name__)


class AlpacaRLDataPipeline(BaseDataPipeline):
    """Alpaca-backed bar loader. Falls back to Yahoo if Alpaca credentials missing."""

    rl_alias: ClassVar[str] = "AlpacaRLDataPipeline"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "alpaca"
    rl_tags: ClassVar[tuple[str, ...]] = ("alpaca", "paper-trading")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        feed: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.api_key = api_key or getattr(settings, "alpaca_api_key", "") or ""
        self.secret_key = secret_key or getattr(settings, "alpaca_secret_key", "") or ""
        self.base_url = base_url or getattr(settings, "alpaca_base_url", "") or ""
        self.feed = feed or getattr(settings, "alpaca_feed", "iex") or "iex"

    def download_data(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        time_interval: str = "1Day",
    ) -> pd.DataFrame:
        if not self.api_key or not self.secret_key:
            logger.info("alpaca credentials missing — falling back to YahooFinanceRLDataPipeline")
            from aqp.rl.data_pipelines.yahoo import YahooFinanceRLDataPipeline

            return YahooFinanceRLDataPipeline().download_data(
                ticker_list,
                start,
                end,
                time_interval="1d" if time_interval.lower().startswith("1d") else time_interval,
            )
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "alpaca-py not installed. `pip install alpaca-py` for AlpacaRLDataPipeline."
            ) from exc
        client = StockHistoricalDataClient(self.api_key, self.secret_key)
        # Map common interval strings to TimeFrame.
        timeframe_map = {
            "1Day": TimeFrame.Day,
            "1d": TimeFrame.Day,
            "1Hour": TimeFrame.Hour,
            "1h": TimeFrame.Hour,
            "1Min": TimeFrame.Minute,
            "1m": TimeFrame.Minute,
        }
        tf = timeframe_map.get(time_interval, TimeFrame.Day)
        request = StockBarsRequest(
            symbol_or_symbols=list(ticker_list),
            timeframe=tf,
            start=pd.Timestamp(start).to_pydatetime(),
            end=pd.Timestamp(end).to_pydatetime(),
            feed=self.feed,
        )
        try:
            bars = client.get_stock_bars(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception("alpaca bar fetch failed; falling back to Yahoo")
            from aqp.rl.data_pipelines.yahoo import YahooFinanceRLDataPipeline

            return YahooFinanceRLDataPipeline().download_data(ticker_list, start, end, "1d")
        df = bars.df.reset_index()
        df = df.rename(
            columns={
                "symbol": "tic",
                "timestamp": "date",
            }
        )[["date", "tic", "open", "high", "low", "close", "volume"]]
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df.sort_values(["date", "tic"], ignore_index=True)


__all__ = ["AlpacaRLDataPipeline"]
