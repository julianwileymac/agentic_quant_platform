"""Adapter ABCs + auto-registering metaclasses.

Three metaclasses, three ABCs:

- :class:`MarketDataAdapterMeta` + :class:`MarketDataAdapter` —
  inbound market data (ticks, quotes, bars, book snapshots).
- :class:`ExecutionAdapterMeta` + :class:`ExecutionAdapter` — outbound
  order placement / amend / cancel + reconciliation.
- :class:`ControlPlaneAdapterMeta` + :class:`ControlPlaneAdapter` —
  drop-copy ingest, venue admin (e.g. CME drop copy, ICE EAS).

Pattern (mirrors :class:`aqp.kubernetes.protocol.KubernetesAdapterMeta`):

```python
class BinancePerpExecution(ExecutionAdapter):
    adapter_kind = "binance_perp"
    adapter_alias = "binance_perp_v1"

    async def place(self, order):
        ...
```

The metaclass calls ``aqp.core.registry.register`` automatically; routes
and the kernel look up adapters by alias via
:func:`get_market_data_adapter` / :func:`get_execution_adapter`.
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from aqp_bots.schemas.market import MarketEvent
from aqp_bots.schemas.trading import (
    Fill,
    NewOrder,
    OrderAck,
    OrderMod,
    OrderRef,
    Position,
    ReconcileSnapshot,
    Reject,
)

logger = logging.getLogger(__name__)

MARKET_DATA_ADAPTER_KIND = "market_data_adapter"
EXECUTION_ADAPTER_KIND = "execution_adapter"
CONTROL_PLANE_ADAPTER_KIND = "control_plane_adapter"


class AdapterUnavailable(RuntimeError):
    """Raised when an adapter cannot service a call."""


@dataclass(slots=True)
class AdapterCapability:
    """Declarative description of what an adapter supports.

    Used by the operator's validating webhook to reject ``Bot`` CRs
    whose declared venue / instruments / order types aren't supported
    by any registered adapter.
    """

    venue: str
    asset_classes: tuple[str, ...] = field(default_factory=tuple)
    supports_streaming: bool = True
    supports_amend: bool = False
    supports_oco: bool = False
    supports_post_only: bool = False
    max_orders_per_second: int | None = None
    order_types: tuple[str, ...] = ("market", "limit")


@dataclass(slots=True)
class Subscription:
    """Subscription request for a market-data adapter."""

    symbol: str
    channels: tuple[str, ...] = ("trades", "quotes")
    depth: int | None = None
    interval: str | None = None  # for bar subscriptions


# ---------------------------------------------------------------------------
# Metaclasses
# ---------------------------------------------------------------------------


def _make_meta(kind: str, label: str) -> type:
    """Factory for the three adapter metaclasses (identical pattern)."""

    class _Meta(ABCMeta):
        def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
            cls = super().__new__(mcs, name, bases, namespace, **kwargs)
            if namespace.get("__abstract_adapter__", False):
                return cls
            if name.startswith(("Base", "_")):
                return cls
            adapter_kind = getattr(cls, "adapter_kind", None)
            if not adapter_kind:
                return cls
            alias = getattr(cls, "adapter_alias", None) or cls.__name__
            try:
                from aqp.core.registry import register

                register(name=alias, kind=kind, source=str(adapter_kind))(cls)
            except Exception:  # noqa: BLE001
                logger.debug(
                    "%s auto-registration failed for %s", label, name, exc_info=True
                )
            return cls

    _Meta.__name__ = f"{label}Meta"
    _Meta.__qualname__ = f"{label}Meta"
    return _Meta


MarketDataAdapterMeta = _make_meta(MARKET_DATA_ADAPTER_KIND, "MarketDataAdapter")
ExecutionAdapterMeta = _make_meta(EXECUTION_ADAPTER_KIND, "ExecutionAdapter")
ControlPlaneAdapterMeta = _make_meta(
    CONTROL_PLANE_ADAPTER_KIND, "ControlPlaneAdapter"
)


# ---------------------------------------------------------------------------
# Market-data adapter ABC
# ---------------------------------------------------------------------------


class MarketDataAdapter(metaclass=MarketDataAdapterMeta):
    """Inbound market data: ticks, quotes, bars, book snapshots."""

    __abstract_adapter__: ClassVar[bool] = True
    adapter_kind: ClassVar[str] = ""
    adapter_alias: ClassVar[str | None] = None
    capability: ClassVar[AdapterCapability | None] = None

    @abstractmethod
    async def connect(self) -> None:
        """Open transport (WebSocket / FIX session / REST poller)."""

    @abstractmethod
    async def subscribe(self, sub: Subscription) -> None:
        """Subscribe to a symbol/channel pair."""

    @abstractmethod
    def stream(self) -> AsyncIterator[MarketEvent]:
        """Yield :class:`MarketEvent` until :meth:`aclose` is called."""

    @abstractmethod
    async def aclose(self) -> None:
        """Close transport + cancel any background tasks."""

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.adapter_kind,
            "alias": self.adapter_alias or self.__class__.__name__,
            "capability": (
                {
                    "venue": self.capability.venue,
                    "asset_classes": list(self.capability.asset_classes),
                    "supports_streaming": self.capability.supports_streaming,
                }
                if self.capability is not None
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Execution adapter ABC
# ---------------------------------------------------------------------------


class ExecutionAdapter(metaclass=ExecutionAdapterMeta):
    """Outbound order placement + reconciliation.

    Hard rule 14 (`BotRuntime` is the only sanctioned executor) is
    preserved: strategies don't call adapters directly — they emit
    :class:`NewOrder` to the kernel bus and the kernel's
    ``execution_task`` drives the right adapter.
    """

    __abstract_adapter__: ClassVar[bool] = True
    adapter_kind: ClassVar[str] = ""
    adapter_alias: ClassVar[str | None] = None
    capability: ClassVar[AdapterCapability | None] = None

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def place(self, order: NewOrder) -> OrderAck | Reject:
        """Submit a new order. Returns the venue ack or a reject."""

    @abstractmethod
    async def cancel(self, ref: OrderRef) -> OrderAck | Reject:
        """Cancel an in-flight order."""

    async def amend(self, mod: OrderMod) -> OrderAck | Reject:
        """Amend an in-flight order. Default: not supported."""
        raise AdapterUnavailable(
            f"{self.__class__.__name__} does not support amend"
        )

    @abstractmethod
    def stream(self) -> AsyncIterator[OrderAck | Fill | Reject]:
        """Yield order state updates (acks, fills, rejects)."""

    @abstractmethod
    async def positions(self) -> tuple[Position, ...]:
        """Snapshot of current positions on the venue."""

    @abstractmethod
    async def reconcile(self) -> ReconcileSnapshot:
        """Full venue-state snapshot for OMS reconciliation."""

    @abstractmethod
    async def aclose(self) -> None:
        ...

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.adapter_kind,
            "alias": self.adapter_alias or self.__class__.__name__,
            "capability": (
                {
                    "venue": self.capability.venue,
                    "supports_amend": self.capability.supports_amend,
                    "supports_oco": self.capability.supports_oco,
                    "order_types": list(self.capability.order_types),
                }
                if self.capability is not None
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Control-plane adapter ABC (drop-copy + venue admin)
# ---------------------------------------------------------------------------


class ControlPlaneAdapter(metaclass=ControlPlaneAdapterMeta):
    """Venue-side control plane (drop-copy, mass cancel, account admin).

    Drop-copy is *read-only* by FIX 4.4 / CME convention — the
    adapter receives execution-report copies from the venue but does
    NOT route orders.
    """

    __abstract_adapter__: ClassVar[bool] = True
    adapter_kind: ClassVar[str] = ""
    adapter_alias: ClassVar[str | None] = None

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    def stream(self) -> AsyncIterator[Fill | OrderAck | Reject]:
        ...

    @abstractmethod
    async def aclose(self) -> None:
        ...


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def list_market_data_adapters() -> dict[str, type[MarketDataAdapter]]:
    """Return ``{alias: class}`` for every registered market-data adapter."""
    return _list_by(MARKET_DATA_ADAPTER_KIND, MarketDataAdapter)


def list_execution_adapters() -> dict[str, type[ExecutionAdapter]]:
    """Return ``{alias: class}`` for every registered execution adapter."""
    return _list_by(EXECUTION_ADAPTER_KIND, ExecutionAdapter)


def list_control_plane_adapters() -> dict[str, type[ControlPlaneAdapter]]:
    return _list_by(CONTROL_PLANE_ADAPTER_KIND, ControlPlaneAdapter)


def _list_by(kind: str, base_cls: type) -> dict[str, type]:
    try:
        from aqp.core.registry import list_by_kind
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, type] = {}
    for alias, cls in list_by_kind(kind).items():
        if isinstance(cls, type) and issubclass(cls, base_cls):
            out[alias] = cls
    return out


def get_market_data_adapter(alias: str) -> type[MarketDataAdapter]:
    """Resolve a registered adapter class by alias."""
    adapters = list_market_data_adapters()
    if alias not in adapters:
        raise KeyError(
            f"No market_data_adapter registered under {alias!r}; "
            f"options: {sorted(adapters)}"
        )
    return adapters[alias]


def get_execution_adapter(alias: str) -> type[ExecutionAdapter]:
    """Resolve a registered adapter class by alias."""
    adapters = list_execution_adapters()
    if alias not in adapters:
        raise KeyError(
            f"No execution_adapter registered under {alias!r}; "
            f"options: {sorted(adapters)}"
        )
    return adapters[alias]


__all__ = [
    "AdapterCapability",
    "AdapterUnavailable",
    "CONTROL_PLANE_ADAPTER_KIND",
    "ControlPlaneAdapter",
    "ControlPlaneAdapterMeta",
    "EXECUTION_ADAPTER_KIND",
    "ExecutionAdapter",
    "ExecutionAdapterMeta",
    "MARKET_DATA_ADAPTER_KIND",
    "MarketDataAdapter",
    "MarketDataAdapterMeta",
    "Subscription",
    "get_execution_adapter",
    "get_market_data_adapter",
    "list_control_plane_adapters",
    "list_execution_adapters",
    "list_market_data_adapters",
]
