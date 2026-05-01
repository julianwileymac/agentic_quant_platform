# HFT (LOB) Strategies — Engine Pending

The strategies in this folder require the LOB backtest engine, which is
deferred. See `extractions/_FUTURE_PROMPTS/lob_adapter_prompt.md` for
the future-work prompt.

Once the LOB adapter ships, configs in this directory will follow this
shape:

```yaml
strategy:
  class: GLFTMM
  module_path: aqp.strategies.hft.alphas
  kwargs:
    gamma: 0.1
    sigma: 0.01
    kappa: 1.5
    order_size: 1.0
    max_position: 10.0
backtest:
  class: LobBacktestEngine          # not yet implemented
  module_path: aqp.backtest.hft
  kwargs:
    dataset_preset: lob_btcusdt_sample
    latency_profile: fast_co_located
    queue_model: power_law_2
```
