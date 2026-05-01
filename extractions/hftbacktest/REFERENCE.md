# hftbacktest — Extraction Reference

**Source:** `inspiration/hftbacktest-master/`
**Repo character:** High-frequency LOB backtester (Rust core + Python via Numba).
**Status:** Engine integration deferred — see [_FUTURE_PROMPTS/lob_adapter_prompt.md](../_FUTURE_PROMPTS/lob_adapter_prompt.md). We extract the analytics today.

## What we extract today

### Microstructure features

**Source:** `examples/Market Making with Alpha - Order Book Imbalance.ipynb`, `examples/Working with Market Depth and Trades.ipynb`, `py-hftbacktest/hftbacktest/binding.py` (event schema)
**AQP target:** `aqp/data/microstructure.py` (Phase 1 module).

```python
def order_book_imbalance(bid_qty, ask_qty):
    # OBI = (Q_bid - Q_ask) / (Q_bid + Q_ask) ∈ [-1, 1]
    return (bid_qty - ask_qty) / (bid_qty + ask_qty + 1e-12)

def microprice(bid_price, ask_price, bid_qty, ask_qty):
    # MP = (P_ask * Q_bid + P_bid * Q_ask) / (Q_bid + Q_ask)
    return (ask_price * bid_qty + bid_price * ask_qty) / (bid_qty + ask_qty + 1e-12)

def depth_slope(prices, qtys):
    # Linear regression of cumulative qty vs |price - mid|
    ...

def weighted_spread(bid_prices, ask_prices, bid_qtys, ask_qtys, depth_levels=5):
    # Quote-weighted spread across multiple depth levels
    ...

def vpin(buy_volume, sell_volume, n_buckets=50):
    # Volume-synchronized probability of informed trading (Easley/Lopez/O'Hara)
    ...

def trade_flow_imbalance(buy_vol, sell_vol):
    # TFI = sum(buy_vol - sell_vol) over rolling window, normalized
    ...
```

### HFT-aware metrics

**Source:** `py-hftbacktest/hftbacktest/stats/metrics.py`
**AQP target:** `aqp/backtest/hft_metrics.py` (Phase 1 module).

```python
class HftMetrics:
    """Sample-aware metrics for HFT backtests."""

    @staticmethod
    def sample_aware_sharpe(returns: pd.Series, samples_per_day: int) -> float:
        # Annualized using actual sample frequency, not 252
        days_per_year = 365  # crypto convention; equity uses 252
        return returns.mean() / returns.std() * np.sqrt(samples_per_day * days_per_year)

    @staticmethod
    def max_position(positions: pd.Series) -> float:
        return positions.abs().max()

    @staticmethod
    def mean_leverage(position_values: pd.Series, equity: pd.Series) -> float:
        return (position_values.abs() / equity.abs()).mean()

    @staticmethod
    def return_over_trade(total_return: float, n_trades: int) -> float:
        return total_return / max(n_trades, 1)

    @staticmethod
    def fill_ratio(fills: int, orders: int) -> float:
        return fills / max(orders, 1)
```

## LOB strategies (5 stubs) — port to `aqp/strategies/hft/`

All subclass new `aqp/strategies/lob.py::LobStrategy` ABC. Engine integration `NotImplementedError` until adapter ships.

### GLFTMM

**Source:** `examples/GLFT Market Making Model and Grid Trading.ipynb`
**Logic:** Guéant-Lehalle-Fernandez-Tapia closed-form optimal market making.
**AQP target:** `aqp/strategies/hft/glft_mm.py::GLFTMM`.

### GridMM

**Source:** `examples/High-Frequency Grid Trading.ipynb` + `... - Simplified from GLFT.ipynb`
**Logic:** Grid quoting around mid price.
**AQP target:** `aqp/strategies/hft/grid_mm.py::GridMM`.

### ImbalanceAlphaMM

**Source:** `examples/Market Making with Alpha - Order Book Imbalance.ipynb`
**Logic:** Skew quotes by order book imbalance.
**AQP target:** `aqp/strategies/hft/imbalance_alpha_mm.py::ImbalanceAlphaMM`.

### BasisAlphaMM

**Source:** `examples/Market Making with Alpha - Basis.ipynb`
**Logic:** Cross-instrument basis as fair-value alpha.
**AQP target:** `aqp/strategies/hft/basis_alpha_mm.py::BasisAlphaMM`.

### QueueAwareMM

**Source:** `examples/Queue-Based Market Making in Large Tick Size Assets.ipynb`
**Logic:** Account for queue position in fill probability when quoting.
**AQP target:** `aqp/strategies/hft/queue_aware_mm.py::QueueAwareMM`.

## Sample data ingestion

### LOB sample loader

**Source:** `examples/usdm/btcusdt_*.gz` (Binance Futures depth dump)
**AQP target:** `aqp/data/pipelines/lob_sample_loader.py` (Phase 8). Decodes Binance Futures depth events to Iceberg `aqp_lob.btcusdt_samples` table.

## Reference event schema (for AQP feature compute)

From `py-hftbacktest/hftbacktest/__init__.py` flags:

- `DEPTH_EVENT` — book update
- `TRADE_EVENT` — trade tick
- `DEPTH_SNAPSHOT_EVENT` — full book snapshot
- `ADD_ORDER_EVENT`, `CANCEL_ORDER_EVENT`, `MODIFY_ORDER_EVENT` (L3)

Our `aqp/data/microstructure.py` consumes pre-aggregated bid/ask price/qty arrays; raw event handling lives in the future LOB adapter.
