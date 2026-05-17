"""Curated dataset presets for the inspiration rehydration.

Each :class:`DatasetPreset` is a declarative spec the UI's
``/data/datasets/library`` page enumerates and lets the user trigger
one-click ingestion via the Celery tasks in
:mod:`aqp.tasks.dataset_preset_tasks`.

Adding a preset is just appending to :data:`PRESETS`.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetPreset:
    name: str
    description: str
    namespace: str
    table: str
    source_kind: str  # e.g. "akshare", "yfinance", "kucoin", "fred", "scraper", "local_gz"
    ingestion_task: str  # e.g. "aqp.tasks.dataset_preset_tasks.ingest_etf_intraday_panel"
    requires_api_key: bool = False
    api_key_env_var: str | None = None
    default_symbols: list[str] = field(default_factory=list)
    interval: str = "1d"
    schedule_cron: str | None = None
    documentation_url: str | None = None
    tags: list[str] = field(default_factory=list)
    version: int = 1
    setup_steps: list[dict[str, Any]] = field(default_factory=list)
    required_config: dict[str, Any] = field(default_factory=dict)
    supported_sinks: list[str] = field(default_factory=lambda: ["sink.iceberg", "sink.parquet", "sink.profile"])
    default_pipeline_manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def iceberg_identifier(self) -> str:
        return f"{self.namespace}.{self.table}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["iceberg_identifier"] = self.iceberg_identifier
        d["setup_steps"] = self.setup_steps or _default_setup_steps(self)
        d["required_config"] = self.required_config or _default_required_config(self)
        d["default_pipeline_manifest"] = self.default_pipeline_manifest or _default_manifest_hint(self)
        return d


PRESETS: dict[str, DatasetPreset] = {
    "intraday_momentum_etf": DatasetPreset(
        name="intraday_momentum_etf",
        description="Gao 2018 ETF intraday momentum panel — 30-minute bars on SPY/QQQ/IWM/DIA/EFA/EEM/TLT/GLD/USO.",
        namespace="aqp_etf",
        table="intraday_30min",
        source_kind="yfinance",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_etf_intraday_panel",
        requires_api_key=False,
        default_symbols=["SPY.NASDAQ", "QQQ.NASDAQ", "IWM.NASDAQ", "DIA.NASDAQ", "EFA.NASDAQ", "EEM.NASDAQ", "TLT.NASDAQ", "GLD.NASDAQ", "USO.NASDAQ"],
        interval="30m",
        documentation_url="https://www.aqr.com/Insights/Research/Working-Paper/A-Half-Hour-Daily-Stock-Market-Anomaly",
        tags=["etf", "intraday", "momentum"],
    ),
    "commodity_futures_panel": DatasetPreset(
        name="commodity_futures_panel",
        description="Continuous commodity futures returns panel (Hollstein 2020-style).",
        namespace="aqp_commodity",
        table="futures_panel",
        source_kind="local_csv",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_commodity_futures_panel",
        default_symbols=["CL=F.NYM", "GC=F.CME", "SI=F.CME", "HG=F.CME", "ZS=F.CME", "ZW=F.CME", "ZC=F.CME", "KC=F.NYBOT", "SB=F.NYBOT"],
        interval="1d",
        tags=["commodity", "futures"],
    ),
    "china_a_shares_top200": DatasetPreset(
        name="china_a_shares_top200",
        description="Top 200 China A-shares by market cap (akshare).",
        namespace="aqp_china",
        table="daily_bars",
        source_kind="akshare",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_akshare_china_panel",
        requires_api_key=False,
        interval="1d",
        tags=["china", "equity"],
    ),
    "crypto_majors_intraday": DatasetPreset(
        name="crypto_majors_intraday",
        description="KuCoin BTC/ETH/SOL/XRP/DOGE/ADA 5-minute bars (powers QTradeX strategies).",
        namespace="aqp_crypto",
        table="intraday_5min",
        source_kind="kucoin",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_crypto_kucoin_intraday",
        default_symbols=["BTC.BINANCE", "ETH.BINANCE", "SOL.BINANCE", "XRP.BINANCE", "DOGE.BINANCE", "ADA.BINANCE"],
        interval="5m",
        tags=["crypto", "intraday"],
    ),
    "equity_universe_sp500_daily": DatasetPreset(
        name="equity_universe_sp500_daily",
        description="S&P 500 constituents — daily OHLCV via yfinance (default training universe).",
        namespace="aqp_equity",
        table="sp500_daily",
        source_kind="yfinance",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_sp500_daily",
        interval="1d",
        tags=["equity", "us"],
    ),
    "fred_macro_basket": DatasetPreset(
        name="fred_macro_basket",
        description="FRED macro basket: unemployment, CPI, PMI, 10Y yield, VIX.",
        namespace="aqp_macro",
        table="fred_basket",
        source_kind="fred",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_fred_macro_basket",
        requires_api_key=True,
        api_key_env_var="AQP_FRED_API_KEY",
        interval="1d",
        schedule_cron="0 9 * * 1-5",  # 9am weekdays
        tags=["macro", "fred"],
    ),
    "eod_options_chain_sample": DatasetPreset(
        name="eod_options_chain_sample",
        description="Small SPY options chain snapshot for options analytics demos.",
        namespace="aqp_options",
        table="spy_chain_sample",
        source_kind="local_csv",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_eod_options_sample",
        default_symbols=["SPY.NASDAQ"],
        interval="1d",
        tags=["options", "sample"],
    ),
    "finrl_fundamentals_panel_sample": DatasetPreset(
        name="finrl_fundamentals_panel_sample",
        description="FinRL-style fundamentals panel sample for ML stock selection and bucket-neutral ranking.",
        namespace="aqp_finrl",
        table="fundamentals_panel_sample",
        source_kind="local_csv",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_finrl_fundamentals_panel_sample",
        interval="1d",
        tags=["finrl_trading", "fundamentals", "ml"],
    ),
    "finrl_sp500_membership_pit_sample": DatasetPreset(
        name="finrl_sp500_membership_pit_sample",
        description="Point-in-time S&P500 membership sample used by FinRL-style historical universe filtering.",
        namespace="aqp_finrl",
        table="sp500_membership_pit_sample",
        source_kind="local_csv",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_finrl_sp500_membership_pit_sample",
        interval="1d",
        tags=["finrl_trading", "equity", "universe", "point_in_time"],
    ),
    "quant_trading_oil_money_sample": DatasetPreset(
        name="quant_trading_oil_money_sample",
        description="Quant Trading Oil Money sample panel (oil + petrocurrency relations) for regression residual strategies.",
        namespace="aqp_quant",
        table="oil_money_sample",
        source_kind="local_csv",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_quant_oil_money_sample",
        interval="1d",
        tags=["quant_trading", "fx", "macro", "stat_arb"],
    ),
    "quant_trading_smart_farmers_cleaned_sample": DatasetPreset(
        name="quant_trading_smart_farmers_cleaned_sample",
        description="Smart Farmers cleaned tabular sample with normalized columns and missing-value handling.",
        namespace="aqp_quant",
        table="smart_farmers_cleaned_sample",
        source_kind="local_csv",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_quant_smart_farmers_cleaned_sample",
        interval="1d",
        tags=["quant_trading", "tabular", "preprocessing", "cleaning"],
    ),
    "finviz_screener": DatasetPreset(
        name="finviz_screener",
        description="Finviz screener snapshot table for equity filtering demos.",
        namespace="aqp_screens",
        table="finviz_snapshots",
        source_kind="scraper",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_finviz_screener",
        interval="1d",
        tags=["screening", "equity", "scraper"],
    ),
    "lob_btcusdt_sample": DatasetPreset(
        name="lob_btcusdt_sample",
        description="Binance Futures BTCUSDT depth+trade gz sample for hftbacktest stubs.",
        namespace="aqp_lob",
        table="btcusdt_samples",
        source_kind="local_gz",
        ingestion_task="aqp.tasks.dataset_preset_tasks.ingest_lob_sample",
        default_symbols=["BTCUSDT.BINANCE"],
        interval="tick",
        tags=["lob", "hft", "sample"],
    ),
}


def _default_setup_steps(preset: DatasetPreset) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "id": "review",
            "label": "Review dataset metadata and licensing notes",
            "status": "pending",
        }
    ]
    if preset.requires_api_key and preset.api_key_env_var:
        steps.append(
            {
                "id": "credentials",
                "label": f"Configure {preset.api_key_env_var}",
                "status": "pending",
                "secret_ref": preset.api_key_env_var,
            }
        )
    steps.extend(
        [
            {
                "id": "sink",
                "label": "Select sink and namespace",
                "status": "pending",
                "default_sink": "sink.iceberg",
            },
            {
                "id": "schedule",
                "label": "Choose manual or scheduled ingestion",
                "status": "pending",
                "cron": preset.schedule_cron,
            },
        ]
    )
    return steps


def _default_required_config(preset: DatasetPreset) -> dict[str, Any]:
    config: dict[str, Any] = {
        "source_kind": preset.source_kind,
        "namespace": preset.namespace,
        "table": preset.table,
        "interval": preset.interval,
    }
    if preset.default_symbols:
        config["symbols"] = preset.default_symbols
    if preset.api_key_env_var:
        config["credentials_ref"] = preset.api_key_env_var
    return config


def _default_manifest_hint(preset: DatasetPreset) -> dict[str, Any]:
    return {
        "name": preset.name,
        "namespace": preset.namespace,
        "description": preset.description,
        "tags": list(preset.tags),
        "source": {
            "name": f"source.{preset.source_kind.replace('-', '_')}",
            "kwargs": {
                "symbols": list(preset.default_symbols),
                "interval": preset.interval,
            },
        },
        "transforms": [],
        "sink": {
            "name": "sink.iceberg",
            "kwargs": {
                "namespace": preset.namespace,
                "table": preset.table,
                "provider": preset.source_kind,
            },
        },
        "schedule": {
            "enabled": bool(preset.schedule_cron),
            "cron": preset.schedule_cron,
        },
    }


def get_preset(name: str) -> DatasetPreset:
    if name not in PRESETS:
        raise KeyError(f"Unknown dataset preset: {name!r}; known={sorted(PRESETS)}")
    return PRESETS[name]


def list_presets() -> list[DatasetPreset]:
    return list(PRESETS.values())


def list_preset_names() -> list[str]:
    return sorted(PRESETS)


def list_presets_by_tag(tag: str) -> list[DatasetPreset]:
    return [p for p in PRESETS.values() if tag in p.tags]


__all__ = [
    "DatasetPreset",
    "PRESETS",
    "get_preset",
    "list_preset_names",
    "list_presets",
    "list_presets_by_tag",
]
