"""BotKernel — single-thread asyncio runtime composing the seven layers.

The kernel is the data-plane half of the QuantBot Platform — the operator
schedules a Pod that imports the kernel, hands it a :class:`BotManifest`,
and calls :meth:`BotKernel.run`.  The kernel:

1. Wires the seven layers from the manifest's :class:`CapabilitySpec` +
   layer specs (Phase 1).
2. Drives the :class:`LifecycleFSM` through ``Provisioning ->
   Initializing -> WarmingUp -> Running``.
3. Runs 7 concurrent coroutines on a single uvloop-accelerated asyncio
   loop (blueprint §I.2):
   - ``ingest_task`` — pull events from market-data adapters into the bus.
   - ``feature_task`` — optional feature enrichment / cache lookups.
   - ``strategy_task`` — tick -> signal.
   - ``risk_task`` — signal -> pass/fail/clip.
   - ``execution_task`` — submit / modify / cancel via execution adapters.
   - ``reconcile_task`` — drop-copy + venue polling reconciliation.
   - ``telemetry_task`` — non-blocking export to OTel + Prometheus.
4. Handles graceful drain on SIGTERM (operator finalizer hook).

Hard rule 14: :class:`BotKernel` is invoked **only** from inside
:class:`aqp_bots.runtime.BotRuntime` (the single sanctioned executor).
Strategies do not import it.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from aqp_bots.core.bus import AsyncQueueBus, MessageBus
from aqp_bots.core.clock import Clock, SystemClock, get_default_clock
from aqp_bots.core.futures import OrderFutureRegistry
from aqp_bots.core.ids import BotID, RunID, new_bot_id, new_run_id
from aqp_bots.core.lifecycle import (
    BotState,
    LifecycleError,
    LifecycleFSM,
    TransitionEvent,
)
from aqp_bots.spec import BotSpec, Frequency

logger = logging.getLogger(__name__)


# Strategy-level coroutine signature: takes a context, returns when shutdown.
CoroFactory = Callable[["BotKernel"], Awaitable[None]]


@dataclass(slots=True)
class BotKernelConfig:
    """Tunables for the kernel runtime."""

    warmup_timeout_s: float = 60.0
    drain_timeout_s: float = 300.0
    use_uvloop: bool = True
    enable_signal_handlers: bool = True
    bus_default_maxsize: int = 4096
    order_idempotency_lru_size: int = 4096

    @classmethod
    def from_spec(cls, spec: BotSpec) -> BotKernelConfig:
        """Derive kernel config from a :class:`BotSpec`.

        HFT bots get aggressive drain timeout (30s vs 300s) and larger
        bus queues; everything else uses defaults.
        """
        cfg = cls()
        if spec.capabilities and spec.capabilities.frequency == Frequency.HFT:
            cfg.drain_timeout_s = 30.0
            cfg.bus_default_maxsize = 16384
        if spec.lifecycle is not None:
            cfg.warmup_timeout_s = float(spec.lifecycle.warmup_timeout_seconds)
            cfg.drain_timeout_s = float(spec.lifecycle.drain_timeout_seconds)
        if spec.execution_layer is not None:
            cfg.order_idempotency_lru_size = int(
                spec.execution_layer.idempotency_lru_size
            )
        return cfg


@dataclass(slots=True)
class _LayerHooks:
    """Per-layer coroutines wired by :meth:`BotKernel.wire_layer`.

    Each hook is called once per kernel run; the kernel awaits them all
    in parallel via :class:`asyncio.TaskGroup`. Missing hooks are
    skipped silently — a bot may legitimately have no telemetry layer
    if it's a backtest, no reconcile task if it's paper-only, etc.
    """

    ingest: CoroFactory | None = None
    feature: CoroFactory | None = None
    strategy: CoroFactory | None = None
    risk: CoroFactory | None = None
    execution: CoroFactory | None = None
    reconcile: CoroFactory | None = None
    telemetry: CoroFactory | None = None
    on_start: list[CoroFactory] = field(default_factory=list)
    on_drain: list[CoroFactory] = field(default_factory=list)


class BotKernel:
    """Single-thread asyncio runtime for a single bot instance.

    Lifecycle::

        async with BotKernel(spec) as kernel:
            kernel.wire_layer("strategy", my_strategy_loop)
            kernel.wire_layer("execution", my_execution_loop)
            await kernel.run()

    On normal exit the kernel walks the FSM through ``Running -> Draining
    -> Stopped``. On SIGTERM / SIGINT it drains gracefully (cancel orders,
    optionally flatten) within :attr:`config.drain_timeout_s`. On unhandled
    exception it transitions to ``Failed``.
    """

    def __init__(
        self,
        spec: BotSpec,
        *,
        bot_id: BotID | None = None,
        run_id: RunID | None = None,
        clock: Clock | None = None,
        bus: MessageBus | None = None,
        config: BotKernelConfig | None = None,
    ) -> None:
        self.spec = spec
        self.bot_id: BotID = bot_id or new_bot_id()
        self.run_id: RunID = run_id or new_run_id()
        self.config = config or BotKernelConfig.from_spec(spec)
        self.clock: Clock = clock or get_default_clock()
        self.bus: MessageBus = bus or AsyncQueueBus(
            default_maxsize=self.config.bus_default_maxsize
        )
        self.futures = OrderFutureRegistry(
            lru_size=self.config.order_idempotency_lru_size
        )
        self.fsm = LifecycleFSM()
        self._hooks = _LayerHooks()
        self._tasks: list[asyncio.Task[Any]] = []
        self._shutdown_evt: asyncio.Event | None = None
        self._exit_stack = AsyncExitStack()

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def wire_layer(self, layer: str, factory: CoroFactory) -> None:
        """Attach a coroutine factory to one of the seven layers.

        Valid ``layer`` values: ``ingest``, ``feature``, ``strategy``,
        ``risk``, ``execution``, ``reconcile``, ``telemetry``.
        """
        if not hasattr(self._hooks, layer):
            raise ValueError(
                f"Unknown layer {layer!r}; valid: "
                "ingest feature strategy risk execution reconcile telemetry"
            )
        setattr(self._hooks, layer, factory)

    def on_start(self, factory: CoroFactory) -> None:
        """Attach a coroutine that runs once during the warmup phase."""
        self._hooks.on_start.append(factory)

    def on_drain(self, factory: CoroFactory) -> None:
        """Attach a coroutine that runs once during the drain phase."""
        self._hooks.on_drain.append(factory)

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe_lifecycle(self, hook: Callable[[TransitionEvent], None]) -> None:
        """Receive every FSM transition event."""
        self.fsm.subscribe(hook)

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    async def __aenter__(self) -> BotKernel:
        await self._exit_stack.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)

    async def run(self) -> None:
        """Walk the lifecycle FSM and run the seven coroutines.

        Returns when the FSM reaches a terminal state. Raises only if
        a layer hook raises something it didn't catch.
        """
        self._shutdown_evt = asyncio.Event()
        self._install_signal_handlers()
        try:
            await self._enter_initializing()
            await self._warmup()
            await self._enter_running()
            await self._main_loop()
        except Exception as exc:  # noqa: BLE001
            logger.exception("kernel run failed for bot %s", self.bot_id)
            self.fsm.fail(reason=f"unhandled: {exc!r}")
            raise
        finally:
            await self._drain()
            await self.bus.aclose()

    # ------------------------------------------------------------------
    # FSM phases
    # ------------------------------------------------------------------

    async def _enter_initializing(self) -> None:
        self.fsm.transition(BotState.INITIALIZING, reason="kernel.run() started")
        logger.info(
            "kernel.init bot_id=%s run_id=%s spec=%s",
            self.bot_id,
            self.run_id,
            self.spec.slug or self.spec.name,
        )

    async def _warmup(self) -> None:
        self.fsm.transition(BotState.WARMING_UP, reason="warmup")
        if not self._hooks.on_start:
            return
        async with asyncio.timeout(self.config.warmup_timeout_s):
            for factory in self._hooks.on_start:
                await factory(self)

    async def _enter_running(self) -> None:
        self.fsm.transition(BotState.RUNNING, reason="warmup complete")

    async def _main_loop(self) -> None:
        # Launch the seven canonical coroutines via TaskGroup so a failure
        # in one cancels the rest.
        layer_factories = (
            ("ingest", self._hooks.ingest),
            ("feature", self._hooks.feature),
            ("strategy", self._hooks.strategy),
            ("risk", self._hooks.risk),
            ("execution", self._hooks.execution),
            ("reconcile", self._hooks.reconcile),
            ("telemetry", self._hooks.telemetry),
        )

        async def _wrap(name: str, factory: CoroFactory) -> None:
            try:
                await factory(self)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("kernel layer %s raised", name)
                raise

        try:
            async with asyncio.TaskGroup() as tg:
                for name, factory in layer_factories:
                    if factory is None:
                        continue
                    tg.create_task(_wrap(name, factory), name=f"kernel.{name}")
                assert self._shutdown_evt is not None
                tg.create_task(self._shutdown_evt.wait(), name="kernel.shutdown")
        except* asyncio.CancelledError:
            # Normal shutdown path — TaskGroup cancellation when shutdown
            # fires.  Suppress so the kernel transitions cleanly to Draining.
            pass

    async def _drain(self) -> None:
        if self.fsm.state in (BotState.STOPPED, BotState.KILLED, BotState.FAILED):
            return
        self.fsm.transition(BotState.DRAINING, reason="drain start")
        try:
            async with asyncio.timeout(self.config.drain_timeout_s):
                for factory in self._hooks.on_drain:
                    try:
                        await factory(self)
                    except Exception:  # noqa: BLE001
                        logger.exception("drain hook raised")
        except asyncio.TimeoutError:
            logger.warning(
                "drain timeout (%.1fs) exceeded for bot %s",
                self.config.drain_timeout_s,
                self.bot_id,
            )
        try:
            self.fsm.transition(BotState.STOPPED, reason="drain complete")
        except LifecycleError:
            pass

    # ------------------------------------------------------------------
    # Shutdown plumbing
    # ------------------------------------------------------------------

    def request_shutdown(self, *, reason: str = "shutdown_requested") -> None:
        """Trigger the kernel to drain.  Idempotent."""
        if self._shutdown_evt is None:
            return
        if not self._shutdown_evt.is_set():
            logger.info("kernel shutdown requested: %s", reason)
            self._shutdown_evt.set()

    def request_kill(self, *, reason: str = "kill_switch") -> None:
        """Emergency kill — bypasses drain hooks.  Cancels every task immediately."""
        logger.warning("kernel KILL requested: %s", reason)
        if self._shutdown_evt is not None:
            self._shutdown_evt.set()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        try:
            self.fsm.kill(reason=reason)
        except LifecycleError:
            pass

    def _install_signal_handlers(self) -> None:
        if not self.config.enable_signal_handlers:
            return
        if sys.platform == "win32":
            return  # signal.add_signal_handler unsupported on Windows
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for sig_name in ("SIGTERM", "SIGINT"):
            try:
                loop.add_signal_handler(
                    getattr(signal, sig_name),
                    lambda s=sig_name: self.request_shutdown(reason=f"signal:{s}"),
                )
            except (NotImplementedError, RuntimeError):
                pass


# ---------------------------------------------------------------------------
# uvloop bootstrap (best-effort)
# ---------------------------------------------------------------------------


def install_uvloop() -> bool:
    """Install uvloop as the asyncio event loop policy.

    Returns True on success, False when uvloop isn't installed (Windows,
    minimal envs, tests). Safe to call multiple times.
    """
    try:
        import uvloop  # type: ignore[import-not-found]

        uvloop.install()
        return True
    except Exception:  # noqa: BLE001
        return False


__all__ = [
    "BotKernel",
    "BotKernelConfig",
    "install_uvloop",
]
