# notebooks-master — Extraction Reference

**Source:** `inspiration/notebooks-master/`
**Repo character:** Academic systematic-strategy reproduction on futures/equities/crypto using the proprietary `vivace` library. We re-implement signal math against AQP's bar interface; engine plumbing replaced.

See [_KNOWN_ISSUES.md](../_KNOWN_ISSUES.md) for vivace-specific caveats.

## Strategies (16) — port to `aqp/strategies/notebooks/`

### MoskowitzTSMOM

**Source:** `trend_following_moskowitz2012.ipynb`
**Logic:** Time-series momentum: 12-month return sign → long/short. Vol-scaled to 40% annualized target. Position cap.
**AQP target:** `aqp/strategies/notebooks/moskowitz_tsmom.py::MoskowitzTSMOMAlpha`.
**Default params:** `lookback_months=12`, `target_vol=0.40`, `vol_window=60`, `position_cap=2.0`.

### BaltasTrend

**Source:** `trend_following_baltas2020.ipynb`
**Logic:** TSMOM with Baltas vol estimator (mix of close-to-close + Yang-Zhang). Correlation-aware position scaling.
**AQP target:** `aqp/strategies/notebooks/baltas_trend.py::BaltasTrendAlpha`.

### BreakoutTrend

**Source:** `trend_following_breakout.ipynb`
**Logic:** N-period Donchian breakout filter on top of TSMOM signal.
**AQP target:** `aqp/strategies/notebooks/breakout_trend.py::BreakoutTrendAlpha`.

### FXCarry

**Source:** `fx_carry.ipynb`
**Logic:** Long high-yielders / short low-yielders quintile portfolio.
**AQP target:** `aqp/strategies/notebooks/fx_carry.py::FXCarryAlpha`.

### CommodityTermStructure

**Source:** `commodity_term_structure.ipynb`
**Logic:** Koijen-style: long contracts in backwardation, short in contango. Roll yield = (front - second) / second.
**AQP target:** `aqp/strategies/notebooks/commodity_term_structure.py::CommodityTermStructureAlpha`.

### CommodityMomentum

**Source:** `commodity_momentum.ipynb`
**Logic:** Cross-sectional 12-month momentum on Hollstein 2020 commodity universe; long top tercile, short bottom tercile.
**AQP target:** `aqp/strategies/notebooks/commodity_momentum.py::CommodityMomentumAlpha`.

### CommoditySkewness

**Source:** `commodity_skewness.ipynb`
**Logic:** Skewness factor — long lowest-skew, short highest-skew; rebalance monthly.
**AQP target:** `aqp/strategies/notebooks/commodity_skewness.py::CommoditySkewnessAlpha`.

### CommodityIntraCurve

**Source:** `commodity_intra_curve.ipynb`
**Logic:** Along-curve / curve-relative momentum (front - back contracts).
**AQP target:** `aqp/strategies/notebooks/commodity_intra_curve.py::CommodityIntraCurveAlpha`.

### CrushSpreadStatArb

**Source:** `commodity_crush_spread_stat_arb.ipynb`
**Logic:** Soybean crush spread (1 bean = 11 oil + 4.4 meal); ADF + EG cointegration filter; mean-reversion entries when |z| > 2.
**AQP target:** `aqp/strategies/notebooks/crush_spread.py::CrushSpreadStatArbStrategy`. Uses new `aqp/data/cointegration.py`.

### CrackSpreadStatArb

**Source:** `commodity_crack_spread_stat_arb.ipynb`
**Logic:** Petroleum 3-2-1 crack (3 bbl crude → 2 bbl gasoline + 1 bbl heating oil). EG cointegration; z-score reversion.
**AQP target:** `aqp/strategies/notebooks/crack_spread.py::CrackSpreadStatArbStrategy`.

### CommodityBasisMomentum

**Source:** `commodity_basis_momentum.ipynb`
**Logic:** Boons-style: difference between (1st - 2nd contract returns) cross-sectionally signaling momentum in basis.
**AQP target:** `aqp/strategies/notebooks/basis_momentum.py::CommodityBasisMomentumAlpha`.

### CommodityBasisReversal

**Source:** `commodity_basis_reversal.ipynb`
**Logic:** Rossi 2025 basis reversal — short-term mean reversion of basis.
**AQP target:** `aqp/strategies/notebooks/basis_reversal.py::CommodityBasisReversalAlpha`.

### ChineseFuturesTrend

**Source:** `commodity_trend_following_chinese_futures.ipynb`
**Logic:** Li/Zhang/Zhou TSMOM on Chinese-listed commodity futures.
**AQP target:** `aqp/strategies/notebooks/chinese_futures_trend.py::ChineseFuturesTrendAlpha`.

