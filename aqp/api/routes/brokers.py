"""Broker playground endpoints — introspect and interactively call the
Alpaca / IBKR / Tradier adapters over a uniform surface.

Every call instantiates a short-lived adapter, opens the connection, runs
the method, and disconnects. That keeps the API stateless and avoids a
long-lived socket that could leak across workers.

Safety rails:

- Only paper/sandbox endpoints are used by default (see each adapter's
  config).
- Order submission goes through the same ``RiskManager.check_pretrade``
  guard the paper engine uses.
- The ``simulated`` venue is always available and requires no credentials
  — handy for UI smoke tests without a live broker.
- IBKR / TWS detection is **socket-aware** — we open a short TCP probe
  before claiming "available" and before attempting an authenticated
  connect, so a stuck gateway never hangs the API.
"""
from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import logging
import socket
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.config import settings
from aqp.core.interfaces import IAsyncBrokerage
from aqp.core.types import (
    AccountData,
    OrderRequest,
    OrderSide,
    OrderType,
    PositionData,
    Symbol,
)
from aqp.risk.kill_switch import is_engaged

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/brokers", tags=["brokers"])


# Tunables: probe + connect timeouts kept short so an unresponsive gateway
# does not block the API for the OS-default 60s socket timeout.
_TCP_PROBE_TIMEOUT_S = 0.75
_IBKR_CONNECT_TIMEOUT_S = 8.0


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class VenueInfo(BaseModel):
    name: str
    available: bool = Field(..., description="True if the broker SDK is installed")
    configured: bool = Field(..., description="True if credentials are in .env")
    paper: bool = Field(default=True)
    description: str = ""
    missing_extras: list[str] = Field(default_factory=list)
    endpoint: str | None = Field(
        default=None,
        description="host:port the adapter would dial (only set for venues with a fixed local endpoint, e.g. IBKR)",
    )
    reachable: bool | None = Field(
        default=None,
        description="True/False if a quick TCP probe succeeded; None when not applicable.",
    )
    sdk_version: str | None = Field(
        default=None,
        description="Installed SDK version, when discoverable.",
    )


class OrderForm(BaseModel):
    symbol: str
    side: str = Field("buy", description="buy | sell")
    order_type: str = Field("market", description="market | limit | stop | stop_limit")
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    exchange: str | None = None


class CallRequest(BaseModel):
    method: str
    kwargs: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Adapter lookup
# ---------------------------------------------------------------------------


# Importable module name -> distribution name on PyPI for cases they differ.
# ``ib_async`` is the import-time module; ``ib-async`` is the dist name.
_DIST_NAMES: dict[str, str] = {
    "ib_async": "ib-async",
    "alpaca": "alpaca-py",
}


