# RL policy backbones

> Transformer / RNN / Autoencoder / PatchTST feature trunks for the
> AQP RL policies. Registered through the
> [`RLComponent`](../aqp/rl/core/base.py) metaclass with
> `rl_kind='rl_policy_backbone'`.

## Backbones

| Class | Source | Use case |
| --- | --- | --- |
| [`TransformerBackbone`](../aqp/rl/policies/backbones/transformer.py) | Self-attention encoder over the lookback window | Default for medium sequence (30-100 bars) |
| [`RecurrentBackbone`](../aqp/rl/policies/backbones/recurrent.py) | LSTM / GRU / RNN cell (configurable) | Causal, memory-efficient, anti-bidirectional default |
| [`AutoencoderBackbone`](../aqp/rl/policies/backbones/autoencoder.py) | MLP encoder bottleneck | High-dim observation (1000+ features) compression |
| [`PatchTSTBackbone`](../aqp/rl/policies/backbones/patchtst.py) | Patch-tokenised Transformer (Nie 2023) | Long-horizon (252+ bars) — avoids token explosion |

## Wiring through SB3

```yaml
agent:
  class: SB3Adapter
  module_path: aqp.rl.agents.sb3_adapter
  kwargs:
    algorithm: PPO
    policy: MlpPolicy
    policy_kwargs:
      features_extractor_class: aqp.rl.policies.feature_extractors.BackboneFeaturesExtractor
      features_extractor_kwargs:
        backbone_alias: TransformerBackbone
        sequence_length: 30
        input_features: 32
        features_dim: 128
        backbone_kwargs:
          n_heads: 4
          n_layers: 2
          d_ff: 256
          dropout: 0.1
```

## Wiring through CleanRL

The [`CleanRLAdapter`](../aqp/rl/agents/cleanrl_adapter.py) wraps the
backbone via
[`build_backbone_from_alias`](../aqp/rl/policies/feature_extractors.py):

```python
from aqp.rl.policies import build_backbone_from_alias

trunk = build_backbone_from_alias(
    "RecurrentBackbone",
    input_features=20,
    sequence_length=30,
    output_dim=128,
    backbone_kwargs={"cell": "lstm", "hidden_size": 128, "num_layers": 2},
)
```

## Shipped example specs

Four reference specs live under
[`configs/rl/policies/`](../configs/rl/policies):

- [`transformer_stock_trading.yaml`](../configs/rl/policies/transformer_stock_trading.yaml)
  — PPO + Transformer over StockTradingEnv.
- [`recurrent_portfolio.yaml`](../configs/rl/policies/recurrent_portfolio.yaml)
  — SAC + LSTM over PortfolioAllocationEnv.
- [`autoencoder_marketmaking.yaml`](../configs/rl/policies/autoencoder_marketmaking.yaml)
  — PPO + Autoencoder over MarketMakingEnv.
- [`patchtst_execution.yaml`](../configs/rl/policies/patchtst_execution.yaml)
  — PPO + PatchTST over OptimalExecutionEnv.

## Adding a new backbone

See [the cursor rule](../.cursor/rules/policy-backbones.mdc) for the
canonical checklist.

## See also

- [aqp_docs/agentic-rl.md](agentic-rl.md)
- [Hard rule 37 in AGENTS.md](../AGENTS.md)
