# Statistical arbitrage primitives

> Status: **Phase 4 shipped**. Module:
> [`aqp/math/arbitrage.py`](../aqp/math/arbitrage.py). Analysis flows:
> [`aqp/analysis/flows/arbitrage.py`](../aqp/analysis/flows/arbitrage.py).

## Five primitives

| Function | Returns | Use |
| --- | --- | --- |
| :func:`johansen_test` | :class:`JohansenResult` | Multivariate cointegration rank among >=2 series |
| :func:`rolling_zscore` | pandas Series | Normalized spread for entry/exit thresholds |
| :func:`half_life` | :class:`HalfLifeResult` | Ornstein-Uhlenbeck mean-reversion timescale |
| :func:`pair_signal` | :class:`PairSignal` | Per-bar ENTRY/EXIT/HOLD for a pair strategy |
| :func:`ah_share_basis` | :class:`BasisResult` | A-share vs H-share cross-market basis |
| :func:`adr_basis` | :class:`BasisResult` | ADR / GDR vs underlying foreign equity basis |

The existing
[`aqp/data/cointegration.py`](../aqp/data/cointegration.py) module
keeps the ADF + Engle-Granger primitives -- Phase 4 doesn't duplicate
them.

## Johansen test

The Engle-Granger test handles two series; Johansen generalises to
``n >= 2`` and reports the **rank** of the cointegration space (how
many independent stationary combinations exist among the series).

```python
import pandas as pd
from aqp.math.arbitrage import johansen_test

# Wide DataFrame: one column per series
prices = pd.DataFrame({
    "BABA_ADR": [...],
    "9988_HKEX_USD": [...],
    "SPY": [...],
})
result = johansen_test(prices, deterministic="constant", k_ar_diff=1)
print(result.rank, result.is_cointegrated_95)
# result.cointegrating_vectors: list[list[float]] -- the n rows of beta
```

## Pair signal state machine

The :func:`pair_signal` function reads the latest spread + a rolling
window and emits one of:

| Signal | Z-score | In position? |
| --- | --- | --- |
| ``ENTRY_LONG_SPREAD`` | ``z >= +entry_threshold`` | False |
| ``ENTRY_SHORT_SPREAD`` | ``z <= -entry_threshold`` | False |
| ``EXIT_LONG_SPREAD`` | ``\|z\| <= exit_threshold`` AND z >= 0 | True |
| ``EXIT_SHORT_SPREAD`` | ``\|z\| <= exit_threshold`` AND z < 0 | True |
| ``HOLD`` | otherwise | any |

The signal also reports the estimated half-life via
:func:`half_life`. Strategies typically reject opportunities where
the half-life exceeds a horizon-based ``half_life_min`` (the spread
will take too long to revert; capital is better deployed elsewhere).

## A/H share basis

The report calls out a specific cross-market arbitrage:
mainland A-shares vs Hong Kong H-shares of the same company. Same
economic rights, different regulatory + liquidity + currency
environments -> persistent divergence + violent reversion.

```python
from aqp.math.arbitrage import ah_share_basis

# ICBC: 1398.HK in HKD, 601398.SS in CNY. CNYHKD ~ 0.93 (CNY per HKD)
res = ah_share_basis(
    a_price=5.10,
    h_price=4.82,
    fx_rate=0.93,
    conversion_ratio=1.0,
    transaction_cost_bps=20.0,
    threshold_bps=100.0,
)
print(res.is_arbitrage, res.arbitrage_direction)
```

The threshold default of 100 bps is conservative; CTA-style operators
typically use 60-80 bps. ``transaction_cost_bps`` captures the
round-trip cost (commissions + bid/ask + stamp duty + FX hedge cost).

## ADR / GDR basis

Same logic for US-listed ADRs and offshore-listed GDRs. The Phase 1
:class:`InstrumentADR` / :class:`InstrumentGDR` rows carry the
``conversion_ratio`` field directly so the basis algorithm reads it
without a manual lookup.

```python
# BABA ADR (NYSE) vs 9988 (HKEX). 1 ADR represents 8 H-shares.
res = adr_basis(
    adr_price=85.00,
    underlying_price=80.50,  # in HKD
    fx_rate=7.84,            # HKD per USD
    conversion_ratio=8.0,
    transaction_cost_bps=30.0,
    depository_fee_bps=5.0,
    threshold_bps=80.0,
)
```

The depository fee is annualised; over short holding periods (hours,
days) it's negligible, but on long-horizon basis trades it
materially eats into the alpha.

## Analysis flows

Four flows wrap the primitives so the AnalysisRuntime can drive them
with the standard preview / persist / chart machinery:

* ``arbitrage.johansen_basket`` -- Johansen test on a column subset
* ``arbitrage.pair_signal`` -- latest pair signal from a spread column
* ``arbitrage.ah_share_basis`` -- per-bar A/H basis monitor
* ``arbitrage.adr_basis`` -- per-bar ADR basis monitor

Each is registered via
[`@register_analysis_flow`](../aqp/analysis/registry.py) so the lab
UI builds a form automatically.

## Agent surface (Phase 5)

The matching DataMCP tools (added in Phase 5):

* ``data.arbitrage.cointegration_pair`` -- two-series Engle-Granger
* ``data.arbitrage.johansen_basket`` -- multivariate Johansen finder
* ``data.arbitrage.ah_share_monitor`` -- A/H share monitor
* ``data.arbitrage.adr_underlying_basis`` -- ADR basis monitor

Agent code uses these tools, not the math primitives directly
(AGENTS rule 22).
