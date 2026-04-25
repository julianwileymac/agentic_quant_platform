"""IBKR market-data ingester -> Kafka.

Covers every streaming/market-data primitive referenced in the
IBKR TWS API docs anchors the user pointed at:

- ``#delayed-market-data`` -- ``reqMarketDataType(3|4)`` + ``reqMktData``
- ``#live-md``              -- ``reqMktData(live)``, ``reqTickByTickData``, ``reqRealTimeBars``
- ``#market-scanner``       -- ``reqScannerSubscription`` + periodic polling
- ``#ec``                   -- ``reqContractDetails`` (event contracts / stocks / futures)

Produces to the canonical Avro topics:

- ``market.trade.v1``      <- ``tickByTick(AllLast)``
- ``market.quote.v1``      <- ``tickByTick(BidAsk)``
- ``market.bar.v1``        <- ``reqRealTimeBars``
- ``market.snapshot.v1``   <- ``reqMktData`` (tickPrice/tickSize events)
- ``market.scanner.v1``    <- ``reqScannerSubscription``
- ``market.contract.v1``   <- ``reqContractDetails`` (log-compacted)

The ingester assumes a single active IB Gateway or TWS connection via
``AQP_IBKR_HOST``/``AQP_IBKR_PORT`` and a **reserved client id** --
different from the brokerage adapter's ``AQP_IBKR_CLIENT_ID`` -- so the
two can coexist.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any

try:
    from ib_async import IB  # type: ignore[import]
    from ib_async import Contract as _IBContract
    from ib_async import ScannerSubscription as _IBScannerSubscription
    from ib_async import Stock as _IBStock
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        'IBKRIngester requires the "ibkr" extra. '
        'Install with: pip install -e ".[ibkr]"'
    ) from exc

from aqp.config import settings
from aqp.streaming.ingesters.base import BaseIngester
from aqp.streaming.kafka_producer import KafkaAvroProducer

logger = logging.getLogger(__name__)


# Client id offset keeps the ingester out of the way of the brokerage (+100)
# and the session feed (+200); anything above +100 is reserved.
INGESTER_CLIENT_ID_OFFSET = 200

# Generic tick list requested alongside reqMktData. See
# https://interactivebrokers.github.io/tws-api/tick_types.html
#  - 225: Auction values
#  - 232: VWAP
#  - 233: RT volume trade conditions
#  - 236: Shortable
DEFAULT_GENERIC_TICKS = "225,232,233,236"


def _symbol_to_contract(vt_symbol: str, default_exchange: str = "SMART", currency: str = "USD") -> _IBContract:
    """Build an IB ``Contract`` from a ``vt_symbol`` or raw ticker."""
    if "." in vt_symbol:
        ticker, _ = vt_symbol.rsplit(".", 1)
    else:
        ticker = vt_symbol
    return _IBStock(ticker, default_exchange, currency)


def _ns_from_ts(ts: Any) -> int:
    if ts is None:
        return time.time_ns()
    # ib_async returns ``datetime`` (sometimes tz-aware, sometimes naive UTC)
    try:
        return int(ts.timestamp() * 1_000_000_000)
    except Exception:
        return time.time_ns()


class IBKRIngester(BaseIngester):
    """Long-lived IBKR -> Kafka ingester."""

    venue = "ibkr"

    def __init__(
        self,
        producer: KafkaAvroProducer,
        *,
        universe: Iterable[str] | None = None,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> None:
        from aqp.streaming.ingesters.base import IngesterMetrics

        super().__init__(
            producer,
            universe=list(universe or settings.stream_universe_list),
            metrics=IngesterMetrics(venue=self.venue),
        )
        self.host = host or settings.ibkr_host
        self.port = int(port if port is not None else settings.ibkr_port)
        base_id = int(client_id if client_id is not None else settings.ibkr_client_id)
        self.client_id = base_id + INGESTER_CLIENT_ID_OFFSET
        self.exchange = exchange
        self.currency = currency
        self._ib = IB()
        self._contracts: dict[str, _IBContract] = {}
        self._scanner_task: asyncio.Task[None] | None = None

    async def _connect(self) -> None:
        if self._ib.isConnected():
            return
        await self._ib.connectAsync(
            self.host,
            self.port,
            clientId=self.client_id,
            timeout=15.0,
            readonly=True,
        )
        self._ib.reqMarketDataType(int(settings.stream_market_data_type))
        logger.info(
            "ibkr ingester connected host=%s port=%d clientId=%d market_data_type=%d",
            self.host,
            self.port,
            self.client_id,
            settings.stream_market_data_type,
        )

    async def _disconnect(self) -> None:
        try:
            if self._ib.isConnected():
                self._ib.disconnect()
        except Exception:
            logger.exception("ibkr disconnect error")

    async def _resolve_contracts(self) -> None:
        """Call ``reqContractDetails`` for each symbol and publish metadata."""
        for vt_symbol in self.universe:
            contract = _symbol_to_contract(vt_symbol, self.exchange, self.currency)
            try:
                details_list = await self._ib.reqContractDetailsAsync(contract)
            except Exception:
                logger.exception("reqContractDetails failed for %s", vt_symbol)
                continue
            if not details_list:
                logger.warning("no contract details for %s", vt_symbol)
                continue
            details = details_list[0]
            qualified = details.contract
            self._contracts[vt_symbol] = qualified
            self.produce(
                "market_contract_v1",
                {
                    "ts_ns": time.time_ns(),
                    "vt_symbol": vt_symbol,
                    "con_id": int(qualified.conId or 0),
                    "sec_type": str(qualified.secType or "STK"),
                    "primary_exchange": qualified.primaryExchange or None,
                    "exchange": qualified.exchange or None,
                    "currency": qualified.currency or self.currency,
                    "local_symbol": qualified.localSymbol or None,
                    "trading_class": qualified.tradingClass or None,
                    "min_tick": float(details.minTick) if getattr(details, "minTick", None) else None,
                    "price_magnifier": int(details.priceMagnifier) if getattr(details, "priceMagnifier", None) else None,
                    "contract_month": getattr(details, "contractMonth", None) or None,
                    "industry": getattr(details, "industry", None) or None,
                    "category": getattr(details, "category", None) or None,
                    "sub_category": getattr(details, "subcategory", None) or None,
                    "timezone_id": getattr(details, "timeZoneId", None) or None,
                    "trading_hours": getattr(details, "tradingHours", None) or None,
                    "liquid_hours": getattr(details, "liquidHours", None) or None,
                    "market_rule_ids": getattr(details, "marketRuleIds", None) or None,
                    "underlying_con_id": int(details.underConId) if getattr(details, "underConId", None) else None,
                    "event_kind": "upsert",
                    "venue_source": "ibkr",
                },
                channel="contract",
            )

    def _subscribe_real_time_bars(self) -> None:
        if not settings.stream_include_bars:
            return
        for vt_symbol, contract in self._contracts.items():
            try:
                bars = self._ib.reqRealTimeBars(
                    contract,
                    barSize=5,
                    whatToShow="TRADES",
                    useRTH=False,
                )
                bars.updateEvent += self._make_bar_handler(vt_symbol)
            except Exception:
                logger.exception("reqRealTimeBars failed for %s", vt_symbol)

    def _subscribe_tick_by_tick(self) -> None:
        for vt_symbol, contract in self._contracts.items():
            if settings.stream_include_trades:
                try:
                    ticker = self._ib.reqTickByTickData(contract, "AllLast", numberOfTicks=0, ignoreSize=False)
                    ticker.updateEvent += self._make_trade_handler(vt_symbol)
                except Exception:
                    logger.exception("reqTickByTickData(AllLast) failed for %s", vt_symbol)
            if settings.stream_include_quotes:
                try:
                    ticker = self._ib.reqTickByTickData(contract, "BidAsk", numberOfTicks=0, ignoreSize=False)
                    ticker.updateEvent += self._make_quote_handler(vt_symbol)
                except Exception:
                    logger.exception("reqTickByTickData(BidAsk) failed for %s", vt_symbol)

    def _subscribe_snapshots(self) -> None:
        for vt_symbol, contract in self._contracts.items():
            try:
                ticker = self._ib.reqMktData(
                    contract,
                    genericTickList=DEFAULT_GENERIC_TICKS,
                    snapshot=False,
                    regulatorySnapshot=False,
                )
                ticker.updateEvent += self._make_snapshot_handler(vt_symbol)
            except Exception:
                logger.exception("reqMktData failed for %s", vt_symbol)

    def _make_bar_handler(self, vt_symbol: str) -> Any:
        def handler(bars: Any, has_new_bar: bool) -> None:
            if not has_new_bar or not bars:
                return
            last = bars[-1]
            try:
                self.produce(
                    "market_bar_v1",
                    {
                        "ts_ns": _ns_from_ts(getattr(last, "time", None)),
                        "vt_symbol": vt_symbol,
                        "interval": "5s",
                        "open": float(getattr(last, "open_", last.open)),
                        "high": float(last.high),
                        "low": float(last.low),
                        "close": float(last.close),
                        "volume": float(last.volume),
                        "vwap": float(getattr(last, "wap", 0.0)) or None,
                        "trade_count": int(getattr(last, "count", 0)) or None,
                        "bar_type": "realtime",
                        "venue_source": "ibkr",
                    },
                    channel="realtime_bar",
                )
            except Exception:
                logger.exception("bar handler failed for %s", vt_symbol)

        return handler

    def _make_trade_handler(self, vt_symbol: str) -> Any:
        def handler(tickers: Any) -> None:
            # ib_async's tickByTick AllLast posts a ticker with last trade filled in.
            try:
                for ticker in tickers if isinstance(tickers, (list, tuple)) else [tickers]:
                    last = getattr(ticker, "last", None)
                    last_size = getattr(ticker, "lastSize", 0)
                    if last is None:
                        continue
                    self.produce(
                        "market_trade_v1",
                        {
                            "ts_ns": _ns_from_ts(getattr(ticker, "time", None)),
                            "vt_symbol": vt_symbol,
                            "price": float(last),
                            "size": float(last_size or 0.0),
                            "exchange_code": getattr(ticker, "lastExchange", None) or None,
                            "conditions": [],
                            "trade_id": None,
                            "venue_source": "ibkr",
                        },
                        channel="trade",
                    )
            except Exception:
                logger.exception("trade handler failed for %s", vt_symbol)

        return handler

    def _make_quote_handler(self, vt_symbol: str) -> Any:
        def handler(tickers: Any) -> None:
            try:
                for ticker in tickers if isinstance(tickers, (list, tuple)) else [tickers]:
                    bid = getattr(ticker, "bid", None)
                    ask = getattr(ticker, "ask", None)
                    if bid is None and ask is None:
                        continue
                    self.produce(
                        "market_quote_v1",
                        {
                            "ts_ns": _ns_from_ts(getattr(ticker, "time", None)),
                            "vt_symbol": vt_symbol,
                            "bid": float(bid or 0.0),
                            "ask": float(ask or 0.0),
                            "bid_size": float(getattr(ticker, "bidSize", 0) or 0),
                            "ask_size": float(getattr(ticker, "askSize", 0) or 0),
                            "bid_exchange": getattr(ticker, "bidExchange", None) or None,
                            "ask_exchange": getattr(ticker, "askExchange", None) or None,
                            "conditions": [],
                            "venue_source": "ibkr",
                        },
                        channel="quote",
                    )
            except Exception:
                logger.exception("quote handler failed for %s", vt_symbol)

        return handler

    def _make_snapshot_handler(self, vt_symbol: str) -> Any:
        def handler(ticker: Any) -> None:
            try:
                tick_map: dict[str, float] = {}
                for field in ("bid", "ask", "last", "high", "low", "close", "open", "volume", "bidSize", "askSize", "lastSize"):
                    val = getattr(ticker, field, None)
                    if val is not None:
                        try:
                            tick_map[field] = float(val)
                        except (TypeError, ValueError):
                            continue
                if not tick_map:
                    return
                self.produce(
                    "market_snapshot_v1",
                    {
                        "ts_ns": _ns_from_ts(getattr(ticker, "time", None)),
                        "vt_symbol": vt_symbol,
                        "market_data_type": int(settings.stream_market_data_type),
                        "tick_map": tick_map,
                        "generic_ticks": DEFAULT_GENERIC_TICKS.split(","),
                        "venue_source": "ibkr",
                    },
                    channel="snapshot",
                )
            except Exception:
                logger.exception("snapshot handler failed for %s", vt_symbol)

        return handler

    async def _scanner_loop(self) -> None:
        """Poll ``reqScannerSubscription`` on a fixed interval."""
        if not settings.stream_scanner_enabled:
            return
        interval = max(30, int(settings.stream_scanner_interval_sec))
        scan_codes = ["TOP_PERC_GAIN", "TOP_PERC_LOSE", "HOT_BY_VOLUME"]
        while not self._stop_event.is_set():
            for scan_code in scan_codes:
                sub = _IBScannerSubscription(
                    instrument="STK",
                    locationCode="STK.US.MAJOR",
                    scanCode=scan_code,
                    numberOfRows=25,
                )
                try:
                    rows = await self._ib.reqScannerDataAsync(sub)
                except Exception:
                    logger.exception("reqScannerData failed scan_code=%s", scan_code)
                    continue
                for row in rows:
                    con = row.contractDetails.contract
                    ticker = con.symbol
                    exch = con.primaryExchange or con.exchange or "NASDAQ"
                    vt = f"{ticker}.{exch}"
                    self.produce(
                        "market_scanner_v1",
                        {
                            "ts_ns": time.time_ns(),
                            "scan_code": scan_code,
                            "instrument": "STK",
                            "location_code": "STK.US.MAJOR",
                            "rank": int(row.rank),
                            "vt_symbol": vt,
                            "con_id": int(con.conId or 0) or None,
                            "projection": getattr(row, "projection", None) or None,
                            "legs_str": getattr(row, "legsStr", None) or None,
                            "scanner_params_hash": None,
                        },
                        channel="scanner",
                    )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _run_once(self) -> None:
        await self._connect()
        try:
            await self._resolve_contracts()
            self._subscribe_real_time_bars()
            self._subscribe_tick_by_tick()
            self._subscribe_snapshots()
            self._scanner_task = asyncio.create_task(self._scanner_loop(), name="ibkr-scanner")
            # Park until stop or disconnection.
            while not self._stop_event.is_set() and self._ib.isConnected():
                await asyncio.sleep(1.0)
        finally:
            if self._scanner_task and not self._scanner_task.done():
                self._scanner_task.cancel()
                try:
                    await self._scanner_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
                self._scanner_task = None
            await self._disconnect()
