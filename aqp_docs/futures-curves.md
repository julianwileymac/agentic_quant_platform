# Continuous futures curves

> Status: **Phase 1 shipped**. Builder module:
> [`aqp/data/futures/curve.py`](../aqp/data/futures/curve.py). DataMCP
> tools: ``data.futures.curve.list`` + ``data.futures.curve.stitched``.

## Why

A futures contract is a dated instrument: every ``ES`` contract has
an expiry and gets rolled forward at some cadence. Naive concatenation
of ``ESH26``, ``ESM26``, ``ESU26`` produces a series with
discontinuities at every roll -- the backtest will see overnight
jumps that don't reflect any market move, just the spread between the
expiring and next contract.

The continuous-curve constructor stitches those contracts into a
single, roll-adjusted series suitable for long-horizon backtests,
ML feature engineering, and stat-arb basis trading.

## Concept map

```text
InstrumentFuture           (parent: ``ESH26`` / ``ESM26`` / ``ESU26`` / ...)
                              |
                              v
FuturesCurveRow            (one row per ``(root_symbol, expiry, snapshot_date)``)
                              |
                              v
FuturesCurve.snapshots     (in-memory grouping by root)
                              |
                       VolumeBasedRoll | DateBasedRoll | OpenInterestRoll
                              |
                              v
StitchedCurveRow + RollEvent (per-day stitched series + audit log)
                              |
                              v
aqp_gold_futures.continuous_curves   (Iceberg gold tier)
```

## Roll rules

Three deterministic strategies live in
[`aqp.data.futures.curve`](../aqp/data/futures/curve.py):

### ``VolumeBasedRoll``

Roll when the next-month contract's volume exceeds the front-month
contract's volume by ``min_volume_ratio`` (default 1.0). This is the
typical CTA / managed-futures rule -- "trade where the liquidity is".

```python
from aqp.data.futures.curve import VolumeBasedRoll
rule = VolumeBasedRoll(min_volume_ratio=1.2)  # 20% buffer prevents jitter
```

### ``DateBasedRoll``

Roll when within ``days_before_expiry`` calendar days of front expiry
(default 5). Simplest rule, useful when liquidity data is unavailable.
Typical for equity-index futures.

```python
from aqp.data.futures.curve import DateBasedRoll
rule = DateBasedRoll(days_before_expiry=5)
```

### ``OpenInterestRoll``

Roll when the next contract's open interest exceeds the front-month's.
Useful when volume is noisy but open interest is stable.

```python
from aqp.data.futures.curve import OpenInterestRoll
rule = OpenInterestRoll(min_oi_ratio=1.0)
```

### Custom rules

Subclass :class:`RollRule` and implement ``should_roll``:

```python
from datetime import date
from aqp.data.futures.curve import FuturesCurveSnapshot, RollRule

class TermStructureRoll(RollRule):
    name = "term_structure"
    def should_roll(self, *, front, next_contract, as_of: date) -> bool:
        # Roll when the curve goes into backwardation
        return next_contract.price < front.price
```

## Adjustment modes

After identifying a roll, three modes scale pre-roll history so the
stitched series is continuous:

| Mode | Math | When to use |
| --- | --- | --- |
| ``none`` | No adjustment | Diagnostic only -- has discontinuities at every roll |
| ``back_adjusted`` | Additive: ``offset += new_price - old_price`` then ``stitched = raw + offset`` | Default. Preserves latest price, shifts older history. |
| ``ratio`` | Multiplicative: ``factor *= new_price / old_price`` | Useful when prices span orders of magnitude (very long history). |

Back-adjustment is the typical CTA choice because it preserves the
absolute price scale at the head of the series (the part used for
live signal generation).

## End-to-end example

```python
from aqp.data.futures.curve import (
    VolumeBasedRoll,
    load_curve_snapshots,
    stitch_curve,
    stitched_to_arrow,
)
from aqp.data.iceberg_catalog import append_arrow
from aqp.data.catalog.active_metadata import BusinessMetadata

curve = load_curve_snapshots("ES")
rows, rolls = stitch_curve(curve, rule=VolumeBasedRoll(), adjustment="back_adjusted")

# Audit: print every roll the stitcher emitted
for e in rolls:
    print(
        e.snapshot_date,
        e.from_contract,
        "->",
        e.to_contract,
        f"(gap={e.to_price - e.from_price:.2f})",
    )

# Persist to gold tier (medallion-validated)
tbl = stitched_to_arrow(
    rows, root_symbol="ES", rule_name="volume", adjustment="back_adjusted"
)
append_arrow(
    "aqp_gold_futures.continuous_curves",
    tbl,
    medallion_layer="gold",
    business_metadata=BusinessMetadata(
        data_owner="quant_research",
        semantic_definition="Continuous, roll-adjusted futures series",
        reliability_score=0.95,
        domain="market.futures",
    ),
)
```

## DataMCP surface

```text
data.futures.curve.list(root_symbol="ES")
data.futures.curve.stitched(root_symbol="ES",
                            rule="volume",
                            adjustment="back_adjusted",
                            limit_rows=2000)
```

Both tools are read-only; the gold-tier Iceberg write is left to the
analysis-flow path (AGENTS rule 23) so agents never accidentally
overwrite the canonical stitched series.

## Roll-rule selection guide

| Asset class | Recommended rule | Why |
| --- | --- | --- |
| Equity index futures (ES, NQ, RTY) | ``VolumeBasedRoll`` | Liquidity flips abruptly ~5d before expiry |
| Treasury futures (ZN, ZB) | ``OpenInterestRoll`` | Volume can be noisy; OI is a cleaner signal |
| Commodity futures (CL, NG, GC) | ``DateBasedRoll(days_before_expiry=10)`` | Roll well before delivery to avoid first-notice-day risk |
| FX futures (6E, 6J) | ``VolumeBasedRoll`` | Quarterly rolls with abrupt liquidity transitions |
| Single-stock futures | ``OpenInterestRoll`` | Thin liquidity -- volume gives false positives |
