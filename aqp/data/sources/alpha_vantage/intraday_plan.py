"""Request planning for Alpha Vantage 1-minute intraday backfills."""

from __future__ import annotations

import hashlib
import json
import logging
import calendar
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

from aqp.config import settings
from aqp.core.types import Symbol
from aqp.data.sources.alpha_vantage.bulk_loader import resolve_symbols

logger = logging.getLogger(__name__)

_FUNCTION = "TIME_SERIES_INTRADAY"
_FUNCTION_ID = "timeseries.intraday"
_REQUESTABLE_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,15}$")


@dataclass(frozen=True)
class IntradayRequestComponent:
    component_id: str
    vt_symbol: str
    ticker: str
    exchange: str
    month: str
    interval: str
    function: str = _FUNCTION
    function_id: str = _FUNCTION_ID
    outputsize: str = "full"
    adjusted: bool = True
    extended_hours: bool = True
    entitlement: str | None = None
    status: str = "pending"
    status_reason: str | None = None
    attempts: int = 0
    rows_written: int = 0
    error: str | None = None
    planned_at: str = ""
    completed_at: str | None = None
    source: dict[str, Any] = field(default_factory=dict)

    @property
    def request_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "function": self.function,
            "symbol": self.ticker,
            "interval": self.interval,
            "month": self.month,
            "outputsize": self.outputsize,
            "adjusted": self.adjusted,
            "extended_hours": self.extended_hours,
        }
        if self.entitlement:
            params["entitlement"] = self.entitlement
        return params

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["request_params"] = self.request_params
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntradayRequestComponent":
        data = dict(payload)
        data.pop("request_params", None)
        return cls(**data)

    def with_status(
        self,
        *,
        status: str,
        status_reason: str | None = None,
        rows_written: int | None = None,
        error: str | None = None,
        completed_at: str | None = None,
    ) -> "IntradayRequestComponent":
        return IntradayRequestComponent(
            **{
                **asdict(self),
                "status": status,
                "status_reason": status_reason,
                "attempts": self.attempts + 1,
                "rows_written": self.rows_written if rows_written is None else int(rows_written),
                "error": error,
                "completed_at": completed_at,
            }
        )


@dataclass(frozen=True)
class IntradayBackfillPlan:
    plan_id: str
    generated_at: str
    interval: str
    lookback_months: int
    manifest_path: str
    components: list[IntradayRequestComponent]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "generated_at": self.generated_at,
            "interval": self.interval,
            "lookback_months": int(self.lookback_months),
            "manifest_path": self.manifest_path,
            "component_count": len(self.components),
            "symbol_count": len({component.vt_symbol for component in self.components}),
            "months": sorted({component.month for component in self.components}),
            "components": [component.to_dict() for component in self.components],
        }


@dataclass(frozen=True)
class IntradayDeltaState:
    vt_symbol: str
    interval: str
    latest_timestamp: str | None = None


def default_manifest_dir() -> Path:
    return Path(settings.alpha_vantage_intraday_manifest_dir).expanduser()


def month_window(*, lookback_months: int, anchor: date | None = None) -> list[str]:
    """Return `YYYY-MM` months ending with the anchor month."""

    if lookback_months <= 0:
        return []
    current = anchor or datetime.now(UTC).date()
    year = current.year
    month = current.month
    months: list[str] = []
    for offset in range(lookback_months - 1, -1, -1):
        total = year * 12 + month - 1 - offset
        y, m0 = divmod(total, 12)
        months.append(f"{y:04d}-{m0 + 1:02d}")
    return months


def is_requestable_intraday_ticker(ticker: str) -> bool:
    raw = str(ticker or "").strip().upper()
    if not raw or raw in {"N/A", "NULL", "NONE"}:
        return False
    return bool(_REQUESTABLE_TICKER_RE.fullmatch(raw))


def build_intraday_plan(
    *,
    symbols: Iterable[str] | str = "all_active",
    filters: dict[str, Any] | None = None,
    limit: int | None = None,
    interval: str | None = None,
    lookback_months: int | None = None,
    manifest_dir: str | Path | None = None,
    anchor: date | None = None,
    entitlement: str | None = None,
    use_delta_state: bool = True,
) -> IntradayBackfillPlan:
    """Build and persist reusable request components for intraday history."""

    effective_interval = interval or settings.alpha_vantage_intraday_interval or "1min"
    months = month_window(
        lookback_months=int(lookback_months or settings.alpha_vantage_intraday_lookback_months),
        anchor=anchor,
    )
    generated_at = datetime.now(UTC).isoformat()
    symbol_list = resolve_symbols(symbols, filters=filters, limit=limit)
    components: list[IntradayRequestComponent] = []
    for raw_vt_symbol in symbol_list:
        sym = Symbol.parse(raw_vt_symbol)
        for month in months:
            component_id = _component_id(sym.vt_symbol, effective_interval, month)
            requestable = is_requestable_intraday_ticker(sym.ticker)
            components.append(
                IntradayRequestComponent(
                    component_id=component_id,
                    vt_symbol=sym.vt_symbol,
                    ticker=sym.ticker,
                    exchange=sym.exchange.value if hasattr(sym.exchange, "value") else str(sym.exchange),
                    month=month,
                    interval=effective_interval,
                    entitlement=entitlement,
                    status="pending" if requestable else "skipped",
                    status_reason=None if requestable else "unsupported_intraday_ticker",
                    planned_at=generated_at,
                    source={
                        "provider": "alpha_vantage",
                        "function": _FUNCTION,
                        "function_id": _FUNCTION_ID,
                        "interval": effective_interval,
                        "month": month,
                        "generated_at": generated_at,
                    },
                )
            )
    plan_id = _plan_id(generated_at, symbol_list, months, effective_interval)
    target_dir = Path(manifest_dir).expanduser() if manifest_dir else default_manifest_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    state = load_delta_state(delta_state_path(effective_interval, target_dir)) if use_delta_state else {}
    manifest_path = target_dir / f"{plan_id}.jsonl"
    components = [
        _apply_delta_skip(component, state)
        for component in components
    ]
    write_components(manifest_path, components)
    return IntradayBackfillPlan(
        plan_id=plan_id,
        generated_at=generated_at,
        interval=effective_interval,
        lookback_months=len(months),
        manifest_path=str(manifest_path),
        components=components,
    )


