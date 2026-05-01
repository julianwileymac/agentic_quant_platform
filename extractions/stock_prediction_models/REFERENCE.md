# Stock-Prediction-Models — Extraction Reference

**Source:** `inspiration/Stock-Prediction-Models-master/`
**Upstream:** https://github.com/huseinzol05/Stock-Prediction-Models

## Repo character

Large catalog of forecasting and RL agents written in TF1.x graph style. Two big sub-trees:

- `deep-learning/` — ~30 forecaster architectures (LSTM, GRU, Transformer, Attention, BERT, TCN, Conv1D, etc.).
- `agent/` — ~25 RL agents (DQN families, A3C, PPO, evolution strategy, policy gradient, actor-critic).

## AQP target mapping

All forecasters port to `aqp/ml/models/spm/<name>.py` on top of `aqp/ml/models/spm/_torch_base.py::TorchForecasterBase` (PyTorch). All RL agents port to `aqp/rl/agents/spm/<name>.py` on top of `aqp/rl/agents/spm/_base.py::BaseRLAgent`.

YAMLs go to `configs/ml/spm/<name>.yaml` and `configs/rl/spm/<name>.yaml` referencing existing `StockTradingEnv` / `PortfolioAllocationEnv`.

## ML forecasters (port to PyTorch)

### LSTMForecaster

**Source:** `deep-learning/1.lstm.ipynb`
**Architecture:** Single LSTM layer + Dense head; window length 5; 30 epochs default.
**AQP target:** `aqp/ml/models/spm/lstm_forecaster.py::LSTMForecaster`.
**Test selected:** Yes — Phase 10 ML training smoke test trains this for 2 epochs on synthetic bars.
**Hyperparameters:** `seq_len=5`, `hidden_size=128`, `num_layers=1`, `dropout=0.0`, `lr=1e-3`, `epochs=30`.

```python
class LSTMForecaster(TorchForecasterBase):
    def build(self):
        self.lstm = nn.LSTM(self.n_features, self.hidden_size, batch_first=True)
        self.head = nn.Linear(self.hidden_size, 1)
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])
```

### BidirectionalLSTM

**Source:** `deep-learning/2.bidirectional-lstm.ipynb`
**Architecture:** `nn.LSTM(..., bidirectional=True)` + Dense head.
**AQP target:** `aqp/ml/models/spm/bidirectional_lstm.py::BidirectionalLSTM`.

### LSTMAttention

**Source:** `deep-learning/4.lstm-2path.ipynb` (and `12.lstm-attention.ipynb`)
**Architecture:** LSTM + scaled-dot-product attention pooling over the sequence.
**AQP target:** `aqp/ml/models/spm/lstm_attention.py::LSTMAttention`.

### StackedLSTM

**Source:** `deep-learning/3.lstm-vanilla.ipynb` (multi-layer variant)
**Architecture:** `nn.LSTM(..., num_layers=2-3)`.
**AQP target:** `aqp/ml/models/spm/stacked_lstm.py::StackedLSTM`.

### GRUForecaster / BidirectionalGRU / VanillaRNN

**Source:** `deep-learning/{6.gru.ipynb, 8.gru-vanilla.ipynb, 11.bidirectional-gru.ipynb}`
**AQP targets:** `aqp/ml/models/spm/{gru_forecaster,bidirectional_gru,vanilla_rnn}.py`.

### LSTMGRUHybrid

**Source:** `deep-learning/16.lstm-gru-hybrid.ipynb`
**Architecture:** Stacked LSTM → stacked GRU → Dense.
**AQP target:** `aqp/ml/models/spm/lstm_gru_hybrid.py::LSTMGRUHybrid`.

### TCNForecaster

**Source:** Inferred / `deep-learning/24.byte-net.ipynb`-style dilated convs.
**Architecture:** Dilated 1D causal convolutions (TCN), 3 blocks of `Conv1d(kernel=2, dilation=2^k)` with residual.
**AQP target:** `aqp/ml/models/spm/tcn_forecaster.py::TCNForecaster`.

### Conv1DForecaster

**Source:** `deep-learning/9.dilated-cnn-seq2seq.ipynb` (simplified)
**Architecture:** Conv1D + GAP + Dense.
**AQP target:** `aqp/ml/models/spm/conv1d_forecaster.py::Conv1DForecaster`.

### TransformerForecaster

**Source:** `deep-learning/22.transformer.ipynb`
**Architecture:** `nn.TransformerEncoder(num_layers=2, d_model=64, nhead=4)` + Dense head, positional encoding.
**AQP target:** `aqp/ml/models/spm/transformer_forecaster.py::TransformerForecaster`.

### AttentionOnlyForecaster

**Source:** `deep-learning/14.attention-is-all-you-need.ipynb` (cut-down)
**Architecture:** Single multi-head self-attention block.
**AQP target:** `aqp/ml/models/spm/attention_only.py::AttentionOnlyForecaster`.

### BERTForecaster (CPU-friendly distilled)

**Source:** `deep-learning/27.bert.ipynb`
**Architecture:** **Small distilled config**: 2 transformer encoder layers, hidden 64, 4 heads. Not vanilla BERT — sized to actually train on CPU.
**AQP target:** `aqp/ml/models/spm/bert_forecaster.py::BERTForecaster`.

### Classical (no PyTorch)

