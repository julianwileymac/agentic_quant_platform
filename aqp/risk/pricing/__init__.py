"""Phase 4: PricingContext + RiskMeasure + polymorphic ``calc`` dispatch.

The keystone of Phase 4: a gs-quant-inspired async context manager
that bundles every parameter a pricing call needs (as-of date, market
data source, curve overrides, dispatch mode) and routes the actual
math through either a synchronous in-process solver or a Celery
distributed dispatch.

Public surface
==============

.. code-block:: python

    from aqp.risk.pricing import (
        PricingContext,
        PricingFuture,
        RiskMeasure,
        calc,
    )

    # Sync dispatch
    async with PricingContext(as_of=datetime(2026, 5, 16), dispatch="sync"):
        price = calc(option, RiskMeasure.PRICE)
        delta = calc(option, RiskMeasure.DELTA)

    # Async dispatch via Celery
    async with PricingContext(dispatch="celery"):
        f = calc(option, RiskMeasure.VAR_95)
        result = await f.aresult()
"""
from __future__ import annotations

from aqp.risk.pricing.context import (
    PricingContext,
    current_context,
)
from aqp.risk.pricing.dispatch import calc, register_measure
from aqp.risk.pricing.futures import (
    CompositeResultFuture,
    PricingFuture,
)
from aqp.risk.pricing.measures import RiskMeasure

__all__ = [
    "CompositeResultFuture",
    "PricingContext",
    "PricingFuture",
    "RiskMeasure",
    "calc",
    "current_context",
    "register_measure",
]
