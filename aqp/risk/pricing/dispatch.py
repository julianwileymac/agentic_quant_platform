"""Polymorphic ``calc(instrument, risk_measure)`` dispatch.

Every instrument subclass declares which measures it can compute via
the :func:`register_measure` decorator. The :func:`calc` entry point
looks up the right handler and routes the call through the active
:class:`PricingContext`'s dispatch mode (sync / async / celery).

Example registrations live in :mod:`aqp.risk.pricing.handlers_options`
and :mod:`aqp.risk.pricing.handlers_portfolio`.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from aqp.risk.pricing.context import PricingContext, current_context
from aqp.risk.pricing.futures import PricingFuture
from aqp.risk.pricing.measures import RiskMeasure

logger = logging.getLogger(__name__)


# Registry: {(instrument_class_name, RiskMeasure): handler_fn}
_HANDLERS: dict[tuple[str, RiskMeasure], Callable[..., Any]] = {}


def register_measure(
    instrument_class: type | str,
    measure: RiskMeasure,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that registers a handler for ``(instrument_class, measure)``.

    ``instrument_class`` is matched by class name so callers can write
    handlers without importing the concrete classes (helpful for the
    optional :mod:`aqp.core.domain.instrument` module).

    .. code-block:: python

        @register_measure("OptionContract", RiskMeasure.DELTA)
        def option_delta(option, *, context: PricingContext) -> float:
            ...
    """
    class_name = (
        instrument_class
        if isinstance(instrument_class, str)
        else instrument_class.__name__
    )

    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        key = (class_name, measure)
        existing = _HANDLERS.get(key)
        if existing is not None and existing is not fn:
            logger.debug("Replacing handler for %s", key)
        _HANDLERS[key] = fn
        return fn

    return _wrap


def get_handler(
    instrument: Any, measure: RiskMeasure
) -> Callable[..., Any] | None:
    """Resolve the right handler walking the MRO of ``instrument``'s class."""
    cls = instrument.__class__
    for ancestor in cls.__mro__:
        handler = _HANDLERS.get((ancestor.__name__, measure))
        if handler is not None:
            return handler
    return None


def calc(
    instrument: Any,
    measure: RiskMeasure,
    *,
    context: PricingContext | None = None,
    **kwargs: Any,
) -> PricingFuture | Any:
    """Polymorphic pricing dispatch.

    Returns the value directly when:

    * The active context's dispatch mode is ``sync`` (default)

    Returns a :class:`PricingFuture` when:

    * The dispatch mode is ``async`` or ``celery``

    Falls back to a synchronous in-process compute when no context is
    active (most callers want this for one-off calls).
    """
    ctx = context or current_context() or PricingContext(dispatch="sync")
    handler = get_handler(instrument, measure)
    if handler is None:
        return PricingFuture(
            mode="sync",
            measure=str(measure),
            instrument_ref=instrument,
            error=(
                f"no handler registered for {instrument.__class__.__name__} + {measure}"
            ),
        )

    started = time.monotonic()

    if ctx.dispatch == "sync":
        try:
            value = handler(instrument, context=ctx, **kwargs)
            return PricingFuture(
                mode="sync",
                measure=str(measure),
                instrument_ref=instrument,
                value=value,
                elapsed_ms=(time.monotonic() - started) * 1000.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("calc(%s, %s) failed", instrument, measure)
            return PricingFuture(
                mode="sync",
                measure=str(measure),
                instrument_ref=instrument,
                error=str(exc),
                elapsed_ms=(time.monotonic() - started) * 1000.0,
            )

    if ctx.dispatch == "async":
        async def _run():
            return handler(instrument, context=ctx, **kwargs)

        return PricingFuture(
            mode="async",
            measure=str(measure),
            instrument_ref=instrument,
            _coro=_run(),
        )

    if ctx.dispatch == "celery":
        try:
            from aqp.tasks.pricing_tasks import price_instrument_task
        except Exception as exc:  # noqa: BLE001
            return PricingFuture(
                mode="sync",
                measure=str(measure),
                instrument_ref=instrument,
                error=f"celery dispatch unavailable: {exc}",
            )
        async_result = price_instrument_task.delay(
            instrument_class=instrument.__class__.__name__,
            measure_value=str(measure),
            spec_json=getattr(instrument, "to_dict", lambda: {})(),
            ctx_json={
                "as_of": ctx.as_of.isoformat() if ctx.as_of else None,
                "market_data_source": ctx.market_data_source,
                "behaviour": ctx.behaviour,
            },
            kwargs=kwargs,
            task_run_id=str(uuid.uuid4()),
        )
        return PricingFuture(
            mode="celery",
            measure=str(measure),
            instrument_ref=instrument,
            _async_result=async_result,
        )

    return PricingFuture(
        mode="sync",
        measure=str(measure),
        instrument_ref=instrument,
        error=f"unknown dispatch mode {ctx.dispatch}",
    )


__all__ = ["calc", "get_handler", "register_measure"]