- **ARIMAForecaster** — `aqp/ml/models/spm/arima_forecaster.py` using `statsmodels.tsa.arima.model.ARIMA`. Source: `deep-learning/2.arima-forecasting/`.
- **ProphetForecaster** — `aqp/ml/models/spm/prophet_forecaster.py` using `prophet` (optional dep). Source: `deep-learning/9.facebook-prophet/`.
- **GARCHForecaster** — `aqp/ml/models/spm/garch_forecaster.py` using `arch.arch_model`. Source: `monte-carlo/`-adjacent and `deep-learning/`.

### Bayesian

- **BayesianRidgeForecaster** — `aqp/ml/models/spm/bayesian_ridge.py` using `sklearn.linear_model.BayesianRidge`. Source: `deep-learning/14.simple-monte-carlo.ipynb` lineage.
- **MonteCarloDropoutForecaster** — `aqp/ml/models/spm/mc_dropout.py` — LSTM with `dropout` enabled at inference for predictive variance. Source: `monte-carlo/`.

## RL agents (port to PyTorch nn.Module)

All ride on `aqp/rl/agents/spm/_base.py::BaseRLAgent` which exposes `train(env, total_timesteps)` and `act(obs)`. Compatible with existing `train_from_config` via `@register("Name")`.

### DQNAgent

**Source:** `agent/4.deep-q-learning-agent.ipynb`
**Architecture:** MLP Q-network (`obs_dim → 256 → 256 → action_dim`), epsilon-greedy with linear decay, replay buffer (10000 transitions), target network refreshed every 1000 steps, gamma=0.99.
**AQP target:** `aqp/rl/agents/spm/dqn.py::DQNAgent`.

### DoubleDQNAgent

**Source:** `agent/5.double-q-learning-agent.ipynb`
**Logic:** DQN + decouples action selection (online net) and evaluation (target net) in TD target.
**AQP target:** `aqp/rl/agents/spm/double_dqn.py::DoubleDQNAgent`.

### DuelingDQNAgent

**Source:** `agent/6.duel-q-learning-agent.ipynb`
**Logic:** Splits Q-network into value stream + advantage stream; Q = V + (A - mean(A)).
**AQP target:** `aqp/rl/agents/spm/dueling_dqn.py::DuelingDQNAgent`.

### DoubleDuelingDQNAgent

**Source:** `agent/7.double-duel-q-learning-agent.ipynb`
**Logic:** Combination of Double + Dueling.
**AQP target:** `aqp/rl/agents/spm/double_dueling_dqn.py::DoubleDuelingDQNAgent`.

### RecurrentDQNAgent

**Source:** `agent/8.recurrent-q-learning-agent.ipynb`
**Logic:** GRU-based Q-network for partially observable settings.
**AQP target:** `aqp/rl/agents/spm/recurrent_dqn.py::RecurrentDQNAgent`.

### PolicyGradientAgent

**Source:** `agent/13.policy-gradient-agent.ipynb`
**Logic:** REINFORCE with discounted returns.
**AQP target:** `aqp/rl/agents/spm/policy_gradient.py::PolicyGradientAgent`.

### ActorCriticAgent

**Source:** `agent/14.actor-critic-agent.ipynb`
**Logic:** Shared encoder, separate value head + policy head; TD-error advantage.
**AQP target:** `aqp/rl/agents/spm/actor_critic.py::ActorCriticAgent`.

### A3CAgent

**Source:** `agent/15.actor-critic-duel-agent.ipynb` (lineage)
**Logic:** Single-process synchronous A2C variant (true asynchronous A3C left for SB3).
**AQP target:** `aqp/rl/agents/spm/a3c.py::A3CAgent`.

### EvolutionStrategyAgent

**Source:** `agent/1.turtle-agent.ipynb` lineage and `agent/3.evolution-strategy-agent.ipynb`
**Logic:** OpenAI ES — perturb policy weights with Gaussian noise, evaluate parallel rollouts, weighted update by reward rank. Pure NumPy.
**AQP target:** `aqp/rl/agents/spm/evolution_strategy.py::EvolutionStrategyAgent`.

### ActorCriticExperienceReplayAgent

**Source:** `agent/16.actor-critic-recurrent-agent.ipynb` lineage
**Logic:** Actor-critic with off-policy replay buffer.
**AQP target:** `aqp/rl/agents/spm/actor_critic_replay.py::ActorCriticExperienceReplayAgent`.

## TorchForecasterBase contract

```python
class TorchForecasterBase(Model):
    seq_len: int = 20
    hidden_size: int = 64
    lr: float = 1e-3
    epochs: int = 5
    batch_size: int = 32
    n_features: int = 1

    def build(self) -> None:
        """Subclasses populate self modules."""
        ...

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        ...

    def fit(self, dataset, **kwargs):
        # standard PyTorch train loop using MSE loss
        ...

    def predict(self, dataset, **kwargs) -> pd.Series:
        ...
```

## BaseRLAgent contract

```python
class BaseRLAgent:
    def __init__(self, env_cls=None, gamma=0.99, lr=1e-3, **kwargs):
        ...

    def train(self, env, total_timesteps: int) -> dict:
        """Train the policy and return metrics."""
        ...

    def act(self, obs) -> int | np.ndarray:
        """Greedy action."""
        ...

    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...
```
