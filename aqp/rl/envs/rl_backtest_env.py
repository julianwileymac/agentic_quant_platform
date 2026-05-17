"""``RLBacktestEnv`` — bridge gym.Env that wraps a registered backtest engine.

The bridge resolves two long-standing impedance mismatches in AQP:

1. The existing FinRL-style envs (``StockTradingEnv``,
   ``PortfolioAllocationEnv``, ``FinRLStockTradingEnv`` …) embed their
   own simplified order matching + accounting code, which subtly
   diverges from :class:`aqp.backtest.broker_sim.SimulatedBrokerage`
   and therefore from the live paper-trading execution path. That
   delta is exactly the FinRL-X "backtest-to-paper gap".
2. The existing :class:`aqp.backtest.engine.EventDrivenBacktester`
   (and friends) execute a complete simulation in one ``run()`` call
   — which the gym ``reset`` / ``step`` API can't drive directly.

This env uses :class:`aqp.backtest.broker_sim.SimulatedBrokerage`
**directly** as the order matcher (rather than spawning a thread to
drive the full engine event loop) so cheat-on-open fill semantics,
commission, slippage, and inventory bookkeeping match the production
execution path byte-for-byte. The action vector flows through the
canonical FinRL-X
:class:`aqp.rl.portfolio.WeightCentricPipeline` (``f_S -> f_A -> f_T -> f_R``)
before becoming the target-weight vector.

The thread-bridge variant that wraps a complete engine (so vbt-pro
optimisation kernels and LobBacktestEngine LOB matching can also
drive ``step``) is delivered separately as
:class:`aqp.rl.envs.rl_backtest_env.EngineThreadBridgeMixin` in Phase
9 alongside the optional ``BacktraderEngine`` adapter.

Determinism contract
--------------------

- ``reset(seed=...)`` re-seeds the numpy RNG used for any synthetic
  liquidity / volatility / regime augmentation.
- The :class:`SimulatedBrokerage` ledger is fully reset on every
  ``reset``; no state leaks between episodes.
- ``info['truncated']`` is set on any ``RiskOverlay``-flagged breach
  (the AQP equivalent of the NeMo-RL "stop properly" trigger). The
  reward shaper in :mod:`aqp.rl.rewards.stop_properly` reads this
  flag and scales accordingly.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, ClassVar, Mapping

import numpy as np
import pandas as pd

try:
    import gymnasium as gym
except Exception:  # pragma: no cover - keeps import-time fail loud
    gym = None  # type: ignore[assignment]

from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.core.types import (
    Direction,
    OrderRequest,
    OrderSide,
    OrderType,
    Symbol,
)
from aqp.rl.core.env import BaseRLEnv
from aqp.rl.portfolio import (
    GrossExposureRiskOverlay,
    IdentityAllocator,
    PipelineState,
    PositionCapRiskOverlay,
    StackedRiskOverlay,
    StaticUniverseSelector,
    WeightCentricPipeline,
)

logger = logging.getLogger(__name__)


class RLBacktestEnv(BaseRLEnv):
    """gym.Env that uses a backtest brokerage as its physics engine.

    Parameters
    ----------
    universe:
        Ordered list of ``vt_symbol`` strings the env will allocate
        across. Defines the action space dimensionality.
    data_pipeline:
        :class:`aqp.rl.core.data.BaseDataPipeline` (injected by
        :class:`RLRuntime` from ``spec.data_pipeline``). If ``None``,
        ``bars`` must be supplied directly.
    bars:
        Pre-loaded long-format DataFrame with columns
        ``date``, ``tic``, ``open``, ``high``, ``low``, ``close``,
        ``volume`` (+ indicators). Skipped when ``data_pipeline`` is
        supplied.
    pipeline:
        :class:`WeightCentricPipeline` (FinRL-X ``f_S -> f_A -> f_T -> f_R``).
        Defaults to a long-only pipeline with a 30%-position-cap +
        100%-gross overlay so the env produces sane weights even
        without spec-level configuration.
    initial_cash:
        Starting equity for the simulated brokerage.
    start / end:
        Optional ISO date strings narrowing the bar window.
    commission_pct / slippage_bps:
        Forwarded to :class:`SimulatedBrokerage`. Defaults match the
        production paper-trading session.
    indicators:
        Per-asset feature columns surfaced via the observation.
        Defaults to the OHLCV columns.
    use_turbulence:
        When ``True`` the env reads a ``turbulence`` column from the
        bars and surfaces it in the observation + risk context (used
        by :class:`TurbulenceTimingAdjuster` and
        :class:`TurbulenceTermination`).
    horizon:
        Optional cap on episode length (in bars). Defaults to the
        number of unique timestamps in the data.
    rebalance_threshold:
        Skip per-bar trading when ``|delta_weight| < threshold``.
        Defaults to ``0.0`` (always rebalance) — set higher to model
        a coarser rebalancing cadence and cut transaction-cost noise.

    Notes
    -----
    Action space is ``Box(-1, 1, shape=(N,))`` so it interleaves
    cleanly with :class:`SoftmaxWeightsAction` /
    :class:`ContinuousWeightsAction` / :class:`TargetPositionAction`.
    Observation space is ``Box(-inf, inf, shape=(D,))`` where ``D``
    is determined on first ``_build_obs`` call.
    """

    rl_alias: ClassVar[str] = "RLBacktestEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "weight_centric"
    rl_tags: ClassVar[tuple[str, ...]] = ("weight_centric", "backtest_bridge", "finrl_x")

    def __init__(
        self,
        *,
        universe: list[str],
        data_pipeline: Any | None = None,
        bars: pd.DataFrame | None = None,
        pipeline: WeightCentricPipeline | None = None,
        initial_cash: float = 100_000.0,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        commission_pct: float = 0.0005,
        slippage_bps: float = 2.0,
        indicators: list[str] | None = None,
        use_turbulence: bool = False,
        horizon: int | None = None,
        rebalance_threshold: float = 0.0,
        seed: int | None = None,
        **kwargs: Any,
    ) -> None:
        if gym is None:
            raise ImportError("RLBacktestEnv requires gymnasium")
        if not universe:
            raise ValueError("RLBacktestEnv requires a non-empty universe")
        self._universe: list[str] = list(universe)
        self._data_pipeline = data_pipeline
        self._initial_bars = bars
        self._initial_cash = float(initial_cash)
        self._start = start
        self._end = end
        self._commission_pct = float(commission_pct)
        self._slippage_bps = float(slippage_bps)
        self._indicators: list[str] = list(indicators or [])
        self._use_turbulence = bool(use_turbulence)
        self._horizon_cap = int(horizon) if horizon is not None else None
        self._rebalance_threshold = float(rebalance_threshold)

        # Default FinRL-X long-only pipeline: identity allocator (the
        # raw RL action IS the unconstrained weight), no timing
        # rescale, and a stacked overlay enforcing per-position 30%
        # cap + gross-exposure 100% cap.
        self.pipeline = pipeline or WeightCentricPipeline(
            selector=StaticUniverseSelector(universe=list(universe)),
            allocator=IdentityAllocator(),
            risk_overlay=StackedRiskOverlay(
                overlays=[
                    PositionCapRiskOverlay(max_position_pct=0.30, mark_truncated=True),
                    GrossExposureRiskOverlay(max_gross=1.0),
                ]
            ),
        )

        # Action space MUST be set before ``BaseRLEnv.__init__`` runs
        # because the base class derives ``self.action_space`` from
        # ``action_space_spec`` (we keep ``action_space_spec=None``
        # here because we expose a custom Box).
        self.action_space = gym.spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(len(self._universe),),
            dtype=np.float32,
        )

        super().__init__(seed=seed, **{k: v for k, v in kwargs.items() if k in {"observation_builder", "reward_model", "terminations"}})

    # ------------------------------------------------------------------ data + state

    def _setup_data(self) -> None:
        bars = self._initial_bars
        if bars is None and self._data_pipeline is not None:
            tickers = list(self._universe)
            start = str(self._start) if self._start is not None else "1970-01-01"
            end = str(self._end) if self._end is not None else "2099-12-31"
            bars = self._data_pipeline.download_data(tickers, start, end)
            bars = self._data_pipeline.clean_data(bars)
            indicator_list = list(self._indicators)
            bars = self._data_pipeline.add_indicators(bars, indicator_list)
            bars = self._data_pipeline.add_risk_features(
                bars,
                use_turbulence=self._use_turbulence,
            )
        if bars is None or bars.empty:
            raise ValueError(
                "RLBacktestEnv needs either a populated ``bars`` DataFrame "
                "or a ``data_pipeline`` that yields one"
            )
        bars = bars.copy()
        if "date" in bars.columns:
            bars["date"] = pd.to_datetime(bars["date"])
        # Stable timestamp index (one row per unique date) so we can
        # iterate the simulator one bar at a time. Bars where a
        # ticker is missing default to forward-fill via groupby.
        bars = bars.sort_values(["date", "tic"]).reset_index(drop=True)
        self._bars = bars
        self._timestamps: list[pd.Timestamp] = sorted(bars["date"].unique().tolist())
        if not self._timestamps:
            raise ValueError("RLBacktestEnv: no timestamps in bar data")
        nat_horizon = len(self._timestamps)
        self.horizon = (
            min(self._horizon_cap, nat_horizon) if self._horizon_cap else nat_horizon
        )
        # Cache (timestamp -> {vt_symbol -> bar}) for O(1) lookup.
        self._bars_by_ts: dict[pd.Timestamp, dict[str, pd.Series]] = {}
        for ts, frame in bars.groupby("date"):
            self._bars_by_ts[pd.Timestamp(ts)] = {
                str(row.tic): row for row in frame.itertuples(index=False)
            }

    def _reset_state(self) -> None:
        self.step_idx = 0
        self._brokerage = SimulatedBrokerage(
            initial_cash=self._initial_cash,
            commission_pct=self._commission_pct,
            slippage_bps=self._slippage_bps,
        )
        self._equity_history: list[float] = [float(self._initial_cash)]
        self._weight_history: list[np.ndarray] = []
        self._last_decision_state: PipelineState | None = None
        self._truncated_flag: bool = False
        self._truncation_reason: str | None = None

    # ------------------------------------------------------------------ env-state helpers

    def _current_ts(self) -> pd.Timestamp:
        idx = min(self.step_idx, len(self._timestamps) - 1)
        return self._timestamps[idx]

    def _bar_at(self, ts: pd.Timestamp) -> dict[str, Any]:
        return self._bars_by_ts.get(ts, {})

    def _close_prices(self, ts: pd.Timestamp) -> dict[str, float]:
        bars = self._bar_at(ts)
        return {sym: float(getattr(row, "close", 0.0)) for sym, row in bars.items()}

    def _open_prices(self, ts: pd.Timestamp) -> dict[str, float]:
        bars = self._bar_at(ts)
        return {sym: float(getattr(row, "open", 0.0)) for sym, row in bars.items()}

    def _turbulence(self, ts: pd.Timestamp) -> float:
        if not self._use_turbulence:
            return 0.0
        bars = self._bar_at(ts)
        if not bars:
            return 0.0
        # All assets share the same turbulence reading at any given
        # timestamp because turbulence is portfolio-level.
        any_row = next(iter(bars.values()))
        return float(getattr(any_row, "turbulence", 0.0) or 0.0)

    def _peak_equity(self) -> float:
        return max(self._equity_history) if self._equity_history else float(self._initial_cash)

    def _drawdown(self) -> float:
        peak = self._peak_equity()
        if peak <= 0:
            return 0.0
        return float((self._equity_history[-1] - peak) / peak)

    def _collect_env_state(self) -> dict[str, Any]:
        ts = self._current_ts()
        equity = self._brokerage.mark_to_market(self._close_prices(ts))
        return {
            "step_idx": self.step_idx,
            "timestamp": ts,
            "cash": float(self._brokerage.cash),
            "portfolio_value": float(equity),
            "weights": (
                self._weight_history[-1].tolist() if self._weight_history else [0.0] * len(self._universe)
            ),
            "positions": {k: float(v.quantity) * (1.0 if v.direction == Direction.LONG else -1.0) for k, v in self._brokerage.positions.items()},
            "drawdown": float(self._drawdown()),
            "turbulence": float(self._turbulence(ts)),
            "universe": list(self._universe),
            "prices": self._close_prices(ts),
            "peak": float(self._peak_equity()),
            "prev_value": float(self._equity_history[-1]) if self._equity_history else float(self._initial_cash),
        }

    # ------------------------------------------------------------------ action application

    def _apply_action(self, action: Any) -> dict[str, Any]:
        ts = self._current_ts()
        env_state = self._collect_env_state()

        # Run the weight-centric pipeline: ``f_S -> f_A -> f_T -> f_R``.
        state = self.pipeline.run(
            universe=list(self._universe),
            raw_action=np.asarray(action, dtype=np.float64).ravel(),
            context={
                "current_time": ts,
                "prices": env_state["prices"],
                "turbulence": env_state["turbulence"],
                "drawdown": env_state["drawdown"],
                "positions": env_state["positions"],
                "equity": env_state["portfolio_value"],
            },
        )
        self._last_decision_state = state
        target_weights = np.asarray(state.weights, dtype=np.float64)
        self._weight_history.append(target_weights.copy())

        # Risk-overlay truncation propagates straight onto ``info``.
        if state.context.get("truncated"):
            self._truncated_flag = True
            self._truncation_reason = str(state.context.get("risk_breach_reason") or "risk_overlay_truncation")

        # Translate target weights into order requests against the
        # *current* close, then fill at next-bar open in the cheat-on-open
        # tradition. (FinRL envs cheat at the same-bar close; this is
        # less optimistic and matches the production execution path.)
        current_equity = float(env_state["portfolio_value"])
        prices_now = env_state["prices"]
        for i, vt in enumerate(self._universe):
            price = float(prices_now.get(vt, 0.0))
            if price <= 0:
                continue
            target_w = float(target_weights[i]) if i < len(target_weights) else 0.0
            target_notional = target_w * current_equity
            target_qty = target_notional / price
            current_qty = self._current_signed_qty(vt)
            delta = target_qty - current_qty
            if abs(delta * price / max(current_equity, 1.0)) < self._rebalance_threshold:
                continue
            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            self._brokerage.submit_order(
                OrderRequest(
                    symbol=Symbol.parse(vt),
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=float(abs(delta)),
                    price=None,
                )
            )

        # Cheat-on-open: fill against the NEXT bar's open prices.
        next_idx = min(self.step_idx + 1, len(self._timestamps) - 1)
        next_ts = self._timestamps[next_idx]
        next_open = self._open_prices(next_ts)
        if next_open:
            self._brokerage.fill_open_orders(next_open, next_ts.to_pydatetime() if hasattr(next_ts, "to_pydatetime") else datetime.utcnow())

        # Mark to market against the next bar's close so the reward
        # captures the PnL of the rebalance over the next bar.
        next_close = self._close_prices(next_ts)
        next_equity = float(self._brokerage.mark_to_market(next_close) if next_close else self._brokerage.equity)
        self._equity_history.append(next_equity)

        turnover = float(np.abs(target_weights - (self._weight_history[-2] if len(self._weight_history) >= 2 else np.zeros_like(target_weights))).sum()) / 2.0
        return {
            "turnover": turnover,
            "portfolio_value": next_equity,
            "drawdown": self._drawdown(),
            "turbulence": self._turbulence(next_ts),
            "rl_target_weights": target_weights.tolist(),
            "rl_universe": list(state.universe),
            "rl_pipeline_history": [stage for stage, _ in state.history],
            "truncated": bool(self._truncated_flag),
            "truncation_reason": self._truncation_reason,
        }

    def _current_signed_qty(self, vt: str) -> float:
        pos = self._brokerage.positions.get(vt)
        if pos is None:
            return 0.0
        sign = 1.0 if pos.direction == Direction.LONG else -1.0
        return sign * float(pos.quantity)

    # ------------------------------------------------------------------ gym driver

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        obs, info = super().reset(seed=seed, options=options)
        info["universe"] = list(self._universe)
        info["initial_cash"] = float(self._initial_cash)
        return obs, info

    def step(self, action: Any):  # type: ignore[override]
        prev_state = self._collect_env_state()
        side_metrics = self._apply_action(action) or {}
        self.step_idx += 1
        next_state = self._collect_env_state()

        info: dict[str, Any] = {
            **side_metrics,
            "timestamp": next_state.get("timestamp"),
            "step_idx": next_state.get("step_idx"),
        }
        if self.reward_model is not None:
            reward = float(self.reward_model.compute(prev_state, action, next_state, info))
            info.setdefault(
                "reward_terms",
                self.reward_model.decomposition(prev_state, action, next_state, info),
            )
        else:
            # Default reward: per-step log return (FinRL convention).
            prev_pv = float(prev_state.get("portfolio_value", self._initial_cash) or self._initial_cash)
            next_pv = float(next_state.get("portfolio_value", prev_pv))
            reward = float(np.log(max(next_pv, 1e-6) / max(prev_pv, 1e-6)))

        # Termination = natural horizon hit. Truncation = risk-overlay /
        # termination-condition flagged a hard breach (the FinRL-X
        # "stop properly" trigger).
        terminated = bool(self._check_terminations(self.step_idx, next_state))
        truncated = bool(self._truncated_flag)
        if truncated:
            info["truncation_reason"] = self._truncation_reason
        return self._build_obs(min(self.step_idx, self.horizon - 1)), reward, terminated, truncated, info

    # ------------------------------------------------------------------ obs

    def _build_obs(self, idx: int) -> np.ndarray:
        # If the user passed an observation builder, defer to it
        # (matches the ``BaseRLEnv`` contract). Otherwise emit a
        # default tensor of the per-asset price + indicator block +
        # portfolio weights — enough to drive a generic policy.
        if self.observation_builder is not None:
            return np.asarray(
                self.observation_builder.build(idx, self._collect_env_state()),
                dtype=np.float32,
            )
        ts = self._current_ts()
        bars = self._bar_at(ts)
        blocks: list[float] = []
        for vt in self._universe:
            row = bars.get(vt)
            if row is None:
                blocks.extend([0.0] * (1 + len(self._indicators)))
                continue
            blocks.append(float(getattr(row, "close", 0.0)))
            for col in self._indicators:
                blocks.append(float(getattr(row, col, 0.0) or 0.0))
        weights = self._weight_history[-1] if self._weight_history else np.zeros(len(self._universe))
        blocks.extend(weights.astype(np.float64).tolist())
        blocks.append(float(self._brokerage.cash))
        blocks.append(float(self._equity_history[-1] if self._equity_history else self._initial_cash))
        arr = np.asarray(blocks, dtype=np.float32)
        if not hasattr(self, "observation_space") or self.observation_space is None:
            self.observation_space = gym.spaces.Box(  # type: ignore[union-attr]
                low=-np.inf, high=np.inf, shape=arr.shape, dtype=np.float32
            )
        return arr

    # ------------------------------------------------------------------ termination override

    def _check_terminations(self, idx: int, env_state: Mapping[str, Any]) -> bool:
        # Subclass hook fires user-configured terminations first; if
        # any of them set ``truncated`` on ``self._truncated_flag``
        # we still let the episode end naturally via the parent
        # ``_check_terminations`` logic.
        result = super()._check_terminations(idx, env_state)
        if not result and idx >= self.horizon - 1:
            return True
        return result


__all__ = ["RLBacktestEnv"]