def write_components(path: str | Path, components: Iterable[IntradayRequestComponent]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for component in components:
            handle.write(json.dumps(component.to_dict(), sort_keys=True, default=str) + "\n")
    tmp.replace(target)
    return target


def delta_state_path(interval: str, manifest_dir: str | Path | None = None) -> Path:
    root = Path(manifest_dir).expanduser() if manifest_dir else default_manifest_dir()
    return root / f"delta_state_{interval}.json"


def load_delta_state(path: str | Path) -> dict[str, IntradayDeltaState]:
    source = Path(path).expanduser()
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to read intraday delta state from %s", source, exc_info=True)
        return {}
    out: dict[str, IntradayDeltaState] = {}
    for vt_symbol, item in dict(payload).items():
        if isinstance(item, dict):
            out[str(vt_symbol)] = IntradayDeltaState(
                vt_symbol=str(vt_symbol),
                interval=str(item.get("interval") or ""),
                latest_timestamp=item.get("latest_timestamp"),
            )
    return out


def save_delta_state(path: str | Path, state: dict[str, IntradayDeltaState]) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: asdict(value) for key, value in sorted(state.items())}
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(target)
    return target


def read_components(path: str | Path) -> list[IntradayRequestComponent]:
    source = Path(path).expanduser()
    if not source.exists():
        return []
    out: list[IntradayRequestComponent] = []
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                out.append(IntradayRequestComponent.from_dict(json.loads(text)))
    return out


def update_component_status(
    path: str | Path,
    component_id: str,
    *,
    status: str,
    status_reason: str | None = None,
    rows_written: int | None = None,
    error: str | None = None,
) -> IntradayRequestComponent | None:
    components = read_components(path)
    updated: IntradayRequestComponent | None = None
    next_components: list[IntradayRequestComponent] = []
    for component in components:
        if component.component_id == component_id:
            updated = component.with_status(
                status=status,
                status_reason=status_reason,
                rows_written=rows_written,
                error=error,
                completed_at=datetime.now(UTC).isoformat() if status in {"completed", "failed", "skipped"} else None,
            )
            next_components.append(updated)
        else:
            next_components.append(component)
    write_components(path, next_components)
    return updated


def _component_id(vt_symbol: str, interval: str, month: str) -> str:
    digest = hashlib.sha256(f"{vt_symbol}|{interval}|{month}".encode()).hexdigest()[:16]
    return f"av-intraday-{digest}"


def _apply_delta_skip(
    component: IntradayRequestComponent,
    state: dict[str, IntradayDeltaState],
) -> IntradayRequestComponent:
    current = state.get(component.vt_symbol)
    if not current or not current.latest_timestamp:
        return component
    try:
        latest = datetime.fromisoformat(str(current.latest_timestamp).replace("Z", "+00:00"))
    except ValueError:
        return component
    year, month = [int(part) for part in component.month.split("-", 1)]
    last_day = calendar.monthrange(year, month)[1]
    month_end = datetime(year, month, last_day, 23, 59, 59)
    if latest.replace(tzinfo=None) >= month_end:
        return IntradayRequestComponent(
            **{
                **asdict(component),
                "status": "skipped",
                "status_reason": "covered_by_delta_state",
            }
        )
    return component


def _plan_id(generated_at: str, symbols: list[str], months: list[str], interval: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "generated_at": generated_at,
                "symbols": symbols,
                "months": months,
                "interval": interval,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:12]
    return f"av-intraday-{digest}"


__all__ = [
    "IntradayBackfillPlan",
    "IntradayDeltaState",
    "IntradayRequestComponent",
    "build_intraday_plan",
    "delta_state_path",
    "default_manifest_dir",
    "is_requestable_intraday_ticker",
    "load_delta_state",
    "month_window",
    "read_components",
    "save_delta_state",
    "update_component_status",
    "write_components",
]