### CrossAssetSkewness

**Source:** `cross_asset_skewness.ipynb`
**Logic:** Baltas cross-asset skew — long lowest-skew assets, short highest-skew across asset classes.
**AQP target:** `aqp/strategies/notebooks/cross_asset_skewness.py::CrossAssetSkewnessAlpha`.

### OvernightReturns

**Source:** `overnight_returns.ipynb`
**Logic:** Knuteson — long overnight returns / short intraday returns.
**AQP target:** `aqp/strategies/notebooks/overnight_returns.py::OvernightReturnsAlpha`.

### ConnorsShortTerm (4 variants)

**Source:** `equity_short_term_trading_connors.ipynb`
**Logic:** Four discrete rule sets:
1. 3 down days + above 200d MA → buy.
2. New 10d lows + above 200d MA → buy.
3. "Double 7's": close < 7d-low and SMA200 rising → buy.
4. Month-end timing + optional down-day filter + 200d MA.
**AQP target:** `aqp/strategies/notebooks/connors.py::ConnorsThreeDownStrategy`, `ConnorsTenDayLowsStrategy`, `ConnorsDoubleSevensStrategy`, `ConnorsMonthEndStrategy`.

### GaoIntradayMomentum

**Source:** `equity_etf_intraday_momentum.ipynb`
**Logic:** Gao 2018 — first 30min return predicts last 30min return; cross-sectional regression on ETF panel; trade last-30min based on first-30min sign.
**AQP target:** `aqp/strategies/notebooks/gao_intraday.py::GaoIntradayMomentumStrategy`.

## Other notable notebook content (analysis methods → framework primitives)

### Realised volatility estimators

**Source:** `realised_volatility.ipynb`
**Implements:** Close-to-close, Parkinson, Garman-Klass, Rogers-Satchell, Yang-Zhang from OHLC.
**AQP target:** `aqp/data/realised_volatility.py` (Phase 1 module).

```python
def parkinson(high, low, period=20):
    # σ²_P = (1 / (4 * ln 2)) * mean(log(H/L)²)
    return np.sqrt((np.log(high/low) ** 2).rolling(period).mean() / (4 * np.log(2)))

def garman_klass(open_, high, low, close, period=20):
    # σ²_GK = mean(0.5 * (log(H/L))² - (2 * ln 2 - 1) * (log(C/O))²)
    term1 = 0.5 * (np.log(high/low) ** 2)
    term2 = (2 * np.log(2) - 1) * (np.log(close/open_) ** 2)
    return np.sqrt((term1 - term2).rolling(period).mean())
```

### Bachelier (Normal model) Greeks

**Source:** `Greeks_under_normal_model.ipynb`
**AQP target:** `aqp/options/normal_model.py`.
**Implements:** Bachelier price + delta + gamma + theta + vega + vanna + volga + veta.

```python
def bachelier_price(F, K, T, sigma, is_call=True):
    d = (F - K) / (sigma * np.sqrt(T))
    sign = 1 if is_call else -1
    return sign * (F - K) * norm.cdf(sign * d) + sigma * np.sqrt(T) * norm.pdf(d)
```

### Inverse options

**Source:** `inverse_option.ipynb`
**AQP target:** `aqp/options/inverse_options.py`.
**Implements:** Deribit-style inverse option PV/Greeks (paid/settled in BTC); IV via `scipy.optimize.brentq`.

### Fisher correlation CI

**Source:** `correlation_confidence_interval.ipynb`
**AQP target:** `aqp/utils/correlation_ci.py` (small).
**Implements:** Fisher z-transform CI for Pearson correlation.

```python
def fisher_corr_ci(r, n, alpha=0.05):
    z = 0.5 * np.log((1 + r) / (1 - r))
    se = 1 / np.sqrt(n - 3)
    z_crit = norm.ppf(1 - alpha/2)
    z_lo, z_hi = z - z_crit * se, z + z_crit * se
    r_lo = (np.exp(2*z_lo) - 1) / (np.exp(2*z_lo) + 1)
    r_hi = (np.exp(2*z_hi) - 1) / (np.exp(2*z_hi) + 1)
    return r_lo, r_hi
```

### Virtue of Complexity (Ridge)

**Source:** `the_virtue_of_complexity_everywhere.ipynb`
**AQP target:** `aqp/ml/models/notebooks/ridge_voc.py::RidgeVoCForecaster`.
**Implements:** Random-feature lift (`P` projections of size `n_features`) + sklearn `Ridge` on the lifted features. Vol-adjusted return labels.
