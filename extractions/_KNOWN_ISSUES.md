# Known Issues — Inspiration Rehydration

Items deliberately not fixed during the rehydration, with rationale.

## Notebooks-master (vivace dependency)

The `notebooks-master` strategies (Moskowitz, Baltas, FX carry, commodity term structure, etc.) all depend on the **proprietary `vivace` library** for the actual backtest engine, futures contract universes, and `Performance` / `PerfStats` math. We re-implement the **signal math** against AQP's bar interface, but **cannot bit-for-bit reproduce the published PnL** because the contract roll definitions, position sizing constants, and vol estimator window choices differ.

**What we keep:** the rule logic, parameter defaults from the papers, and references to the citing papers.

**What we lose:** exact reproducibility of figures in the original notebooks.

**Affected assets:** `MoskowitzTSMOM`, `BaltasTrend`, `BreakoutTrend`, `FXCarry`, `CommodityTermStructure`, `CommodityMomentum`, `CommoditySkewness`, `CommodityIntraCurve`, `CrushSpreadStatArb`, `CrackSpreadStatArb`, `CommodityBasisMomentum`, `CommodityBasisReversal`, `ChineseFuturesTrend`, `CrossAssetSkewness`, `OvernightReturns`, `GaoIntradayMomentum`.

## Stock-Prediction-Models (TF1 → PyTorch ports)

The SPM repo is TensorFlow 1.x graph-style code. We port to PyTorch via `aqp/ml/models/spm/_torch_base.py`. **Numerics will not match** because:

- TF1 used `tf.contrib.rnn` cell variants with different default initializations.
- Optimizer defaults (Adam beta_1, beta_2, epsilon) differ.
- Dropout vs DropConnect distinctions in originals are flattened.
- BERT model uses a small distilled config (~2 layers, 64 hidden) so it trains on CPU; not directly comparable to upstream BERT-base.

**What we keep:** architecture topology, layer counts, and hyperparameter defaults where they map cleanly.

**What we lose:** ability to load upstream TF1 weights.

## QTradeX (duplicate class names)

`harmonica.py` and `parabolic_ten.py` both define `class ParabolicSARBot`. We collapse them into one canonical `ParabolicSARBot` in `aqp/strategies/qtradex/parabolic_sar.py`, taking the more featureful `harmonica.py` variant (six PSARs + four EMAs).

`heiken_ashi.py` and `ema_cross.py` both define `class EmaCross` but with different logic. We keep both as `EmaCrossSMA` (from `ema_cross.py`, SMA-envelope) and `EmaCrossHA` (from `heiken_ashi.py`, Heikin-Ashi).

The `qi_indicators_test.py` strategy uses an undefined `random` symbol — we treat it as **indicator survey only** and do not register it as a strategy.

## QTradeX `qi_indicators_test.py` is incomplete

The original `strategy()` body references an undefined `random` symbol. We document the indicators it surveys (in `extractions/qtradex/REFERENCE.md`) but **do not port it as a runnable strategy**.

## Analyzingalpha (FTX / Backtrader)

- The FTX adapter under `inspiration/analyzingalpha-master/2022-02-24-ftx-rest-api-python/` is **deliberately not integrated** — the exchange shut down in April 2025. Code remains in `inspiration/` for historical reference only.
- The repo's strategies are predominantly Backtrader-based. We **do not add Backtrader as an AQP dependency**. Strategy logic is re-implemented natively against `IAlphaModel` / `FrameworkAlgorithm`. Any execution-stack quirks (e.g., Backtrader bracket order semantics) are documented inline.

## Stock-Analysis-Engine (Keras 2 dependency)

`analysis_engine/ai/build_regression_dnn.py` uses Keras 2 + `KerasRegressor` from `tensorflow.keras.wrappers.scikit_learn` (deprecated in Keras 3 / TF 2.16+). We port to PyTorch in `aqp/ml/models/sae/keras_mlp_regressor.py` keeping the layer-count and dropout topology but using PyTorch primitives.

## hftbacktest (LOB engine)

The full LOB simulation engine requires Numba + a Rust extension built via Maturin (`hftbacktest._hftbacktest`). We add a stub `LobStrategy` ABC and the 5 strategies that target it (`GLFTMM`, `GridMM`, etc.) but **the engine integration is deferred** — see [_FUTURE_PROMPTS/lob_adapter_prompt.md](_FUTURE_PROMPTS/lob_adapter_prompt.md). Strategies are listed in the UI as "Engine pending".

## SPM RL agents (TF1 graph-mode)

The SPM "deep-learning agents" use TF1 graph-mode Q-networks. We port to PyTorch using `nn.Module` Q-networks. The `EvolutionStrategyAgent` is more straightforward (just a numpy-based perturbation loop) and ports without changes.

## Akquant (Rust core dependency)

The `akquant` runtime uses a Rust core; we **do not** import `akquant` itself. Strategy logic and portfolio rebalancing patterns are re-implemented against `FrameworkAlgorithm` / `IPortfolioConstructionModel`. The `FactorEngine` expression language is mirrored in `aqp/data/factor_expression.py` using Polars.

## Akquant `feed_adapter` multi-frequency

`akquant`'s daily-vs-intraday alignment is engine-specific. We document the alignment requirements in the per-strategy notes but **do not add a multi-frequency engine in this rehydration**. Strategies needing intraday + daily alignment receive both as separate `pd.DataFrame` inputs.

## Network-bound dataset presets

The `china_a_shares_top200`, `crypto_majors_intraday`, `etf_intraday_panel`, `commodity_futures_panel`, `fred_macro_basket`, and `finviz_screener` presets reach external APIs. The platform-smoke tests **do not exercise these** — they use synthetic fixtures only. To exercise live ingestion run the Celery tasks manually with appropriate API keys configured in `.env`.

## Ingestion of `lob_btcusdt_sample`

The hftbacktest sample feed format is `gzip` of a venue-specific schema. Our `lob_sample_loader.py` decodes Binance Futures depth events; other formats (Bybit fused, Hyperliquid, MEXC) are documented but not implemented in this pass. The sample preset registration covers the Binance one only.
