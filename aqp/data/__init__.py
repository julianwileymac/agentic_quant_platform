"""Data tier: DuckDB analytics + Parquet lake + ChromaDB vectors + optional ArcticDB."""

from aqp.data.arctic_store import ArcticStore
from aqp.data.chroma_store import ChromaStore
from aqp.data.cv import MultipleTimeSeriesCV, PurgedKFold, TimeSeriesWalkForward
from aqp.data.duckdb_engine import DuckDBHistoryProvider, get_connection
from aqp.data.expressions import Expression, compute
from aqp.data.factors import (
    FactorReport,
    align_factor_and_returns,
    compute_forward_returns,
    cumulative_quantile_returns,
    evaluate_factor,
    factor_information_coefficient,
    ic_summary,
    mean_returns_by_quantile,
    plot_ic_decay,
    plot_quantile_returns,
    plot_turnover,
    quantile_spread,
    turnover_top_quantile,
)
from aqp.data.feature_engineer import FeatureEngineer
from aqp.data.indicators_zoo import IndicatorSpec, IndicatorZoo
from aqp.data.ingestion import (
    AlpacaSource,
    AlphaVantageSource,
    BaseDataSource,
    CCXTSource,
    IBKRHistoricalSource,
    LocalCSVSource,
    LocalDirectoryLoader,
    LocalParquetSource,
    PolygonSource,
    YahooFinanceSource,
    dataset_hash,
    ingest,
    write_parquet,
)
from aqp.data.subscription import SubscriptionManager, subscriptions_from_symbols

__all__ = [
    # Sources
    "AlphaVantageSource",
    "AlpacaSource",
    "BaseDataSource",
    "CCXTSource",
    "IBKRHistoricalSource",
    "LocalCSVSource",
    "LocalDirectoryLoader",
    "LocalParquetSource",
    "PolygonSource",
    "YahooFinanceSource",
    # Stores / providers
    "ArcticStore",
    "ChromaStore",
    "DuckDBHistoryProvider",
    "get_connection",
    # Subscription routing
    "SubscriptionManager",
    "subscriptions_from_symbols",
    # Feature engineering
    "Expression",
    "FeatureEngineer",
    "IndicatorSpec",
    "IndicatorZoo",
    "compute",
    # Factors (Alphalens-style)
    "FactorReport",
    "align_factor_and_returns",
    "compute_forward_returns",
    "cumulative_quantile_returns",
    "evaluate_factor",
    "factor_information_coefficient",
    "ic_summary",
    "mean_returns_by_quantile",
    "plot_ic_decay",
    "plot_quantile_returns",
    "plot_turnover",
    "quantile_spread",
    "turnover_top_quantile",
    # Cross-validation
    "MultipleTimeSeriesCV",
    "PurgedKFold",
    "TimeSeriesWalkForward",
    # Ingest helpers
    "dataset_hash",
    "ingest",
    "write_parquet",
]
