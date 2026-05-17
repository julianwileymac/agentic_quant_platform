"""Async PricingContext -- gs-quant-inspired.

A context manager that bundles every parameter a pricing call needs:

* ``as_of`` -- the point-in-time the market data should resolve to
* ``market_data_source`` -- which dataset / Iceberg namespace to read
  curves and vol surfaces from
* ``behaviour`` -- ``Calibrated`` (use the official calibrated curves)
  or ``ConstraintsBased`` (rebuild curves from raw constraint quotes)
* ``dispatch`` -- ``sync`` (in-process), ``async`` (asyncio executor),
  ``celery`` (distributed via Celery)
* ``curve_overrides`` -- per-call curve / surface overrides for
  scenario analysis

Stored as a :class:`contextvars.ContextVar` so the
:func:`aqp.risk.pricing.dispatch.calc` polymorphic dispatch can read
the active context without explicit threading.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)


DispatchMode = Literal["sync", "async", "celery"]
PricingBehaviour = Literal["Calibrated", "ConstraintsBased"]


@dataclass(slots=True)
class PricingContext:
    """gs-quant-style pricing context.

    Use as a (sync or async) context manager:

    .. code-block:: python

        async with PricingContext(as_of=datetime(2026, 5, 16)):
            price = calc(option, RiskMeasure.PRICE)

    Inside the ``with`` block, the ``calc`` dispatch reads the active
    context from a :class:`contextvars.ContextVar` so callers don't
    have to thread the context through every layer.
    """

    as_of: datetime | None = None
    market_data_source: str = "live"
    behaviour: PricingBehaviour = "Calibrated"
    dispatch: DispatchMode = "sync"
    curve_overrides: dict[str, Any] = field(default_factory=dict)
    surface_overrides: dict[str, Any] = field(default_factory=dict)
    use_cache: bool = True
    cache_ttl_seconds: int = 60
    meta: dict[str, Any] = field(default_factory=dict)

    _token: Any = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------
    # Sync context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> PricingContext:
        self._token = _current.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _current.reset(self._token)
            self._token = None

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> PricingContext:
        self._token = _current.set(self)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._token is not None:
            _current.reset(self._token)
            self._token = None

    def __repr__(self) -> str:
        return (
            f"PricingContext(as_of={self.as_of}, "
            f"dispatch={self.dispatch}, behaviour={self.behaviour})"
        )


_current: ContextVar[PricingContext | None] = ContextVar("aqp.pricing.context", default=None)


def current_context() -> PricingContext | None:
    """Return the currently-active :class:`PricingContext`, if any.

    Returns None outside any ``with PricingContext(...)`` block.
    """
    return _current.get()


@contextmanager
def override_context(ctx: PricingContext):
    """Temporarily install ``ctx`` as the active context.

    Useful in tests + dispatch handlers that need to swap the
    context without entering it via the normal ``with`` block.
    """
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


__all__ = [
    "DispatchMode",
    "PricingBehaviour",
    "PricingContext",
    "current_context",
    "override_context",
]
