"""Typed helpers for the ``/data/security/*`` and historical endpoints.

Every helper:

- catches ``httpx.HTTPStatusError`` and repackages the structured body
  (``{detail, code, hint}``) into a :class:`SecurityError` the UI can
  render with a single ``solara.Error`` card;
- normalises vt_symbols (``AAPL`` → ``AAPL.NASDAQ``) so callers can be
  lazy with user input;
- returns the raw dict, not a Pydantic model — the UI consumes JSON
  anyway and keeping it loose avoids a compile-time dependency on the
  API schemas package.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pandas as pd

from aqp.ui.api_client import get as api_get
from aqp.ui.api_client import post as api_post


@dataclass(frozen=True)
class SecurityError(Exception):
    """Structured failure raised from the security service helpers."""

    status: int
    code: str
    detail: str
    hint: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        parts = [f"[{self.status} {self.code}] {self.detail}"]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        return " — ".join(parts)


@dataclass(frozen=True)
class IBKRAvailability:
    ok: bool
    message: str
    host: str = ""
    port: int = 0


def _normalise_vt(symbol: str) -> str:
    raw = (symbol or "").strip().upper()
    if not raw:
        raise SecurityError(
            status=400,
            code="missing_symbol",
            detail="Please enter a ticker.",
            hint="Try AAPL, SPY or NVDA.",
        )
    return raw if "." in raw else f"{raw}.NASDAQ"


def _reraise(exc: httpx.HTTPStatusError) -> SecurityError:
    """Translate an HTTPX error into our structured :class:`SecurityError`."""
    status = exc.response.status_code
    try:
        body = exc.response.json()
    except (ValueError, TypeError):
        return SecurityError(status=status, code="http_error", detail=str(exc))
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return SecurityError(
            status=status,
            code=str(detail.get("code") or "http_error"),
            detail=str(detail.get("detail") or exc),
            hint=str(detail.get("hint") or ""),
        )
    if isinstance(detail, str):
        return SecurityError(status=status, code="http_error", detail=detail)
    return SecurityError(status=status, code="http_error", detail=str(exc))


def _http_error_message(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    detail = ""
    try:
        body = exc.response.json()
    except (ValueError, TypeError):
        body = None
    if isinstance(body, dict):
        nested = body.get("detail")
        if isinstance(nested, dict):
            detail = str(nested.get("detail") or nested.get("message") or nested.get("code") or "")
        elif isinstance(nested, str):
            detail = nested
        elif isinstance(body.get("error"), str):
            detail = str(body["error"])
        elif isinstance(body.get("message"), str):
            detail = str(body["message"])
    if detail:
        return f"HTTP {status}: {detail}"
    reason = exc.response.reason_phrase or "Request failed"
    return f"HTTP {status}: {reason}"


def _parse_endpoint(endpoint: str) -> tuple[str, int]:
    raw = (endpoint or "").strip()
    if not raw:
        return "", 0
    if ":" not in raw:
        return raw, 0
    host, _, port_raw = raw.rpartition(":")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 0
    return host or raw, port


def _availability_from_broker_status(payload: dict[str, Any]) -> IBKRAvailability:
    ok = bool(payload.get("ok"))
    message = str(payload.get("error") or payload.get("message") or "")
    if not message:
        stage = str(payload.get("stage") or "unknown")
        message = "IBKR broker status is healthy." if ok else f"IBKR broker status: {stage}"
    host, port = _parse_endpoint(str(payload.get("endpoint") or ""))
    return IBKRAvailability(ok=ok, message=message, host=host, port=port)


def _call_get(path: str, **params: Any) -> dict[str, Any]:
    try:
        return api_get(path, params=params or None)
    except httpx.HTTPStatusError as exc:
        raise _reraise(exc) from exc
    except httpx.HTTPError as exc:  # network-level failure
        raise SecurityError(
            status=0,
            code="network_error",
            detail=str(exc),
            hint="Check the API is reachable.",
        ) from exc


def _call_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return api_post(path, json=body)
    except httpx.HTTPStatusError as exc:
        raise _reraise(exc) from exc
    except httpx.HTTPError as exc:
        raise SecurityError(
            status=0,
            code="network_error",
            detail=str(exc),
            hint="Check the API is reachable.",
        ) from exc


# ---------------------------------------------------------------------------
# Per-facet helpers
# ---------------------------------------------------------------------------


def get_fundamentals(symbol: str) -> dict[str, Any]:
    return _call_get(f"/data/security/{_normalise_vt(symbol)}/fundamentals")


def get_news(symbol: str, limit: int = 20) -> dict[str, Any]:
    return _call_get(f"/data/security/{_normalise_vt(symbol)}/news", limit=limit)


def get_calendar(symbol: str) -> dict[str, Any]:
    return _call_get(f"/data/security/{_normalise_vt(symbol)}/calendar")


def get_corporate(symbol: str) -> dict[str, Any]:
    return _call_get(f"/data/security/{_normalise_vt(symbol)}/corporate")


def get_quote(symbol: str) -> dict[str, Any]:
    return _call_get(f"/data/security/{_normalise_vt(symbol)}/quote")


def get_ibkr_availability(refresh: bool = False) -> IBKRAvailability:
    try:
        payload = api_get(
            "/data/ibkr/historical/availability",
            params={"refresh": "true"} if refresh else None,
        )
    except httpx.HTTPStatusError as exc:
        # Backward-compat fallback for environments still exposing only the
        # broker playground status endpoint.
        if exc.response.status_code == 404:
            try:
                broker_payload = api_get("/brokers/ibkr/status")
            except httpx.HTTPStatusError as broker_exc:
                return IBKRAvailability(ok=False, message=_http_error_message(broker_exc))
            except httpx.RequestError:
                return IBKRAvailability(ok=False, message="API unreachable")
            if not isinstance(broker_payload, dict):
                return IBKRAvailability(ok=False, message="Malformed broker status response")
            return _availability_from_broker_status(broker_payload)
        return IBKRAvailability(ok=False, message=_http_error_message(exc))
    except httpx.RequestError:
        return IBKRAvailability(ok=False, message="API unreachable")
    except httpx.HTTPError as exc:
        return IBKRAvailability(ok=False, message=str(exc) or "API error")
    if not isinstance(payload, dict):
        return IBKRAvailability(ok=False, message="Malformed availability response")
    return IBKRAvailability(
        ok=bool(payload.get("ok")),
        message=str(payload.get("message") or ""),
        host=str(payload.get("host") or ""),
        port=int(payload.get("port") or 0),
    )


# ---------------------------------------------------------------------------
# Historical bars — unified entry point
# ---------------------------------------------------------------------------


def get_historical_bars(
    *,
    symbol: str,
    venue: str,
    start: str | None = None,
    end: str | None = None,
    bar_size: str = "1 day",
    what_to_show: str = "TRADES",
    use_rth: bool = True,
    limit: int = 5000,
) -> pd.DataFrame:
    """Return tidy OHLCV bars from the appropriate backend for ``venue``.

    ``venue`` is one of ``ibkr``, ``duckdb`` (default for anything else).
    Returns an empty DataFrame on no data — raises :class:`SecurityError`
    on transport / upstream failures.
    """
    vt = _normalise_vt(symbol)
    if venue == "ibkr":
        body: dict[str, Any] = {
            "vt_symbol": vt,
            "bar_size": bar_size,
            "what_to_show": what_to_show,
            "use_rth": use_rth,
            "rows": int(limit),
        }
        if start:
            body["start"] = start
        if end:
            body["end"] = end
        if not start and not end:
            body["duration_str"] = "30 D"
        payload = _call_post("/data/ibkr/historical/fetch", body)
    else:
        params: dict[str, Any] = {"interval": _interval_from_bar_size(bar_size), "limit": int(limit)}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        payload = _call_get(f"/data/{vt}/bars", **params)

    bars = payload.get("bars") or []
    if not bars:
        return pd.DataFrame(columns=["timestamp", "vt_symbol", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(bars)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def _interval_from_bar_size(bar_size: str) -> str:
    mapping = {
        "1 min": "1m",
        "5 mins": "5m",
        "15 mins": "15m",
        "30 mins": "30m",
        "1 hour": "1h",
        "1 day": "1d",
        "1d": "1d",
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
    }
    return mapping.get(bar_size.strip().lower(), "1d")
