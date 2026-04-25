"""Exchange trading hours and holiday calendars (Lean ``MarketHoursDatabase``).

Lightweight JSON-driven model good enough for US equities and crypto.
Each entry describes:

- ``timezone`` — IANA zone name for the venue's local clock
- ``sessions`` — weekday (0 = Mon, 6 = Sun) → ``(open_local, close_local)``
  in ``HH:MM`` format; ``None`` on a weekday means the market is closed
- ``holidays`` — list of ISO date strings when the market is closed
- ``early_closes`` — optional override map of ``date -> close_hhmm``

``MarketHoursDatabase`` loads the bundled ``market_hours.json`` at
:mod:`aqp.core.data`; callers can point at a custom file for other
regions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python < 3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ExchangeHours:
    """Trading hours for a single exchange + security-type combination."""

    exchange: str
    timezone: str
    sessions: dict[int, tuple[str, str] | None] = field(default_factory=dict)
    holidays: set[date] = field(default_factory=set)
    early_closes: dict[date, str] = field(default_factory=dict)

    def is_open(self, utc_dt: datetime) -> bool:
        """``True`` when the market is open at this UTC timestamp."""
        local = self._to_local(utc_dt)
        local_date = local.date()
        if local_date in self.holidays:
            return False
        session = self.sessions.get(local.weekday())
        if session is None:
            return False
        open_str, close_str = session
        if local_date in self.early_closes:
            close_str = self.early_closes[local_date]
        open_t = _parse_hhmm(open_str)
        close_t = _parse_hhmm(close_str)
        return open_t <= local.time() < close_t

    def next_open(self, utc_dt: datetime, days_ahead: int = 14) -> datetime | None:
        """Return the next UTC timestamp at which the market opens."""
        local = self._to_local(utc_dt)
        for i in range(days_ahead):
            candidate = local + timedelta(days=i)
            if candidate.date() in self.holidays:
                continue
            session = self.sessions.get(candidate.weekday())
            if session is None:
                continue
            open_t = _parse_hhmm(session[0])
            local_open = datetime.combine(candidate.date(), open_t)
            if ZoneInfo:
                local_open = local_open.replace(tzinfo=ZoneInfo(self.timezone))
            if local_open > local:
                return local_open.astimezone(UTC)
        return None

    def _to_local(self, utc_dt: datetime) -> datetime:
        if ZoneInfo is None:
            return utc_dt
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=UTC)
        return utc_dt.astimezone(ZoneInfo(self.timezone))


def _parse_hhmm(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


DEFAULT_DB_PATH = Path(__file__).parent / "data" / "market_hours.json"


def _default_payload() -> dict[str, Any]:
    """Fallback payload used when the bundled JSON is missing."""
    us_equities = {
        "timezone": "America/New_York",
        "sessions": {
            "0": ["09:30", "16:00"],
            "1": ["09:30", "16:00"],
            "2": ["09:30", "16:00"],
            "3": ["09:30", "16:00"],
            "4": ["09:30", "16:00"],
            "5": None,
            "6": None,
        },
        "holidays": [
            "2026-01-01",
            "2026-01-19",
            "2026-02-16",
            "2026-04-03",
            "2026-05-25",
            "2026-06-19",
            "2026-07-03",
            "2026-09-07",
            "2026-11-26",
            "2026-12-25",
        ],
        "early_closes": {},
    }
    crypto_247 = {
        "timezone": "UTC",
        "sessions": {str(i): ["00:00", "23:59"] for i in range(7)},
        "holidays": [],
        "early_closes": {},
    }
    return {
        "NASDAQ": us_equities,
        "NYSE": us_equities,
        "ARCA": us_equities,
        "BATS": us_equities,
        "LOCAL": crypto_247,
        "BINANCE": crypto_247,
        "COINBASE": crypto_247,
        "SIM": crypto_247,
    }


class MarketHoursDatabase:
    """Exchange-hours lookup. Backed by a JSON file or an in-memory dict."""

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        raw = payload if payload is not None else self._load_default()
        self._hours: dict[str, ExchangeHours] = {}
        for exchange, spec in raw.items():
            self._hours[exchange.upper()] = self._parse_spec(exchange, spec)

    @classmethod
    def from_json(cls, path: str | Path) -> MarketHoursDatabase:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data)

    @staticmethod
    def _load_default() -> dict[str, Any]:
        try:
            return json.loads(DEFAULT_DB_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return _default_payload()

    @staticmethod
    def _parse_spec(exchange: str, spec: dict[str, Any]) -> ExchangeHours:
        sessions: dict[int, tuple[str, str] | None] = {}
        for day_key, window in (spec.get("sessions") or {}).items():
            day = int(day_key)
            if window is None:
                sessions[day] = None
            else:
                sessions[day] = (str(window[0]), str(window[1]))
        holidays = {date.fromisoformat(d) for d in (spec.get("holidays") or [])}
        early_closes = {
            date.fromisoformat(k): str(v)
            for k, v in (spec.get("early_closes") or {}).items()
        }
        return ExchangeHours(
            exchange=exchange.upper(),
            timezone=spec.get("timezone", "UTC"),
            sessions=sessions,
            holidays=holidays,
            early_closes=early_closes,
        )

    # -- lookup ------------------------------------------------------------

    def get(self, exchange: str) -> ExchangeHours | None:
        return self._hours.get(exchange.upper())

    def __contains__(self, exchange: str) -> bool:
        return exchange.upper() in self._hours

    def __iter__(self):
        return iter(self._hours)

    def is_open(self, exchange: str, utc_dt: datetime) -> bool:
        hours = self.get(exchange)
        return bool(hours and hours.is_open(utc_dt))

    def next_open(self, exchange: str, utc_dt: datetime) -> datetime | None:
        hours = self.get(exchange)
        return hours.next_open(utc_dt) if hours else None


def default_database() -> MarketHoursDatabase:
    """Process-wide default. Cached on first call via module globals."""
    global _DEFAULT_DB
    if "_DEFAULT_DB" not in globals():
        globals()["_DEFAULT_DB"] = MarketHoursDatabase()
    return globals()["_DEFAULT_DB"]
