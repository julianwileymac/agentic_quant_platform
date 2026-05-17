"""API-based fetchers (REST adapters)."""
from __future__ import annotations

from aqp.data.fetchers.api.akshare_ohlcv import AkshareOHLCVFetcher
from aqp.data.fetchers.api.akshare_proxy import AkshareProxyFetcher
from aqp.data.fetchers.api.alpha_vantage import AlphaVantageFetcher
from aqp.data.fetchers.api.cfpb import CfpbComplaintsFetcher
from aqp.data.fetchers.api.coingecko import CoingeckoFetcher
from aqp.data.fetchers.api.fda import FdaFetcher
from aqp.data.fetchers.api.finance_database import FinanceDatabaseFetcher
from aqp.data.fetchers.api.fred import FredObservationsFetcher
from aqp.data.fetchers.api.gdelt import GdeltFetcher
from aqp.data.fetchers.api.polygon import PolygonFetcher
from aqp.data.fetchers.api.quandl import QuandlFetcher
from aqp.data.fetchers.api.rest_api import RestApiFetcher
from aqp.data.fetchers.api.sec import SecFilingsFetcher
from aqp.data.fetchers.api.tiingo import TiingoFetcher
from aqp.data.fetchers.api.uspto import UsptoFetcher
from aqp.data.fetchers.api.yfinance import YFinanceFetcher

__all__ = [
    "AkshareOHLCVFetcher",
    "AkshareProxyFetcher",
    "AlphaVantageFetcher",
    "CfpbComplaintsFetcher",
    "CoingeckoFetcher",
    "FdaFetcher",
    "FinanceDatabaseFetcher",
    "FredObservationsFetcher",
    "GdeltFetcher",
    "PolygonFetcher",
    "QuandlFetcher",
    "RestApiFetcher",
    "SecFilingsFetcher",
    "TiingoFetcher",
    "UsptoFetcher",
    "YFinanceFetcher",
]
