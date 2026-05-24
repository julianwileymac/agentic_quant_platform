"""QuantBot Platform core — single-thread asyncio kernel + primitives.

Six modules:

- :mod:`aqp_bots.core.lifecycle` — 10-state FSM for the bot life cycle.
- :mod:`aqp_bots.core.clock` — wall / monotonic / simulated / PTP clocks.
- :mod:`aqp_bots.core.ids` — UUIDv7 + newtype identifiers.
- :mod:`aqp_bots.core.bus` — :class:`MessageBus` protocol + default
  asyncio-queue implementation.
- :mod:`aqp_bots.core.futures` — request/response :class:`asyncio.Future`
  registry keyed by ``client_order_id``.
- :mod:`aqp_bots.core.kernel` — :class:`BotKernel` (single-thread asyncio
  runtime composing the 7 layers from :class:`BotSpec.capabilities`).

The kernel is **only** invoked via :meth:`BotRuntime._run_with_kernel`
(Phase 2 wiring on :class:`BotRuntime`) — never imported directly by a
strategy or route. Hard rule 14 (``BotRuntime`` is the single sanctioned
executor) is preserved.
"""
from __future__ import annotations

from aqp_bots.core.bus import AsyncQueueBus, MessageBus
from aqp_bots.core.clock import (
    Clock,
    MonotonicClock,
    SimulatedClock,
    SystemClock,
    get_default_clock,
)
from aqp_bots.core.futures import OrderFutureRegistry
from aqp_bots.core.ids import (
    BotID,
    OrderID,
    RunID,
    StrategyID,
    new_bot_id,
    new_client_order_id,
    new_run_id,
)
from aqp_bots.core.kernel import BotKernel, BotKernelConfig
from aqp_bots.core.lifecycle import (
    BotState,
    LifecycleError,
    LifecycleFSM,
    TransitionEvent,
)

__all__ = [
    "AsyncQueueBus",
    "BotID",
    "BotKernel",
    "BotKernelConfig",
    "BotState",
    "Clock",
    "LifecycleError",
    "LifecycleFSM",
    "MessageBus",
    "MonotonicClock",
    "OrderFutureRegistry",
    "OrderID",
    "RunID",
    "SimulatedClock",
    "StrategyID",
    "SystemClock",
    "TransitionEvent",
    "get_default_clock",
    "new_bot_id",
    "new_client_order_id",
    "new_run_id",
]
