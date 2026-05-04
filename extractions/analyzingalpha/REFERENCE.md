# analyzingalpha - Extraction Reference

**Source:** `inspiration/analyzingalpha-master/`
**Upstream:** <https://github.com/leosmigel/analyzingalpha>
**Repo character:** Blog-driven strategy examples with mixed code quality and partial LFS objects; extraction relies on file names, notebooks, and article semantics rather than strict line-by-line ports.

## Strategy ports (8) - map to `aqp/strategies/analyzingalpha/`

### SectorMomentumAlpha

**Source:** `2019-11-06-sector-momentum/sector-momentum.py`
**Logic:** Cross-sectional momentum on sector ETFs (XLK, XLF, XLE, etc.); long top quartile, short bottom.
**AQP target:** `aqp/strategies/analyzingalpha/sector_momentum.py::SectorMomentumAlpha`.

### SectorRSIAlpha

**Source:** `2020-10-09-relative-strength-index/sector-rsi-strategy.py`
**Logic:** RSI(14) cross above 30 → buy, below 70 → sell on sector ETFs.
**AQP target:** `aqp/strategies/analyzingalpha/sector_rsi.py::SectorRSIAlpha`.

### EquitiesStopLossStrategy

**Source:** `2020-01-05-stop-loss-for-stocks/equities-stop-loss.py`
**Logic:** Per-equity trailing stops at fixed pct of recent high.
**AQP target:** `aqp/strategies/analyzingalpha/stop_loss.py::EquitiesStopLossStrategy`. Uses `aqp/strategies/risk_models.py::TrailingStopRiskManagementModel`.

### EquitiesBracketStrategy

**Source:** `2020-01-10-risk-reward-ratio-for-stocks/equities-bracket-order.py`
**Logic:** Bracket orders — entry + take-profit + stop-loss with fixed R:R ratio.
**AQP target:** `aqp/strategies/analyzingalpha/bracket.py::EquitiesBracketStrategy`.

### CryptoPriceShearMRAlpha

**Source:** `2021-09-23-crypto-price-shear-algo-trading-strategy/crypto-price-shear-mean-reversion-strategy.ipynb`
**Logic:** "Shear" transform = price minus rolling regression line; mean-reversion on extreme deviations.
**AQP target:** `aqp/strategies/analyzingalpha/crypto_shear.py::CryptoPriceShearMRAlpha`.

### StatArbPairsStrategy

**Source:** `alpaca/statistically-significant/statarb_part_one.py` + `_two.py`
**Logic:** Engle-Granger cointegration; trade z-score reversion of residual.
**AQP target:** `aqp/strategies/analyzingalpha/statarb_pairs.py::StatArbPairsStrategy`. Uses `aqp/data/cointegration.py`.

### UnemploymentMacroOverlayStrategy

**Source:** `alpaca/unemployment-algo/alpaca-backtrader-fred.py`
**Logic:** FRED unemployment rate as macro filter — only go long when unemployment trend is improving.
**AQP target:** `aqp/strategies/analyzingalpha/unemployment_overlay.py::UnemploymentMacroOverlayStrategy`. Uses `fred_macro_basket` dataset preset.

### ConnorsRSIAlpha (companion)

**Source:** `2019-09-26-backtrader-backtesting-trading-strategies/backtrader-conners-rsi-strategy.py`
**Logic:** Connors RSI = 1/3 RSI + 1/3 RSI(streak) + 1/3 PercentRank(roc).
**AQP target:** `aqp/strategies/analyzingalpha/connors_rsi.py::ConnorsRSIAlpha`.

## Pattern detection utilities

### Swing extrema and chart pattern matchers

**Source:** `2020-04-18-algorithmic-chart-pattern-detection/extrema.py` + `pattern-recognition.py`
**AQP target:** `aqp/data/patterns.py`
**Implements:** `find_swing_highs(close, window)`, `find_swing_lows(...)`, `detect_head_and_shoulders`, `detect_double_top`, `detect_double_bottom`.

```python
def find_swing_highs(close: pd.Series, window: int = 5) -> pd.Series:
    # Local max within rolling 2*window+1 window
    return (close == close.rolling(2*window+1, center=True).max()).astype(int)

def detect_double_top(close, window=5, tolerance=0.02):
    highs = find_swing_highs(close, window)
    # find consecutive swing highs within tolerance pct
    ...
```

## Data and macro overlays

### FRED macro data flow

**Source:** `alpaca/unemployment-algo/alpaca-backtrader-fred.py`
**Pattern:** Pull macro series, align to market calendar, and use as risk-on/risk-off filter.
**AQP mapping:** `fred_macro_basket` preset and macro-overlay strategy adapters.

### Sector ETF panel assumptions

**Source:** sector momentum and RSI examples
**Pattern:** Fixed sector ETF universe (`XLK`, `XLF`, `XLE`, etc.) with monthly/weekly rebalance cadence.
**AQP mapping:** strategy YAML defaults + universe selector presets.

## Caveats

- Several upstream entries are article snippets, not hardened package modules.
- LFS pointers and notebook drift mean extraction is "semantic parity", not literal source parity.
- Backtrader/Alpaca glue is converted to AQP interfaces (`Symbol`, strategy contracts, and backtest engines).
