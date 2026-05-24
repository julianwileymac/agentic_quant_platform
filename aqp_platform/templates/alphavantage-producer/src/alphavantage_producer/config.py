"""Runtime configuration for the Alpha Vantage producer.

Two layers:

* Environment variables (Kafka bootstrap, SASL, OTel, metrics port, AV base
  URL, etc.).
* Optional YAML config file mounted from a ConfigMap that defines the symbol
  universe and per-stream cadence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProducerSettings(BaseSettings):
    """Env-driven settings shared across all AV streams."""

    model_config = SettingsConfigDict(env_prefix="AV_PRODUCER_", extra="ignore")

    # Kafka
    bootstrap_servers: str = Field(
        default="trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094",
    )
    security_protocol: str = Field(default="SASL_SSL")
    sasl_mechanism: str = Field(default="SCRAM-SHA-512")
    sasl_username: str = Field(default="producer-market")
    sasl_password: Optional[str] = Field(default=None)
    sasl_password_file: Optional[str] = Field(default=None)
    ssl_ca_location: Optional[str] = Field(default="/etc/kafka/ca/ca.crt")
    client_id: str = Field(default="alphavantage-producer")

    # Schema registry
    schema_registry_url: str = Field(
        default="http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2",
    )
    schema_group: str = Field(default="default")
    schema_dir: str = Field(
        default="/opt/alphavantage-producer/schemas",
        description="Path to the alphavantage/*.avsc schema files inside the container.",
    )
    register_schemas_on_start: bool = Field(default=True)

    # Topics
    topic_quote: str = Field(default="alphavantage.quote.v1")
    topic_bar: str = Field(default="alphavantage.bar.v1")
    topic_fx: str = Field(default="alphavantage.fx.v1")
    topic_crypto: str = Field(default="alphavantage.crypto.v1")
    topic_indicator: str = Field(default="alphavantage.indicator.v1")
    topic_news: str = Field(default="alphavantage.news.v1")
    topic_gainers: str = Field(default="alphavantage.gainers.v1")
    topic_insider: str = Field(default="alphavantage.insider.v1")
    topic_overview: str = Field(default="alphavantage.overview.v1")
    topic_earnings: str = Field(default="alphavantage.earnings.v1")
    topic_options: str = Field(default="alphavantage.options.v1")
    topic_commodity: str = Field(default="alphavantage.commodity.v1")
    topic_econ: str = Field(default="alphavantage.econ.v1")
    topic_deadletter: str = Field(default="alphavantage.deadletter.v1")

    # AV engine
    av_api_key: Optional[str] = Field(default=None)
    av_api_key_file: Optional[str] = Field(default="/var/run/secrets/alphavantage/api-key")
    av_base_url: str = Field(default="https://www.alphavantage.co/query")
    av_rpm_limit: int = Field(default=75)
    av_daily_limit: int = Field(default=0)
    av_timeout_seconds: float = Field(default=15.0)
    av_max_retries: int = Field(default=5)

    # Config file (symbol universe / cadence)
    config_file: Optional[str] = Field(
        default="/etc/alphavantage-producer/config.yaml",
        description="Path to a YAML file describing streams + symbols + cadence.",
    )

    # Runtime
    metrics_port: int = Field(default=9312)
    service_name: str = Field(default="alphavantage-producer")
    otel_endpoint: str = Field(
        default="http://otel-collector.observability.svc.cluster.local:4317",
    )

    def resolve_sasl_password(self) -> Optional[str]:
        if self.sasl_password:
            return self.sasl_password
        if self.sasl_password_file:
            try:
                return open(self.sasl_password_file, "r", encoding="utf-8").read().strip()
            except OSError:
                return None
        return None


# ---------------------------------------------------------------------------
# Stream definitions loaded from config.yaml
# ---------------------------------------------------------------------------


@dataclass
class StreamConfig:
    name: str
    enabled: bool = True
    interval_seconds: float = 60.0
    extras: Dict[str, object] = field(default_factory=dict)


@dataclass
class SymbolUniverse:
    equities: List[str] = field(default_factory=list)
    fx_pairs: List[Dict[str, str]] = field(default_factory=list)
    crypto_pairs: List[Dict[str, str]] = field(default_factory=list)
    options: List[str] = field(default_factory=list)


@dataclass
class IndicatorRequest:
    name: str
    symbol: str
    interval: str = "daily"
    time_period: int = 20
    series_type: str = "close"


@dataclass
class RuntimeConfig:
    """Full runtime profile merged from env + yaml file."""

    streams: Dict[str, StreamConfig] = field(default_factory=dict)
    universe: SymbolUniverse = field(default_factory=SymbolUniverse)
    indicators: List[IndicatorRequest] = field(default_factory=list)


def load_runtime_config(path: Optional[str]) -> RuntimeConfig:
    """Read ``path`` (YAML) if present, otherwise return a minimal default."""

    if not path:
        return _default_runtime()

    try:
        import yaml
    except ImportError:
        return _default_runtime()

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except OSError:
        return _default_runtime()

    streams_cfg: Dict[str, StreamConfig] = {}
    for name, data in (raw.get("streams") or {}).items():
        data = data or {}
        streams_cfg[name] = StreamConfig(
            name=name,
            enabled=bool(data.get("enabled", True)),
            interval_seconds=float(data.get("interval_seconds", 60.0)),
            extras={k: v for k, v in data.items() if k not in {"enabled", "interval_seconds"}},
        )

    universe_raw = raw.get("universe") or {}
    universe = SymbolUniverse(
        equities=list(universe_raw.get("equities") or []),
        fx_pairs=[dict(p) for p in (universe_raw.get("fx_pairs") or [])],
        crypto_pairs=[dict(p) for p in (universe_raw.get("crypto_pairs") or [])],
        options=list(universe_raw.get("options") or []),
    )

    indicators = [
        IndicatorRequest(
            name=str(item.get("name", "")).upper(),
            symbol=str(item.get("symbol", "")),
            interval=str(item.get("interval", "daily")),
            time_period=int(item.get("time_period", 20)),
            series_type=str(item.get("series_type", "close")),
        )
        for item in (raw.get("indicators") or [])
        if item.get("name") and item.get("symbol")
    ]

    return RuntimeConfig(streams=streams_cfg, universe=universe, indicators=indicators)


def _default_runtime() -> RuntimeConfig:
    return RuntimeConfig(
        streams={
            "quote": StreamConfig(name="quote", interval_seconds=60.0),
            "bar": StreamConfig(
                name="bar", interval_seconds=300.0,
                extras={"interval": "5min", "outputsize": "compact"},
            ),
            "news": StreamConfig(name="news", interval_seconds=300.0),
            "gainers": StreamConfig(name="gainers", interval_seconds=300.0),
            "fx": StreamConfig(name="fx", interval_seconds=60.0),
            "crypto": StreamConfig(
                name="crypto", interval_seconds=120.0, extras={"interval": "5min"},
            ),
            "indicator": StreamConfig(name="indicator", interval_seconds=600.0),
        },
        universe=SymbolUniverse(
            equities=["IBM", "AAPL", "MSFT", "GOOGL", "SPY"],
            fx_pairs=[{"from": "EUR", "to": "USD"}, {"from": "USD", "to": "JPY"}],
            crypto_pairs=[{"symbol": "BTC", "market": "USD"}, {"symbol": "ETH", "market": "USD"}],
        ),
        indicators=[
            IndicatorRequest(name="SMA", symbol="IBM", interval="daily", time_period=20),
            IndicatorRequest(name="RSI", symbol="IBM", interval="daily", time_period=14),
            IndicatorRequest(name="MACD", symbol="IBM", interval="daily"),
        ],
    )


__all__ = [
    "IndicatorRequest",
    "ProducerSettings",
    "RuntimeConfig",
    "StreamConfig",
    "SymbolUniverse",
    "load_runtime_config",
]
