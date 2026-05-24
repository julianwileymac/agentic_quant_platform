# RL Market Dynamics Modeling (Phase 6)

Reference docs for the slice-and-merge regime labeller and its
consumers in `aqp_rl`.

## Overview

The market-dynamics framework labels every bar in a price series
with a regime ID (default 4 regimes: strong-down / weak-down /
sideways / strong-up). The labels feed:

- `RegimeAwareObservation` — appends a one-hot regime vector to the
  RL agent's observation.
- `RegimeStratifiedEvaluation` — runs the trained policy and
  decomposes per-regime performance for the RL Lab dashboard.

## Pipeline

1. **Butterworth filter** on the indicator column (default
   `close`). Causal `lfilter` to avoid look-ahead.
2. **Turning-point detection** — bars where the filtered pct-return
   sign flips mark candidate segment boundaries.
3. **Segment merging** — segments below `min_length_limit` are
   merged with their neighbour so every regime has a stable
   estimation window.
4. **Per-segment slope** — linear regression of the filtered
   indicator inside each segment.
5. **Labelling** — quantile (default) or fixed-threshold buckets.

## Modules

| File | Class | Purpose |
| --- | --- | --- |
| [`aqp/analysis/flows/market_dynamics_modeling.py`](../aqp/analysis/flows/market_dynamics_modeling.py) | `slice_and_merge_regime_flow` | Analysis flow; emits per-bar labels |
| [`aqp_rl/src/aqp_rl/observations/regime.py`](../aqp_rl/src/aqp_rl/observations/regime.py) | `RegimeAwareObservation` | One-hot observation appendage |
| [`aqp_rl/src/aqp_rl/experiments/regime_stratified.py`](../aqp_rl/src/aqp_rl/experiments/regime_stratified.py) | `RegimeStratifiedEvaluation` | Per-regime metric breakdown |

## Usage

```python
from aqp.analysis.base import FlowContext
from aqp.analysis.flows.market_dynamics_modeling import (
    SliceAndMergeRegimeParams,
    slice_and_merge_regime_flow,
)

params = SliceAndMergeRegimeParams(
    indicator_column="close",
    dynamic_number=4,
    min_length_limit=12,
    labeling_method="quantile",
)
result = slice_and_merge_regime_flow(df, params, FlowContext(run_id="…"))
labels = [row["label"] for row in result.rows]
```

The labels are surfaced into the RL pipeline via
`RegimeAwareObservation(labels=labels)` and the matching evaluation
through `RegimeStratifiedEvaluation(n_regimes=4, regime_labels=labels)`.

## Hard rule alignment

- Hard rule 23: analysis-spec lifecycle goes through
  `AnalysisRuntime`. The flow registers via `register_analysis_flow`.
- Hard rule 21: gold-tier writes via `iceberg_catalog.append_arrow`
  to `aqp_gold_analysis_market_dynamics_modeling`.
- Hard rule 25: flow body has no direct LLM calls.

## Acceptance

- [Phase 6 tests](../aqp_rl/tests/mdm/) verify:
  - `slice_and_merge_regime_flow` produces ≥1 segment on a
    trending+sideways+downtrend synthetic series.
  - `RegimeAwareObservation` emits the expected one-hot shape.
  - `RegimeStratifiedEvaluation` breaks performance down per regime.
