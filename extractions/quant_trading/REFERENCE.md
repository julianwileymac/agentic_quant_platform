# quant-trading-master - Extraction Reference

**Source:** `inspiration/quant-trading-master/`
**Repo character:** Script-first educational quant trading collection (mostly pandas + matplotlib), with technical-indicator backtests, stat-arb examples, and small quantamental projects. Paths and data sources are often local-machine specific and need normalization before framework use.

## Strategy ports (10) - map to `aqp/strategies/`

### DualThrustAlpha

**Source:** `Dual Thrust backtest.py`
**Logic:** Opening-range breakout with prior-range thresholds.
**AQP target:** `aqp/strategies/dual_thrust_alpha.py::DualThrustAlpha`

### LondonBreakoutAlpha

**Source:** `London Breakout backtest.py`
**Logic:** Session-range breakout around London open.
**AQP target:** `aqp/strategies/london_breakout_alpha.py::LondonBreakoutAlpha`

### HeikinAshiAlpha

**Source:** `Heikin-Ashi backtest.py`
**Logic:** Heikin-Ashi transformed candles and reversal/momentum triggers.
**AQP target:** `aqp/strategies/heikin_ashi_alpha.py::HeikinAshiAlpha`

### AwesomeOscillatorAlpha

**Source:** `Awesome Oscillator backtest.py`
**Logic:** AO momentum transitions and crossover-style entries.
**AQP target:** `aqp/strategies/awesome_oscillator_alpha.py::AwesomeOscillatorAlpha`

### BollingerWAlpha

**Source:** `Bollinger Bands Pattern Recognition backtest.py`
**Logic:** Bollinger-band pattern recognition and reversal entries.
**AQP target:** `aqp/strategies/bollinger_w_alpha.py::BollingerWAlpha`

### RsiPatternAlpha

**Source:** `RSI Pattern Recognition backtest.py`
**Logic:** RSI oscillator with pattern-layer confirmation.
**AQP target:** `aqp/strategies/rsi_pattern_alpha.py::RsiPatternAlpha`

### ParabolicSARAlpha

**Source:** `Parabolic SAR backtest.py`
**Logic:** Parabolic SAR trend-flip entries.
**AQP target:** `aqp/strategies/parabolic_sar_alpha.py::ParabolicSARAlpha`

### ShootingStarAlpha

**Source:** `Shooting Star backtest.py`
**Logic:** Candlestick shooting-star reversal signal.
**AQP target:** `aqp/strategies/shooting_star_alpha.py::ShootingStarAlpha`

### PairsTradingAlphaModel (related)

**Source:** `Pair trading backtest.py`
**Logic:** Cointegration residual z-score mean reversion.
**AQP target:** `aqp/strategies/pairs_alpha.py::PairsTradingAlphaModel`

### OilMoneyRegressionAlpha

**Source:** `Oil Money project/Oil Money Trading backtest.py`
**Logic:** Regression residual mean reversion of petrocurrency vs oil proxy.
**AQP target:** `aqp/strategies/oil_money_alpha.py::OilMoneyRegressionAlpha`

## ML and split patterns

### Chronological holdout split

**Source:** `Monte Carlo project/Monte Carlo backtest.py`
**Pattern:** Time-ordered split (`shuffle=False`) for no-lookahead training/testing.
**AQP target:** `aqp/ml/splits.py` and `aqp/ml/walk_forward.py`

### Rolling macro/FX regression split

**Source:** `Oil Money project/Oil Money CAD.py`, `Oil Money COP.py`, `Oil Money NOK.py`
**Pattern:** Date-sliced train/validation/inference windows on macro panels.
**AQP target:** `aqp/ml/splits.py::quarterly_point_in_time_split` (or equivalent helper)

## Data cleaning and preprocessing patterns

### Multi-source panel clean/merge

**Source:** `Smart Farmers project/cleanse data.py`
**Pattern:** Column normalization, merge-on-key/date, duplicate dropping, missing-value handling.
**AQP target:** `aqp/ml/processors.py` and `aqp/data/pipelines/dataset_preset_pipelines.py`

```python
def clean_panel(df):
    df = df.rename(columns=lambda c: c.strip().lower().replace(" ", "_"))
    df = df.drop_duplicates()
    for col in ("timestamp", "date", "datadate"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df
```

## Backtest/evaluation snippets of interest

### Residual z-score entry/exit

**Source:** `Pair trading backtest.py`
**AQP mapping:** `aqp/data/cointegration.py` + strategy-level entry/exit thresholds

```python
spread = y - beta * x
z = (spread - spread.rolling(window).mean()) / spread.rolling(window).std()
long_entry = z < -2.0
short_entry = z > 2.0
```

### Portfolio/risk metric block

**Source:** `Heikin-Ashi backtest.py`, `Awesome Oscillator backtest.py`
**AQP mapping:** `aqp/backtest/metrics.py` and `aqp/backtest/hft_metrics.py`
**Notes:** Keep framework-standard summary keys (`sharpe`, `sortino`, `max_drawdown`, `calmar`, `turnover`).

## Data/pipeline extraction opportunities

### Quant Trading sample datasets

High-value sample inputs to expose via dataset presets:

1. Oil Money panel (`Oil Money project/data/*.csv`)
2. Smart Farmers cleaned panel (`Smart Farmers project/data/*.csv`)
3. Monte Carlo input series (`data/*.csv`)

**AQP target:** `aqp/data/dataset_presets.py` + `aqp/data/pipelines/dataset_preset_pipelines.py`

## Caveats

- Scripts assume frictionless execution (no slippage/fees/liquidity constraints unless manually added).
- Some examples use deprecated data connectors and local absolute paths.
- Treat scripts as algorithm/pattern references, not production modules.