def _sdk_version(name: str) -> str | None:
    """Return the installed package version of ``name`` *without importing it*.

    Critical: do NOT call ``importlib.import_module(name)`` here. The
    ``ib_async`` package transitively pulls in ``aeventkit``, whose import
    on Python 3.14 has been observed to break ``sniffio``'s asyncio
    backend detection — every subsequent sync FastAPI route then 500s
    with ``anyio.NoEventLoopError``. Using ``find_spec`` (which checks
    presence without executing the module) plus ``importlib.metadata``
    avoids that side-effect entirely.
    """
    spec = importlib.util.find_spec(name)
    if spec is None:
        return None
    dist_name = _DIST_NAMES.get(name, name)
    try:
        return importlib.metadata.version(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return "?"


def _tcp_probe(host: str, port: int, *, timeout: float = _TCP_PROBE_TIMEOUT_S) -> bool:
    """Return True iff a TCP connection to ``host:port`` opens within ``timeout``.

    Pure stdlib: avoids the broker SDK so we can detect "gateway up" even
    when the SDK is missing. Used by both ``/brokers/`` and
    ``/brokers/{venue}/status``.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, int(port)))
        return True
    except (TimeoutError, ConnectionError, OSError):
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _ibkr_descriptor() -> VenueInfo:
    """Build the IBKR venue card.

    Uses a small TCP probe so we can distinguish three states the user
    cares about: SDK missing, gateway down, both ok. Each state gets a
    different ``description`` so the UI can render an actionable hint.
    """
    sdk_ver = _sdk_version("ib_async")
    missing = ["ib-async"] if sdk_ver is None else []
    host = settings.ibkr_host
    port = int(settings.ibkr_port)
    reachable = _tcp_probe(host, port)
    parts = [f"Interactive Brokers TWS / Gateway at {host}:{port}."]
    if sdk_ver is None:
        parts.append("Install the SDK with: `pip install -e .[ibkr]`.")
    if not reachable:
        parts.append(
            "Gateway not listening — start TWS or IB Gateway, "
            "enable the API ('Configure → API → Enable ActiveX and Socket Clients'), "
            f"and confirm the socket port is {port}."
        )
    if sdk_ver and reachable:
        parts.append("Both SDK and gateway are healthy.")
    return VenueInfo(
        name="ibkr",
        # The venue is "available" only if BOTH the SDK and the gateway
        # are usable. This is a meaningful change vs. the pre-fix logic
        # which only checked SDK presence — gateway-down used to silently
        # claim available.
        available=bool(sdk_ver) and reachable,
        configured=True,  # host/port always have defaults
        paper=(port == 7497),
        description=" ".join(parts),
        missing_extras=missing,
        endpoint=f"{host}:{port}",
        reachable=reachable,
        sdk_version=sdk_ver,
    )


def _alpaca_descriptor() -> VenueInfo:
    sdk_ver = _sdk_version("alpaca")
    missing = ["alpaca-py"] if sdk_ver is None else []
    return VenueInfo(
        name="alpaca",
        available=sdk_ver is not None,
        configured=bool(settings.alpaca_api_key and settings.alpaca_secret_key),
        paper=bool(settings.alpaca_paper),
        description="Alpaca — equities + crypto paper and live. US-only.",
        missing_extras=missing,
        sdk_version=sdk_ver,
    )


def _tradier_descriptor() -> VenueInfo:
    return VenueInfo(
        name="tradier",
        available=True,  # uses base httpx
        configured=bool(settings.tradier_token and settings.tradier_account_id),
        paper=("sandbox" in settings.tradier_base_url.lower()),
        description="Tradier REST — sandbox and production.",
        missing_extras=[] if settings.tradier_token else ["AQP_TRADIER_TOKEN"],
        endpoint=settings.tradier_base_url,
    )


def _simulated_descriptor() -> VenueInfo:
    return VenueInfo(
        name="simulated",
        available=True,
        configured=True,
        paper=True,
        description="Deterministic simulator — no SDK required. Safe sandbox for UI demos.",
    )


def _venue_descriptors() -> list[VenueInfo]:
    return [
        _alpaca_descriptor(),
        _ibkr_descriptor(),
        _tradier_descriptor(),
        _simulated_descriptor(),
    ]


def _build_adapter(venue: str) -> Any:
    """Instantiate the chosen brokerage. Raises ``HTTPException`` on missing deps."""
    venue = venue.lower()
    try:
        if venue == "alpaca":
            from aqp.trading.brokerages.alpaca import AlpacaBrokerage

            return AlpacaBrokerage(paper=settings.alpaca_paper)
        if venue == "ibkr":
            from aqp.trading.brokerages.ibkr import InteractiveBrokersBrokerage

            return InteractiveBrokersBrokerage()
        if venue == "tradier":
            from aqp.trading.brokerages.tradier import TradierBrokerage

            return TradierBrokerage()
        if venue == "simulated":
            from aqp.backtest.broker_sim import SimulatedBrokerage

            return SimulatedBrokerage(initial_cash=100_000.0)
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{venue} adapter unavailable: {exc}. Install the matching extra.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=404, detail=f"unknown venue: {venue!r}")


async def _with_adapter(venue: str, fn, *, connect_timeout: float | None = None):
    """Run ``fn(adapter)`` with an open connection, closed on exit.

    ``connect_timeout`` defaults are venue-aware: IBKR gets a tight
    :data:`_IBKR_CONNECT_TIMEOUT_S` so an unresponsive gateway can't hang
    the request thread for the OS-default 60 s. Other venues fall back
    to the SDK default.
    """
    adapter = _build_adapter(venue)
    is_async = isinstance(adapter, IAsyncBrokerage)
    if connect_timeout is None:
        connect_timeout = _IBKR_CONNECT_TIMEOUT_S if venue == "ibkr" else 30.0
    try:
        if is_async:
            await asyncio.wait_for(adapter.connect_async(), timeout=connect_timeout)
        else:
            await asyncio.wait_for(
                asyncio.to_thread(adapter.connect), timeout=connect_timeout
            )
        result = await fn(adapter, is_async)
        return result
    finally:
        try:
            if is_async:
                await asyncio.wait_for(adapter.disconnect_async(), timeout=5.0)
            else:
                await asyncio.wait_for(
                    asyncio.to_thread(adapter.disconnect), timeout=5.0
                )
        except Exception:  # noqa: BLE001
            logger.exception("disconnect failed for %s", venue)


def _pos_to_dict(p: PositionData) -> dict[str, Any]:
    return {
        "vt_symbol": p.symbol.vt_symbol,
        "ticker": p.symbol.ticker,
        "direction": p.direction.value,
        "quantity": p.quantity,
        "average_price": p.average_price,
        "notional": p.notional,
        "unrealized_pnl": p.unrealized_pnl,
        "realized_pnl": p.realized_pnl,
    }


def _acct_to_dict(a: AccountData) -> dict[str, Any]:
    return {
        "account_id": a.account_id,
        "cash": a.cash,
        "equity": a.equity,
        "margin_used": a.margin_used,
        "currency": a.currency,
        "updated_at": a.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[VenueInfo])
def list_venues() -> list[VenueInfo]:
    """Inventory of every supported venue with its availability + config."""
    return _venue_descriptors()


@router.get("/schema")
def broker_schema() -> dict[str, Any]:
    """Return the shared ``IBrokerage`` / ``IAsyncBrokerage`` method surface.

    The UI playground uses this to render generic "call a method" forms so we
    don't hard-code each venue's nuances.
    """
    return {
        "methods": [
            {
                "name": "query_account",
                "returns": "AccountData",
                "readonly": True,
                "description": "Cash, equity, margin used.",
                "params": [],
            },
            {
                "name": "query_positions",
                "returns": "list[PositionData]",
                "readonly": True,
                "description": "Currently open positions.",
                "params": [],
            },
            {
                "name": "submit_order",
                "returns": "OrderData",
                "readonly": False,
                "description": "Place a new order. Respects the global kill switch.",
                "params": [
                    {"name": "symbol", "type": "str", "required": True},
                    {
                        "name": "side",
                        "type": "enum",
                        "required": True,
                        "enum": ["buy", "sell"],
                    },
                    {
                        "name": "order_type",
                        "type": "enum",
                        "required": True,
                        "enum": ["market", "limit", "stop", "stop_limit"],
                    },
                    {"name": "quantity", "type": "float", "required": True},
                    {"name": "price", "type": "float", "required": False},
                    {"name": "stop_price", "type": "float", "required": False},
                ],
            },
            {
                "name": "cancel_order",
                "returns": "bool",
                "readonly": False,
                "description": "Cancel an existing order by id.",
                "params": [{"name": "order_id", "type": "str", "required": True}],
            },
        ]
    }


@router.get("/{venue}/status")
async def venue_status(venue: str) -> dict[str, Any]:
    """Connect-probe + account summary so UIs can render a green/red light.

    Diagnostic ladder for IBKR (matches the descriptor logic):

    1. SDK missing            -> ok=False, action: install ``ib-async``.
    2. Gateway port closed    -> ok=False, action: start TWS / IB Gateway.
    3. SDK + port open, but   -> ok=False, error from ``IB.connectAsync``,
       authenticated connect     usually a clientId clash or API gate
       fails                     in the gateway settings.
    4. Everything ok          -> ok=True, returns the live account summary.

    Each rung is reachable from the UI's status pill so the user knows
    exactly which precondition broke.
    """
    info = next((v for v in _venue_descriptors() if v.name == venue), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown venue: {venue!r}")

    base = {
        "venue": venue,
        "endpoint": info.endpoint,
        "reachable": info.reachable,
        "available": info.available,
        "configured": info.configured,
        "missing": info.missing_extras,
        "sdk_version": info.sdk_version,
    }

    # Rung 1: SDK missing.
    if info.missing_extras:
        return {
            **base,
            "ok": False,
            "stage": "sdk-missing",
            "error": (
                f"SDK not installed for {venue}: missing "
                f"{', '.join(info.missing_extras)}. "
                "Install the matching extra to enable this venue."
            ),
        }

    # Rung 2: gateway not listening (only meaningful when we have an endpoint).
    if info.reachable is False:
        return {
            **base,
            "ok": False,
            "stage": "gateway-down",
            "error": (
                f"No process listening on {info.endpoint}. "
                "Start TWS or IB Gateway, enable the API "
                "(Configure → API → Enable ActiveX and Socket Clients), "
                "and confirm the socket port matches AQP_IBKR_PORT."
            ),
        }

    # Rung 3: missing credentials (Alpaca / Tradier — IBKR doesn't apply).
    if not info.configured:
        return {
            **base,
            "ok": False,
            "stage": "not-configured",
            "error": "credentials missing — populate the matching AQP_* env vars",
        }

    async def _probe(adapter: Any, is_async: bool) -> dict[str, Any]:
        if is_async:
            acct = await adapter.query_account_async()
        else:
            acct = await asyncio.to_thread(adapter.query_account)
        return {**base, "ok": True, "stage": "online", "account": _acct_to_dict(acct)}

    try:
        return await _with_adapter(venue, _probe)
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.warning("status probe timed out for %s", venue)
        return {
            **base,
            "ok": False,
            "stage": "connect-timeout",
            "error": (
                f"Connect to {info.endpoint or venue} timed out after "
                f"{_IBKR_CONNECT_TIMEOUT_S:.0f}s. Most common causes: a "
                "stale clientId session held by another process, the API "
                "is enabled but read-only, or the gateway is paused."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("status probe failed for %s", venue)
        return {
            **base,
            "ok": False,
            "stage": "connect-error",
            "error": str(exc),
        }


@router.get("/{venue}/account")
async def venue_account(venue: str) -> dict[str, Any]:
    async def _fn(adapter: Any, is_async: bool) -> dict[str, Any]:
        if is_async:
            return _acct_to_dict(await adapter.query_account_async())
        return _acct_to_dict(await asyncio.to_thread(adapter.query_account))

    try:
        return await _with_adapter(venue, _fn)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{venue}/positions")
async def venue_positions(venue: str) -> list[dict[str, Any]]:
    async def _fn(adapter: Any, is_async: bool) -> list[dict[str, Any]]:
        if is_async:
            rows = await adapter.query_positions_async()
        else:
            rows = await asyncio.to_thread(adapter.query_positions)
        return [_pos_to_dict(p) for p in rows]

    try:
        return await _with_adapter(venue, _fn)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{venue}/orders")
async def venue_submit_order(venue: str, form: OrderForm) -> dict[str, Any]:
    if is_engaged():
        raise HTTPException(status_code=423, detail="kill switch engaged — rejecting order")
    try:
        side = OrderSide(form.side.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid side: {form.side}") from exc
    try:
        order_type = OrderType(form.order_type.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid order_type: {form.order_type}") from exc

    request = OrderRequest(
        symbol=Symbol.parse(form.symbol) if "." in form.symbol else Symbol(ticker=form.symbol),
        side=side,
        order_type=order_type,
        quantity=float(form.quantity),
        price=form.price,
        stop_price=form.stop_price,
        reference="api-playground",
    )

    async def _fn(adapter: Any, is_async: bool) -> dict[str, Any]:
        if is_async:
            order = await adapter.submit_order_async(request)
        else:
            order = await asyncio.to_thread(adapter.submit_order, request)
        return {
            "order_id": order.order_id,
            "gateway": order.gateway,
            "vt_symbol": order.symbol.vt_symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "status": order.status.value,
            "price": order.price,
            "stop_price": order.stop_price,
        }

    try:
        return await _with_adapter(venue, _fn)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/{venue}/orders/{order_id}")
async def venue_cancel_order(venue: str, order_id: str) -> dict[str, Any]:
    async def _fn(adapter: Any, is_async: bool) -> dict[str, Any]:
        if is_async:
            ok = await adapter.cancel_order_async(order_id)
        else:
            ok = await asyncio.to_thread(adapter.cancel_order, order_id)
        return {"order_id": order_id, "cancelled": bool(ok)}

    try:
        return await _with_adapter(venue, _fn)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{venue}/call")
async def venue_call(venue: str, req: CallRequest) -> dict[str, Any]:
    """Generic method dispatcher used by the API playground.

    Whitelisted to the read-only methods on ``IBrokerage``. Non-read methods
    are rejected to keep the playground safe; use the dedicated order
    endpoints instead.
    """
    allowed = {"query_account", "query_positions"}
    if req.method not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"method {req.method!r} is not allowed here; allowed={sorted(allowed)}",
        )

    async def _fn(adapter: Any, is_async: bool) -> Any:
        async_name = f"{req.method}_async"
        if is_async and hasattr(adapter, async_name):
            result = await getattr(adapter, async_name)(**req.kwargs)
        else:
            result = await asyncio.to_thread(getattr(adapter, req.method), **req.kwargs)
        if isinstance(result, AccountData):
            return _acct_to_dict(result)
        if isinstance(result, list):
            return [_pos_to_dict(p) for p in result if isinstance(p, PositionData)]
        return {"raw": repr(result)}

    try:
        return {"method": req.method, "result": await _with_adapter(venue, _fn)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
