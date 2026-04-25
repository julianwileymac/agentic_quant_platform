"""IBKR historical bars service for preview + lake ingestion flows.

Design goals:
- lazy-import ``ib_async`` so importing this module is safe on hosts without
  the ``ibkr`` extra;
- enforce IBKR historical request constraints up front with actionable errors;
- return canonical tidy bars matching the Parquet lake schema.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)

_BAR_SIZE_ALIASES: dict[str, str] = {
    "1s": "1 secs",
    "5s": "5 secs",
    "10s": "10 secs",
    "15s": "15 secs",
    "30s": "30 secs",
    "1m": "1 min",
    "2m": "2 mins",
    "3m": "3 mins",
    "5m": "5 mins",
    "10m": "10 mins",
    "15m": "15 mins",
    "20m": "20 mins",
    "30m": "30 mins",
    "1h": "1 hour",
    "2h": "2 hours",
    "3h": "3 hours",
    "4h": "4 hours",
    "8h": "8 hours",
    "1d": "1 day",
}

_ALLOWED_BAR_SIZES = {
    "1 secs",
    "5 secs",
    "10 secs",
    "15 secs",
    "30 secs",
    "1 min",
    "2 mins",
    "3 mins",
    "5 mins",
    "10 mins",
    "15 mins",
    "20 mins",
    "30 mins",
    "1 hour",
    "2 hours",
    "3 hours",
    "4 hours",
    "8 hours",
    "1 day",
}

_BAR_SIZE_SECONDS: dict[str, int] = {
    "1 secs": 1,
    "5 secs": 5,
    "10 secs": 10,
    "15 secs": 15,
    "30 secs": 30,
    "1 min": 60,
    "2 mins": 120,
    "3 mins": 180,
    "5 mins": 300,
    "10 mins": 600,
    "15 mins": 900,
    "20 mins": 1200,
    "30 mins": 1800,
    "1 hour": 3600,
    "2 hours": 7200,
    "3 hours": 10800,
    "4 hours": 14400,
    "8 hours": 28800,
    "1 day": 86400,
}

_ALLOWED_WHAT_TO_SHOW = {"TRADES", "MIDPOINT", "BID", "ASK"}

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([SDWMY])\s*$", flags=re.IGNORECASE)

_PRIMARY_EXCHANGE_MAP: dict[str, str] = {
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "ARCA": "ARCA",
    "BATS": "BATS",
    "CBOE": "CBOE",
}


class IBKRHistoricalError(RuntimeError):
    """Base error for IBKR historical requests."""


class IBKRHistoricalValidationError(IBKRHistoricalError):
    """Validation error for unsupported request combinations."""


class IBKRHistoricalPacingError(IBKRHistoricalError):
    """Error raised when request pacing would violate IBKR limits."""


class IBKRHistoricalDependencyError(IBKRHistoricalError):
    """Raised when optional IBKR dependencies are missing."""


class IBKRHistoricalUnavailableError(IBKRHistoricalError):
    """Raised when TWS / IB Gateway cannot be reached."""


class IBKRHistoricalTimeoutError(IBKRHistoricalError):
    """Raised when a historical request times out after all retries."""


# Timeout / transient error markers — these trigger the single retry path.
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (asyncio.TimeoutError, TimeoutError)


@dataclass(frozen=True)
class _PacingEntry:
    ts_monotonic: float
    signature: str
    contract_key: str
    weight: int


class IBKRHistoricalService:
    """Fetch historical bars from IB Gateway / TWS via ``ib_async``."""

    _pacing_lock = threading.Lock()
    _pacing_entries: deque[_PacingEntry] = deque()
    # Cached availability probe; keyed by (host, port).  Holds a tuple of
    # ``(ok: bool, message: str, ts_monotonic: float)``.  TTL is 5 minutes.
    _availability_cache: dict[tuple[str, int], tuple[bool, str, float]] = {}
    _availability_lock = threading.Lock()
    _AVAILABILITY_TTL_SEC = 300.0

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
        exchange: str = "SMART",
        currency: str = "USD",
        connect_timeout: float = 12.0,
        request_timeout: float = 45.0,
        max_requests: int = 60,
        min_request_interval_sec: float = 0.45,
        max_retries: int = 1,
        retry_backoff_sec: float = 2.0,
    ) -> None:
        self.host = host or settings.ibkr_host
        self.port = int(port if port is not None else settings.ibkr_port)
        self.client_id = int(client_id if client_id is not None else settings.ibkr_client_id)
        self.exchange = exchange
        self.currency = currency
        self.connect_timeout = float(connect_timeout)
        self.request_timeout = float(request_timeout)
        self.max_requests = int(max_requests)
        self.min_request_interval_sec = float(min_request_interval_sec)
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_sec = float(retry_backoff_sec)

    async def fetch_bars(
        self,
        *,
        vt_symbol: str,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
        end_date_time: datetime | str | None = None,
        duration_str: str | None = None,
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        exchange: str | None = None,
        currency: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical bars and return canonical tidy bars."""
        clean_vt = _normalize_vt_symbol(vt_symbol)
        ticker, exch = _split_vt_symbol(clean_vt)
        resolved_exchange = (exchange or self.exchange or "SMART").upper()
        resolved_currency = (currency or self.currency or "USD").upper()
        canonical_bar_size = _normalize_bar_size(bar_size)
        canonical_what = _normalize_what_to_show(what_to_show)

        if duration_str:
            _validate_duration_for_bar_size(duration_str, canonical_bar_size)

        start_dt, end_dt = _normalize_time_range(
            start=start,
            end=end,
            end_date_time=end_date_time,
            duration_str=duration_str,
        )

        IB, Stock = _load_ib_components()
        ib = IB()
        client_id = _next_client_id(self.client_id)

        try:
            try:
                await ib.connectAsync(
                    self.host,
                    self.port,
                    clientId=client_id,
                    timeout=self.connect_timeout,
                    readonly=True,
                )
            except _RETRYABLE_EXCEPTIONS as exc:
                raise IBKRHistoricalUnavailableError(
                    f"Could not connect to IBKR at {self.host}:{self.port} "
                    f"(timeout {self.connect_timeout}s). Is TWS / IB Gateway running "
                    "with API access enabled?"
                ) from exc
            except (ConnectionRefusedError, OSError) as exc:
                raise IBKRHistoricalUnavailableError(
                    f"IBKR connection refused at {self.host}:{self.port}. "
                    "Start TWS / IB Gateway and enable API connections."
                ) from exc

            try:
                # Use the same market-data mode knob already exposed for streaming:
                # 1 live, 2 frozen, 3 delayed, 4 delayed-frozen.
                ib.reqMarketDataType(int(settings.stream_market_data_type))
            except Exception:
                # Not fatal for historical requests.
                pass

            contract = Stock(ticker, resolved_exchange, resolved_currency)
            primary_exchange = _PRIMARY_EXCHANGE_MAP.get(exch)
            if primary_exchange:
                contract.primaryExchange = primary_exchange

            try:
                details = await ib.reqContractDetailsAsync(contract)
            except _RETRYABLE_EXCEPTIONS as exc:
                raise IBKRHistoricalTimeoutError(
                    f"Timed out resolving IBKR contract for {clean_vt}."
                ) from exc
            if not details:
                raise IBKRHistoricalValidationError(
                    f"IBKR contract not found or ambiguous for {clean_vt}. "
                    "Try specifying vt_symbol with exchange, e.g. AAPL.NASDAQ."
                )
            qualified_contract = details[0].contract
            if str(getattr(qualified_contract, "secType", "")).upper() != "STK":
                raise IBKRHistoricalValidationError(
                    "This release supports equity/ETF contracts only (IB secType=STK)."
                )

            request_windows = _build_request_windows(
                start_dt=start_dt,
                end_dt=end_dt,
                bar_size=canonical_bar_size,
                explicit_duration=duration_str,
                max_requests=self.max_requests,
            )

            chunks: list[pd.DataFrame] = []
            last_request_ts = 0.0
            contract_key = f"{ticker}|{resolved_exchange}|{canonical_what}"

            for window_end, window_duration in request_windows:
                now = time.monotonic()
                since_last = now - last_request_ts
                if last_request_ts > 0 and since_last < self.min_request_interval_sec:
                    await asyncio.sleep(self.min_request_interval_sec - since_last)
                signature = (
                    f"{ticker}|{resolved_exchange}|{window_end.isoformat()}|"
                    f"{window_duration}|{canonical_bar_size}|{canonical_what}|{int(use_rth)}"
                )
                _check_and_record_pacing(signature=signature, contract_key=contract_key, weight=1)

                bars = await self._fetch_window_with_retry(
                    ib,
                    qualified_contract=qualified_contract,
                    window_end=window_end,
                    window_duration=window_duration,
                    canonical_bar_size=canonical_bar_size,
                    canonical_what=canonical_what,
                    use_rth=use_rth,
                )
                last_request_ts = time.monotonic()

                chunk = _bars_to_frame(bars, clean_vt)
                if chunk.empty:
                    # Stop once IB starts returning empty slices while paging back.
                    if duration_str or window_end <= start_dt:
                        break
                    continue
                chunks.append(chunk)
                if duration_str:
                    break

                earliest = chunk["timestamp"].min()
                if pd.isna(earliest) or earliest <= pd.Timestamp(start_dt):
                    break

            if not chunks:
                return pd.DataFrame(
                    columns=["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]
                )

            out = pd.concat(chunks, ignore_index=True)
            out = out.drop_duplicates(subset=["timestamp", "vt_symbol"]).sort_values("timestamp")
            out = out[(out["timestamp"] >= pd.Timestamp(start_dt)) & (out["timestamp"] <= pd.Timestamp(end_dt))]
            out = out.reset_index(drop=True)
            return out[
                ["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]
            ]
        except IBKRHistoricalError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IBKRHistoricalError(f"IBKR historical request failed: {exc}") from exc
        finally:
            try:
                if ib.isConnected():
                    ib.disconnect()
            except Exception:
                pass

    async def _fetch_window_with_retry(
        self,
        ib: Any,
        *,
        qualified_contract: Any,
        window_end: datetime,
        window_duration: str,
        canonical_bar_size: str,
        canonical_what: str,
        use_rth: bool,
    ) -> Any:
        """Issue one ``reqHistoricalDataAsync`` call with bounded retries.

        Pacing errors are *not* retried — by construction they indicate
        that the caller is hitting IBKR limits and should back off.
        """
        attempts = self.max_retries + 1
        last_exc: BaseException | None = None
        for attempt in range(attempts):
            try:
                return await ib.reqHistoricalDataAsync(
                    contract=qualified_contract,
                    endDateTime=window_end,
                    durationStr=window_duration,
                    barSizeSetting=canonical_bar_size,
                    whatToShow=canonical_what,
                    useRTH=bool(use_rth),
                    formatDate=2,
                    keepUpToDate=False,
                    chartOptions=[],
                    timeout=self.request_timeout,
                )
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    raise IBKRHistoricalTimeoutError(
                        "IBKR historical request timed out after "
                        f"{attempts} attempt(s); window={window_duration} "
                        f"bar={canonical_bar_size}."
                    ) from exc
                logger.warning(
                    "ibkr historical timeout (attempt %d/%d); retrying in %.1fs",
                    attempt + 1,
                    attempts,
                    self.retry_backoff_sec,
                )
                await asyncio.sleep(self.retry_backoff_sec)
        raise IBKRHistoricalTimeoutError(
            "IBKR historical request exhausted retries"
        ) from last_exc

    # ------------------------------------------------------------------
    # Availability probe — cheap health-check used by the UI to gate
    # the "Fetch" button and to surface a clear message when TWS is
    # offline.  Cached for 5 minutes to avoid hammering Gateway.
    # ------------------------------------------------------------------

    @classmethod
    def is_available(
        cls,
        *,
        host: str | None = None,
        port: int | None = None,
        timeout: float = 2.0,
        use_cache: bool = True,
    ) -> tuple[bool, str]:
        """Return ``(ok, message)``. ``ok=False`` when import or connect fails."""
        resolved_host = host or settings.ibkr_host
        resolved_port = int(port if port is not None else settings.ibkr_port)
        key = (resolved_host, resolved_port)

        if use_cache:
            with cls._availability_lock:
                cached = cls._availability_cache.get(key)
                if cached is not None:
                    ok, message, ts = cached
                    if time.monotonic() - ts < cls._AVAILABILITY_TTL_SEC:
                        return ok, message

        try:
            _load_ib_components()
        except IBKRHistoricalDependencyError as exc:
            result = (False, str(exc))
            cls._store_availability(key, *result)
            return result

        # Socket-level probe is enough to know whether TWS/Gateway is
        # accepting connections — we don't need to run the full IB
        # handshake here.
        import socket

        try:
            with socket.create_connection((resolved_host, resolved_port), timeout=timeout):
                result = (True, f"TWS / IB Gateway reachable at {resolved_host}:{resolved_port}.")
        except (OSError, socket.timeout) as exc:
            result = (
                False,
                f"Cannot reach TWS / IB Gateway at {resolved_host}:{resolved_port} ({exc}). "
                "Start TWS/Gateway, enable 'Enable ActiveX and Socket Clients', and make "
                "sure API port matches AQP_IBKR_PORT.",
            )
        cls._store_availability(key, *result)
        return result

    @classmethod
    def _store_availability(cls, key: tuple[str, int], ok: bool, message: str) -> None:
        with cls._availability_lock:
            cls._availability_cache[key] = (ok, message, time.monotonic())

    @classmethod
    def clear_availability_cache(cls) -> None:
        with cls._availability_lock:
            cls._availability_cache.clear()


def _load_ib_components():
    try:
        from ib_async import IB  # type: ignore[import]
        from ib_async import Stock
    except ImportError as exc:  # pragma: no cover
        raise IBKRHistoricalDependencyError(
            'IBKR historical requests require the "ibkr" extra. '
            'Install with: pip install -e ".[ibkr]"'
        ) from exc
    return IB, Stock


def _next_client_id(base_client_id: int) -> int:
    # Keep historical requests separate from brokerage (+0) and streaming (+200).
    return int(base_client_id) + 300 + int(time.time_ns() % 1000)


def _normalize_vt_symbol(vt_symbol: str) -> str:
    raw = (vt_symbol or "").strip().upper()
    if not raw:
        raise IBKRHistoricalValidationError("vt_symbol is required")
    if "." not in raw:
        return f"{raw}.NASDAQ"
    return raw


def _split_vt_symbol(vt_symbol: str) -> tuple[str, str]:
    ticker, exch = vt_symbol.rsplit(".", 1)
    return ticker.strip().upper(), exch.strip().upper()


def _normalize_bar_size(bar_size: str) -> str:
    raw = (bar_size or "").strip().lower()
    canonical = _BAR_SIZE_ALIASES.get(raw, raw)
    # Keep canonical values in IB style casing.
    for candidate in _ALLOWED_BAR_SIZES:
        if candidate.lower() == canonical.lower():
            return candidate
    valid = ", ".join(sorted(_ALLOWED_BAR_SIZES))
    raise IBKRHistoricalValidationError(f"Unsupported bar_size '{bar_size}'. Valid values: {valid}")


def _normalize_what_to_show(what_to_show: str) -> str:
    value = (what_to_show or "").strip().upper()
    if value not in _ALLOWED_WHAT_TO_SHOW:
        valid = ", ".join(sorted(_ALLOWED_WHAT_TO_SHOW))
        raise IBKRHistoricalValidationError(
            f"Unsupported what_to_show '{what_to_show}'. Valid values: {valid}"
        )
    return value


def _parse_time(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise IBKRHistoricalValidationError(
            f"Invalid timestamp '{value}'. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)."
        ) from exc


def _normalize_time_range(
    *,
    start: datetime | str | None,
    end: datetime | str | None,
    end_date_time: datetime | str | None,
    duration_str: str | None,
) -> tuple[datetime, datetime]:
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    if duration_str:
        end_dt = _parse_time(end_date_time) or _parse_time(end) or now
        duration_delta = _duration_to_timedelta(duration_str, anchor=end_dt)
        start_dt = end_dt - duration_delta
        if start_dt >= end_dt:
            raise IBKRHistoricalValidationError("duration_str results in an empty time range")
        return start_dt, end_dt
    start_dt = _parse_time(start)
    end_dt = _parse_time(end) or now
    if start_dt is None:
        # Preserve previous Data Browser behavior: default to roughly two years.
        start_dt = end_dt - timedelta(days=730)
    if start_dt >= end_dt:
        raise IBKRHistoricalValidationError("start must be strictly earlier than end")
    return start_dt, end_dt


def _duration_to_timedelta(
    duration_str: str,
    *,
    anchor: datetime | None = None,
) -> timedelta:
    """Convert an IBKR duration token into a ``timedelta``.

    Months and years use calendar arithmetic (``dateutil.relativedelta``)
    anchored at ``anchor`` (defaults to *now* in UTC) so ``'1 M'`` means
    the same number of days as ``anchor - 1 month`` would, not a rough
    30-day approximation.  Days / weeks / seconds use ``timedelta`` as
    before because they are already exact.
    """
    qty, unit = _parse_duration(duration_str)
    if unit == "S":
        return timedelta(seconds=qty)
    if unit == "D":
        return timedelta(days=qty)
    if unit == "W":
        return timedelta(weeks=qty)
    if unit in {"M", "Y"}:
        try:
            from dateutil.relativedelta import relativedelta
        except ImportError as exc:  # pragma: no cover - dateutil is a hard dep of pandas
            # Fall back to the old rough constants rather than 500-ing in prod.
            logger.warning("dateutil missing; falling back to rough month/year math")
            if unit == "M":
                return timedelta(days=30 * qty)
            return timedelta(days=365 * qty)
        reference = anchor or datetime.now(tz=UTC).replace(tzinfo=None)
        if unit == "M":
            delta = relativedelta(months=qty)
        else:
            delta = relativedelta(years=qty)
        return reference - (reference - delta)
    raise IBKRHistoricalValidationError(f"Unsupported duration unit '{unit}'")


def _parse_duration(duration_str: str) -> tuple[int, str]:
    m = _DURATION_RE.match(duration_str or "")
    if not m:
        raise IBKRHistoricalValidationError(
            f"Invalid duration_str '{duration_str}'. Expected forms like '10 D', '1 W', '3 M', '1 Y'."
        )
    qty = int(m.group(1))
    unit = m.group(2).upper()
    if qty <= 0:
        raise IBKRHistoricalValidationError("duration_str quantity must be positive")
    return qty, unit


def _validate_duration_for_bar_size(duration_str: str, bar_size: str) -> None:
    qty, unit = _parse_duration(duration_str)
    bar_seconds = _BAR_SIZE_SECONDS[bar_size]

    # Step-size constraints from IBKR docs.
    if unit == "S" and not (1 <= bar_seconds <= 60):
        raise IBKRHistoricalValidationError("Duration unit 'S' only supports bar sizes between 1 sec and 1 min.")
    if unit == "D" and not (5 <= bar_seconds <= 3600):
        raise IBKRHistoricalValidationError("Duration unit 'D' supports bar sizes from 5 secs to 1 hour.")
    if unit == "W" and not (10 <= bar_seconds <= 14400):
        raise IBKRHistoricalValidationError("Duration unit 'W' supports bar sizes from 10 secs to 4 hours.")
    if unit == "M" and not (30 <= bar_seconds <= 28800):
        raise IBKRHistoricalValidationError("Duration unit 'M' supports bar sizes from 30 secs to 8 hours.")
    if unit == "Y" and not (60 <= bar_seconds <= 86400):
        raise IBKRHistoricalValidationError("Duration unit 'Y' supports bar sizes from 1 min to 1 day.")

    # Max duration per unit from the IBKR table.
    if unit == "S":
        sec_cap = 2000 if bar_size == "1 secs" else 86400
        if qty > sec_cap:
            raise IBKRHistoricalValidationError(
                f"duration_str exceeds max {sec_cap} S for bar size '{bar_size}'."
            )
    elif unit == "D" and qty > 365:
        raise IBKRHistoricalValidationError("duration_str exceeds max 365 D.")
    elif unit == "W" and qty > 52:
        raise IBKRHistoricalValidationError("duration_str exceeds max 52 W.")
    elif unit == "M" and qty > 12:
        raise IBKRHistoricalValidationError("duration_str exceeds max 12 M.")
    elif unit == "Y" and qty > 68:
        raise IBKRHistoricalValidationError("duration_str exceeds max 68 Y.")


def _build_request_windows(
    *,
    start_dt: datetime,
    end_dt: datetime,
    bar_size: str,
    explicit_duration: str | None,
    max_requests: int,
) -> list[tuple[datetime, str]]:
    if explicit_duration:
        return [(end_dt, explicit_duration)]

    bar_seconds = _BAR_SIZE_SECONDS[bar_size]
    target_bars_per_request = 1500
    if bar_seconds == 1:
        chunk_duration = "1500 S"
    else:
        chunk_seconds = max(bar_seconds * target_bars_per_request, bar_seconds)
        if chunk_seconds <= 86400:
            chunk_duration = f"{int(chunk_seconds)} S"
        else:
            chunk_days = int(math.ceil(chunk_seconds / 86400))
            if chunk_days <= 365:
                chunk_duration = f"{chunk_days} D"
            else:
                chunk_years = int(math.ceil(chunk_days / 365))
                chunk_duration = f"{chunk_years} Y"
    _validate_duration_for_bar_size(chunk_duration, bar_size)

    windows: list[tuple[datetime, str]] = []
    cursor = end_dt
    while cursor > start_dt and len(windows) < max_requests:
        windows.append((cursor, chunk_duration))
        cursor = cursor - _duration_to_timedelta(chunk_duration, anchor=cursor) - timedelta(seconds=1)
    if not windows:
        windows.append((end_dt, chunk_duration))
    if len(windows) >= max_requests and cursor > start_dt:
        raise IBKRHistoricalValidationError(
            "Requested range is too large for IBKR pacing safeguards. "
            "Narrow the date range or use a larger bar size."
        )
    return windows


def _check_and_record_pacing(*, signature: str, contract_key: str, weight: int) -> None:
    now = time.monotonic()
    with IBKRHistoricalService._pacing_lock:
        entries = IBKRHistoricalService._pacing_entries
        while entries and now - entries[0].ts_monotonic > 600:
            entries.popleft()

        weighted_count = sum(e.weight for e in entries)
        if weighted_count + weight > 60:
            raise IBKRHistoricalPacingError(
                "IBKR pacing guard: more than 60 historical requests within 10 minutes."
            )

        for e in reversed(entries):
            if now - e.ts_monotonic > 15:
                break
            if e.signature == signature:
                raise IBKRHistoricalPacingError(
                    "IBKR pacing guard: identical historical request repeated within 15 seconds."
                )

        same_contract_recent = sum(
            1
            for e in entries
            if e.contract_key == contract_key and now - e.ts_monotonic <= 2
        )
        if same_contract_recent + 1 >= 6:
            raise IBKRHistoricalPacingError(
                "IBKR pacing guard: six or more historical requests for the same contract/exchange/tick-type within 2 seconds."
            )

        entries.append(
            _PacingEntry(
                ts_monotonic=now,
                signature=signature,
                contract_key=contract_key,
                weight=weight,
            )
        )


def _parse_ib_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError):
            return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        if len(raw) == 8:
            try:
                return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=None)
            except ValueError:
                return None
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError):
            return None
    # Handle strings like "20231019 16:11:48 America/New_York" by dropping TZ token.
    if "/" in raw and len(raw.split(" ")) >= 3:
        trimmed = " ".join(raw.split(" ")[:-1])
        parsed = pd.to_datetime(trimmed, errors="coerce")
        if not pd.isna(parsed):
            return parsed.to_pydatetime()
    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _bars_to_frame(bars: Any, vt_symbol: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bar in bars or []:
        ts = _parse_ib_timestamp(getattr(bar, "date", None))
        if ts is None:
            continue
        rows.append(
            {
                "timestamp": ts,
                "vt_symbol": vt_symbol,
                "open": float(getattr(bar, "open", getattr(bar, "open_", 0.0)) or 0.0),
                "high": float(getattr(bar, "high", 0.0) or 0.0),
                "low": float(getattr(bar, "low", 0.0) or 0.0),
                "close": float(getattr(bar, "close", 0.0) or 0.0),
                "volume": float(getattr(bar, "volume", 0.0) or 0.0),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"]
        )
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["timestamp"])
    return df.reset_index(drop=True)
