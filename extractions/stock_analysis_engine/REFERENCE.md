# stock-analysis-engine — Extraction Reference

**Source:** `inspiration/stock-analysis-engine-master/analysis_engine/`
**Repo character:** Redis/S3-cached pricing pipeline + indicator-driven single-symbol backtest. Heavy on `spylunking` logging (we drop it for stdlib `logging`).

## Strategies (3) — port to `aqp/strategies/sae/`

### StockAnalysisEngineAdapter

**Source:** `algo.py::BaseAlgo` + `handle_data` + `process`
**Logic:** Generic per-bar callback loop — `process(dataset)` sets `should_buy`/`should_sell` from indicator readouts.
**AQP target:** `aqp/strategies/sae/sae_adapter.py::StockAnalysisEngineAdapterStrategy`. Wraps a user-provided `process_fn` callable into an `IStrategy`.

### IndicatorVoteStrategy

**Source:** `algo.py::trade_off_indicator_buy_and_sell_signals`
**Logic:** Count buy-signal indicators vs sell-signal indicators; trade when count exceeds `min_buy_indicators` or `min_sell_indicators`.
**AQP target:** `aqp/strategies/sae/indicator_vote.py::IndicatorVoteAlpha`. Generic over IndicatorZoo specs.
**Params:** `indicator_specs: list[str]`, `min_buy_count: int = 3`, `min_sell_count: int = 3`.

### OptionSpreadStrategy

**Source:** `build_option_spread_details.py` + `build_entry_call_spread_details.py`
**Logic:** Vertical option spread P&L math; entry/exit leg pricing.
**AQP target:** `aqp/strategies/sae/option_spread.py::OptionSpreadStrategy`. Uses `aqp/options/spreads.py` (Phase 1).

## Notable utilities

### Vertical spread math

**Source:** `build_option_spread_details.py`
**AQP target:** `aqp/options/spreads.py`.

```python
def vertical_spread_details(
    long_strike: float, short_strike: float,
    long_premium: float, short_premium: float,
    is_call: bool = True,
):
    width = abs(long_strike - short_strike)
    net_debit = long_premium - short_premium
    max_profit = width - net_debit if is_call else net_debit
    max_loss = net_debit if is_call else width - net_debit
    breakeven = (long_strike + net_debit) if is_call else (long_strike - net_debit)
    return {
        "width": width, "net_debit": net_debit,
        "max_profit": max_profit, "max_loss": max_loss,
        "breakeven": breakeven, "mid": (max_profit - max_loss) / 2,
    }
```

### Options expiration calendar

**Source:** `options_dates.py`
**AQP target:** `aqp/utils/options_calendar.py` (small) or absorb into existing exchange-hours module.
**Implements:** Monthly expiration (third Friday) calculator with US holiday handling.

### Finviz screener (HTML scrape)

**Source:** `finviz/fetch_api.py`
**AQP target:** `aqp/data/pipelines/finviz_screener.py` (Phase 8 pipeline).
**Note:** Scraper-fragile; respects ToS rate limits.
