"""Bridge adapters: wrap existing AQP infrastructure for the new kernel runtime.

Lets the kernel drive the existing brokerages (Alpaca, IBKR, paper) and
the existing Alpaca/Polygon WebSocket ingesters without rewriting any
of them.

- :class:`PaperBridgeExecutionAdapter` — wraps the existing
  :class:`aqp.trading.session.PaperTradingSession` so a kernel-mode bot
  can paper-trade against the same simulated brokerage as the legacy
  ``BotRuntime.paper()`` path.
- :class:`AlpacaBridgeExecutionAdapter` — wraps the existing
  :class:`aqp.trading.brokerages.alpaca.AlpacaBrokerage`
  (an :class:`IDomainBrokerage`).
- :class:`IBKRBridgeExecutionAdapter` — wraps
  :class:`aqp.trading.brokerages.ibkr.InteractiveBrokersBrokerage`.
- :class:`AlpacaBridgeMarketDataAdapter` — wraps
  :mod:`aqp.streaming.ingesters.alpaca`.
"""
from __future__ import annotations

from aqp_bots.adapters.bridges.alpaca_market_bridge import (
    AlpacaBridgeMarketDataAdapter,
)
from aqp_bots.adapters.bridges.execution_bridges import (
    AlpacaBridgeExecutionAdapter,
    IBKRBridgeExecutionAdapter,
    PaperBridgeExecutionAdapter,
)

__all__ = [
    "AlpacaBridgeExecutionAdapter",
    "AlpacaBridgeMarketDataAdapter",
    "IBKRBridgeExecutionAdapter",
    "PaperBridgeExecutionAdapter",
]
