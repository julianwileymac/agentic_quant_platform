"""Adapter layer: metaclass-driven Protocols for market data + execution.

Mirrors :class:`aqp.kubernetes.protocol.KubernetesAdapterMeta` (line 107 of
``aqp/kubernetes/protocol.py``) — subclasses set ``adapter_kind`` (e.g.
``binance_perp``, ``cme_fix``) and the metaclass registers the class
through :func:`aqp.core.registry.register` automatically.

Families:

- :mod:`aqp_bots.adapters.fix` — FIX 4.x / 5.x via simplefix, with the
  full ResendRequest / SeqResetGapFill / TestRequest recovery state
  machine documented in blueprint §G.5.
- :mod:`aqp_bots.adapters.websocket` — generic WS framework with
  reconnect / backoff / msgspec JSON decode.
- :mod:`aqp_bots.adapters.rest` — :class:`httpx.AsyncClient` + tenacity
  retry + aiolimiter token bucket.
- :mod:`aqp_bots.adapters.grpc` — gRPC adapter base.
- :mod:`aqp_bots.adapters.onchain` — web3.py + Flashbots + MEV-share.
- :mod:`aqp_bots.adapters.bridges` — wraps existing AQP infrastructure
  (Alpaca, IBKR, paper session) so the kernel runtime can drive them
  without rewriting.
"""
from __future__ import annotations

from aqp_bots.adapters.protocol import (
    AdapterCapability,
    ControlPlaneAdapter,
    ControlPlaneAdapterMeta,
    ExecutionAdapter,
    ExecutionAdapterMeta,
    MarketDataAdapter,
    MarketDataAdapterMeta,
    Subscription,
    get_execution_adapter,
    get_market_data_adapter,
    list_execution_adapters,
    list_market_data_adapters,
)

__all__ = [
    "AdapterCapability",
    "ControlPlaneAdapter",
    "ControlPlaneAdapterMeta",
    "ExecutionAdapter",
    "ExecutionAdapterMeta",
    "MarketDataAdapter",
    "MarketDataAdapterMeta",
    "Subscription",
    "get_execution_adapter",
    "get_market_data_adapter",
    "list_execution_adapters",
    "list_market_data_adapters",
]
