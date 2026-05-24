# PricingContext

> Status: **Phase 4 shipped**. Package:
> [`aqp/risk/pricing/`](../aqp/risk/pricing/).

## Why a context manager

The report (gs-quant section) makes the case: every pricing call
needs to know

* The as-of date (point-in-time bias)
* The market data source (live curves vs scenario curves)
* The behaviour (use calibrated curves vs rebuild from constraints)
* The dispatch mode (sync / async / celery)

Passing all of these through every function would clutter every
strategy and risk routine. gs-quant solves it with a context manager
that's read out of a thread-local; Phase 4 brings the same pattern
to AQP using Python's :class:`contextvars.ContextVar` (which works
correctly with asyncio).

```python
from datetime import datetime
from aqp.risk.pricing import PricingContext, RiskMeasure, calc

# Sync dispatch — calc() returns the value directly
with PricingContext(as_of=datetime(2026, 5, 16)):
    price = calc(option, RiskMeasure.PRICE).value
    delta = calc(option, RiskMeasure.DELTA).value

# Async dispatch — calc() returns a coroutine-wrapping future
async with PricingContext(dispatch="async"):
    f = calc(option, RiskMeasure.PRICE)
    value = await f.aresult()

# Celery dispatch — calc() returns a Celery-backed future
async with PricingContext(dispatch="celery"):
    f = calc(portfolio, RiskMeasure.VAR_95)
    value = await f.aresult(timeout=60)
```

## Polymorphic dispatch

Handlers register via :func:`register_measure`:

```python
from aqp.risk.pricing import RiskMeasure, register_measure
from aqp.core.domain.instrument import OptionContract

@register_measure("OptionContract", RiskMeasure.DELTA)
def option_delta(option: OptionContract, *, context):
    # JAX Black-Scholes here
    return ...
```

The dispatcher walks ``__mro__`` so subclasses inherit handlers from
their bases. A ``CryptoOption`` registered without its own delta
handler picks up the ``OptionContract`` handler.

## ``RiskMeasure`` enum

One enum value per measurable quantity, grouped by family:

* **Pricing** -- ``PRICE``, ``THEORETICAL_PRICE``, ``MID_PRICE``,
  ``MARK_PRICE``, ``IMPLIED_VOL``
* **First-order Greeks** -- ``DELTA``, ``GAMMA``, ``THETA``, ``VEGA``,
  ``RHO``, ``PSI``
* **Second-order Greeks** -- ``VANNA``, ``VOLGA``, ``CHARM``, ``SPEED``,
  ``ZOMMA``, ``COLOR``
* **Rates** -- ``IR_DELTA``, ``IR_GAMMA``, ``IR_ANNUAL_IMPLIED_VOL``,
  ``KRD``, ``DV01``, ``CONVEXITY``
* **Credit** -- ``CS01``, ``JTD``
* **Equity** -- ``EQ_DELTA``, ``EQ_VEGA``
* **Aggregate** -- ``NOTIONAL``, ``GROSS_EXPOSURE``, ``NET_EXPOSURE``
* **VaR family** -- ``VAR_95``, ``VAR_99``, ``TVAR_95``, ``TVAR_99``,
  ``MARGINAL_VAR``, ``COMPONENT_VAR``
* **Stress / scenario** -- ``STRESS_LOSS``, ``SCENARIO_PNL``
* **Microstructure** -- ``LOB_DEPTH``, ``LOB_PRESSURE``,
  ``QUEUE_POSITION``

Adding a new measure: add the enum value, ship at least one handler
via :func:`register_measure`, document here.

## Dispatch modes

### sync (default)

The default for one-off calls, REST routes, and tests. Returns a
:class:`PricingFuture` whose ``.value`` is populated immediately.

### async

The handler is wrapped in a coroutine; the caller awaits the future.
Useful when the handler itself makes async work (httpx fetches, Redis
lookups). The handler signature is unchanged -- the dispatcher
manages the asyncio bridge.

### celery

The handler runs out-of-process via a Celery task. The
:class:`PricingFuture` wraps a :class:`celery.result.AsyncResult`
that callers poll. Used for portfolio-wide VaR / TVaR runs that
fan out hundreds of per-instrument tasks.

## Composite futures

When a single calc fans out into many sub-calcs (portfolio VaR,
multi-strike Greeks), :class:`CompositeResultFuture` aggregates them:

```python
from aqp.risk.pricing import CompositeResultFuture

composite = CompositeResultFuture()
for instrument in portfolio.legs:
    composite.add(calc(instrument, RiskMeasure.DELTA))

results = await composite.aresults(timeout=30)
```

## Tenancy + caching

The :class:`PricingContext` includes ``workspace_id`` /
``project_id`` (added in Phase 5 wiring) so per-tenant caches stay
isolated. ``use_cache`` + ``cache_ttl_seconds`` control the Redis
prefetch layer (see [aqp_docs/metadata-cache.md](metadata-cache.md)).
