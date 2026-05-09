"""Polymorphic ``BaseDataHandler`` abstraction over historical bar feeds.

The legacy backtest runner (``aqp.backtest.runner.run_backtest_from_config``)
infers data sources from a YAML config: parquet root, Iceberg table,
or the default DuckDB-backed history. That works for batch backtests
but doesn't compose well with the agentic workflow described in the
report — agents need to spin up backtests against:

- workspace-owned bronze tables (Phase 2 uploads)
- ad-hoc local Parquet files
- live API providers (yfinance / Alpaca / Polygon) for sandbox runs
- replayed Kafka topics for streaming backtests

This module unifies them under a single :class:`BaseDataHandler` ABC.
Each handler emits a chronologically sorted :class:`pandas.DataFrame`
of bars with a UTC :class:`pandas.DatetimeIndex` and (at minimum)
``open``, ``high``, ``low``, ``close``, ``volume`` columns plus a
``vt_symbol`` column. The :class:`EventDrivenBacktester` already
understands that frame; what changes is who produces it.

Handler implementations:

- :class:`IcebergDataHandler` — wraps :class:`DuckDBHistoryProvider`
  reading directly from Iceberg via ``iceberg_to_duckdb_view``.
- :class:`LocalParquetDataHandler` — wraps the ``LocalParquetSource``
  shipped under ``aqp.data.ingestion``.
- :class:`YFinanceDataHandler` — fetches via ``yfinance`` (already a
  core dep; used today by ``aqp.backtest.benchmarks``).
- :class:`AlpacaDataHandler` — uses the optional ``alpaca-py`` SDK.
- :class:`KafkaReplayDataHandler` — replays a Kafka topic to disk and
  yields the resulting frame; useful for backtesting against
  streaming-only datasets.

The factory :func:`build_data_handler` reads a small dict spec and
returns the right concrete handler, so call sites (Celery tasks, the
backtest runner, the Phase 4 iterative loop) don't need to import
every concrete class.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DataHandlerSpec:
    """Declarative spec for a :class:`BaseDataHandler`.

    Construct via the factory :func:`build_data_handler`. The minimal
    fields are ``kind`` + ``symbols``; everything else is per-kind.
    """

    kind: str  # ``iceberg`` | ``parquet`` | ``yfinance`` | ``alpaca`` | ``kafka``
    symbols: tuple[str, ...]
    start: datetime | None = None
    end: datetime | None = None
    iceberg_identifier: str | None = None
    parquet_root: str | None = None
    interval: str = "1d"
    extras: dict[str, Any] | None = None


class BaseDataHandler(ABC):
    """Abstract bar feed used by :class:`EventDrivenBacktester`.

    Concrete implementations override :meth:`fetch_bars`. The base
    class normalises the returned frame into the schema the engine
    expects.
    """

    name: str = "base"

    def __init__(
        self,
        symbols: Iterable[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> None:
        self.symbols = tuple(symbols)
        self.start = start
        self.end = end
        self.interval = interval

    @abstractmethod
    def fetch_bars(self) -> pd.DataFrame:
        """Return a chronologically sorted bar frame with UTC index."""

    # ------------------------------------------------------------------
    # Helpers shared across concrete handlers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_frame(df: pd.DataFrame) -> pd.DataFrame:
        """Coerce to UTC index + canonical OHLCV column names."""
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        if "timestamp" in out.columns:
            out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
            out = out.set_index("timestamp")
        elif not isinstance(out.index, pd.DatetimeIndex):
            try:
                out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
            except Exception:  # noqa: BLE001
                logger.debug("could not coerce index to datetime", exc_info=True)
        if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is None:
            out.index = out.index.tz_localize("UTC")
        rename = {}
        for col in ("Open", "High", "Low", "Close", "Volume", "Adj Close"):
            target = col.lower().replace(" ", "_")
            if col in out.columns and target not in out.columns:
                rename[col] = target
        if rename:
            out = out.rename(columns=rename)
        return out.sort_index()


class IcebergDataHandler(BaseDataHandler):
    """Read bars from an Iceberg table via :class:`DuckDBHistoryProvider`."""

    name = "iceberg"

    def __init__(
        self,
        iceberg_identifier: str,
        symbols: Iterable[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> None:
        super().__init__(symbols, start=start, end=end, interval=interval)
        self.iceberg_identifier = iceberg_identifier

    def fetch_bars(self) -> pd.DataFrame:
        from aqp.data.iceberg_catalog import iceberg_to_duckdb_view

        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("duckdb required for IcebergDataHandler") from exc

        conn = duckdb.connect(":memory:", read_only=False)
        view = iceberg_to_duckdb_view(conn, self.iceberg_identifier)
        if not view:
            return pd.DataFrame()

        symbol_clause = ""
        if self.symbols:
            joined = ", ".join(f"'{s}'" for s in self.symbols)
            symbol_clause = f"WHERE vt_symbol IN ({joined})"
        date_clauses: list[str] = []
        params: list[Any] = []
        if self.start:
            date_clauses.append("timestamp >= ?")
            params.append(self.start)
        if self.end:
            date_clauses.append("timestamp <= ?")
            params.append(self.end)
        if date_clauses:
            joined_date = " AND ".join(date_clauses)
            symbol_clause = (
                f"{symbol_clause} AND {joined_date}" if symbol_clause else f"WHERE {joined_date}"
            )

        sql = f'SELECT * FROM "{view}" {symbol_clause} ORDER BY timestamp ASC'
        df = conn.execute(sql, params).df()
        return self._normalise_frame(df)


class LocalParquetDataHandler(BaseDataHandler):
    """Read bars from a local Parquet directory."""

    name = "parquet"

    def __init__(
        self,
        parquet_root: str,
        symbols: Iterable[str],
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> None:
        super().__init__(symbols, start=start, end=end, interval=interval)
        self.parquet_root = parquet_root

    def fetch_bars(self) -> pd.DataFrame:
        from aqp.data.duckdb_engine import DuckDBHistoryProvider

        provider = DuckDBHistoryProvider(parquet_root=self.parquet_root)
        df = provider.get_bars(
            symbols=self.symbols,
            start=self.start,
            end=self.end,
            interval=self.interval,
        )
        return self._normalise_frame(df)


class YFinanceDataHandler(BaseDataHandler):
    """Fetch bars via the ``yfinance`` library (free public-market data)."""

    name = "yfinance"

    def fetch_bars(self) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("yfinance not installed") from exc

        if not self.symbols:
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        for symbol in self.symbols:
            ticker = symbol.split(".", 1)[0] if "." in symbol else symbol
            try:
                raw = yf.download(
                    ticker,
                    start=self.start,
                    end=self.end,
                    interval=self.interval,
                    progress=False,
                    auto_adjust=False,
                )
            except Exception:  # noqa: BLE001
                logger.warning("yfinance fetch failed for %s", symbol, exc_info=True)
                continue
            if raw is None or raw.empty:
                continue
            raw = raw.reset_index()
            raw["vt_symbol"] = symbol
            frames.append(raw)

        if not frames:
            return pd.DataFrame()
        merged = pd.concat(frames, ignore_index=True)
        merged = merged.rename(columns={"Date": "timestamp", "Datetime": "timestamp"})
        return self._normalise_frame(merged)


class AlpacaDataHandler(BaseDataHandler):
    """Fetch bars via the optional ``alpaca-py`` SDK.

    Requires the ``[alpaca]`` extra and the user's API keys configured
    via ``settings.alpaca_api_key`` / ``settings.alpaca_api_secret``.
    """

    name = "alpaca"

    def fetch_bars(self) -> pd.DataFrame:
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("alpaca-py not installed (use [alpaca] extra)") from exc

        from aqp.config import settings

        api_key = getattr(settings, "alpaca_api_key", "") or ""
        api_secret = getattr(settings, "alpaca_api_secret", "") or ""
        if not api_key or not api_secret:
            raise RuntimeError("alpaca credentials missing (settings.alpaca_api_key / _secret)")

        unit_map = {
            "1d": (1, TimeFrameUnit.Day),
            "1h": (1, TimeFrameUnit.Hour),
            "5m": (5, TimeFrameUnit.Minute),
            "1m": (1, TimeFrameUnit.Minute),
        }
        amount, unit = unit_map.get(self.interval, (1, TimeFrameUnit.Day))
        timeframe = TimeFrame(amount=amount, unit=unit)

        tickers = [s.split(".", 1)[0] if "." in s else s for s in self.symbols]
        client = StockHistoricalDataClient(api_key, api_secret)
        request = StockBarsRequest(
            symbol_or_symbols=tickers,
            timeframe=timeframe,
            start=self.start,
            end=self.end,
        )
        response = client.get_stock_bars(request)
        df = response.df.reset_index().rename(columns={"symbol": "vt_symbol"})
        return self._normalise_frame(df)


class KafkaReplayDataHandler(BaseDataHandler):
    """Replay a Kafka topic into the engine.

    The handler reads the named topic from the workspace's Kafka
    cluster, snapshots the messages to a DataFrame, and returns it.
    This intentionally does **not** drive the engine event loop with
    Kafka semantics — the goal is to backtest against streaming-only
    data sources by capturing them once and replaying off the
    captured frame, which keeps the backtest deterministic.
    """

    name = "kafka_replay"

    def __init__(
        self,
        topic: str,
        symbols: Iterable[str],
        *,
        bootstrap_servers: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
        max_messages: int = 100_000,
    ) -> None:
        super().__init__(symbols, start=start, end=end, interval=interval)
        self.topic = topic
        self.bootstrap_servers = bootstrap_servers
        self.max_messages = int(max_messages)

    def fetch_bars(self) -> pd.DataFrame:
        try:
            from confluent_kafka import Consumer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("confluent-kafka not installed (use [streaming] extra)") from exc

        consumer = Consumer(
            {
                "bootstrap.servers": self.bootstrap_servers,
                "group.id": f"aqp-replay-{self.topic}",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        consumer.subscribe([self.topic])
        messages: list[dict[str, Any]] = []
        try:
            while len(messages) < self.max_messages:
                msg = consumer.poll(timeout=2.0)
                if msg is None:
                    break
                if msg.error():  # type: ignore[union-attr]
                    continue
                try:
                    payload = msg.value()  # type: ignore[union-attr]
                    if isinstance(payload, bytes):
                        import json

                        payload = json.loads(payload.decode("utf-8"))
                    if isinstance(payload, dict):
                        messages.append(payload)
                except Exception:  # noqa: BLE001
                    continue
        finally:
            consumer.close()

        if not messages:
            return pd.DataFrame()
        df = pd.DataFrame(messages)
        return self._normalise_frame(df)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_data_handler(spec: DataHandlerSpec | dict[str, Any]) -> BaseDataHandler:
    """Construct a :class:`BaseDataHandler` from a spec.

    Accepts either a :class:`DataHandlerSpec` or a plain dict (so
    YAML configs and JSON payloads can be passed verbatim).
    """
    if isinstance(spec, dict):
        spec = DataHandlerSpec(
            kind=str(spec.get("kind") or "").strip().lower(),
            symbols=tuple(spec.get("symbols") or ()),
            start=spec.get("start"),
            end=spec.get("end"),
            iceberg_identifier=spec.get("iceberg_identifier"),
            parquet_root=spec.get("parquet_root"),
            interval=str(spec.get("interval") or "1d"),
            extras=dict(spec.get("extras") or {}),
        )
    kind = spec.kind.lower()
    if kind == "iceberg":
        if not spec.iceberg_identifier:
            raise ValueError("iceberg handler requires iceberg_identifier")
        return IcebergDataHandler(
            iceberg_identifier=spec.iceberg_identifier,
            symbols=spec.symbols,
            start=spec.start,
            end=spec.end,
            interval=spec.interval,
        )
    if kind == "parquet":
        if not spec.parquet_root:
            raise ValueError("parquet handler requires parquet_root")
        return LocalParquetDataHandler(
            parquet_root=spec.parquet_root,
            symbols=spec.symbols,
            start=spec.start,
            end=spec.end,
            interval=spec.interval,
        )
    if kind in ("yfinance", "yahoo"):
        return YFinanceDataHandler(
            symbols=spec.symbols,
            start=spec.start,
            end=spec.end,
            interval=spec.interval,
        )
    if kind == "alpaca":
        return AlpacaDataHandler(
            symbols=spec.symbols,
            start=spec.start,
            end=spec.end,
            interval=spec.interval,
        )
    if kind in ("kafka", "kafka_replay"):
        extras = spec.extras or {}
        topic = str(extras.get("topic") or "")
        bootstrap = str(extras.get("bootstrap_servers") or "")
        if not topic or not bootstrap:
            raise ValueError("kafka handler requires extras.topic + extras.bootstrap_servers")
        return KafkaReplayDataHandler(
            topic=topic,
            bootstrap_servers=bootstrap,
            symbols=spec.symbols,
            start=spec.start,
            end=spec.end,
            interval=spec.interval,
            max_messages=int(extras.get("max_messages") or 100_000),
        )
    raise ValueError(f"unsupported data handler kind: {spec.kind!r}")


__all__ = [
    "AlpacaDataHandler",
    "BaseDataHandler",
    "DataHandlerSpec",
    "IcebergDataHandler",
    "KafkaReplayDataHandler",
    "LocalParquetDataHandler",
    "YFinanceDataHandler",
    "build_data_handler",
]
