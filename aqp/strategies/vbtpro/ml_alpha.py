"""ML-driven alpha tuned for the vbt-pro engine.

Wraps any :class:`aqp.ml.base.Model` (or any object with a ``predict`` method)
behind the :class:`IAlphaModel` contract so a trained ML model can drive a
vbt-pro signals backtest with a single panel-wide prediction pass.

Three model loading paths:

1. **Inline build-spec** — ``model={class, module_path, kwargs}``; the
   :func:`build_from_config` factory instantiates the class.
2. **MLflow URI** — ``mlflow_uri="models:/MyModel/Production"`` resolves
   through :class:`aqp.mlops.serving.base.PreparedModel` so production
   models flow into research backtests.
3. **Pre-built instance** — a Python object with a ``predict`` method.

Predictions are converted to entries / exits via one of three policies:

- ``threshold`` — ``score > threshold_long`` enters a long, ``score <
  threshold_short`` enters a short.
- ``top_k`` — at each rebalance, the top ``k`` symbols by score go long
  (and bottom ``k`` go short if shorts are enabled).
- ``rank`` — full long-short by rank percentile.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import build_from_config, register
from aqp.core.types import Direction, Signal, Symbol

if TYPE_CHECKING:
    from aqp.backtest.vbtpro.signal_builder import SignalArrays

logger = logging.getLogger(__name__)


@register("MLVbtAlpha", kind="alpha")
class MLVbtAlpha(IAlphaModel):
    """Wrap an :class:`aqp.ml.base.Model` as an :class:`IAlphaModel`.

    Parameters
    ----------
    model:
        Either a build-spec dict (``{"class", "module_path", "kwargs"}``)
        or a pre-built model instance with a ``predict`` method. Mutually
        exclusive with ``mlflow_uri``.
    mlflow_uri:
        Optional MLflow model URI (e.g. ``"models:/MyModel/Production"``);
        loaded via :class:`aqp.mlops.serving.base.PreparedModel`.
    deployment_id:
        Optional model deployment id used by
        :class:`aqp.mlops.serving.base.PreparedModel` for ledger linkage.
    indicators:
        List of indicator specs forwarded to
        :class:`aqp.data.indicators_zoo.IndicatorZoo`. Each indicator becomes
        a feature column on the panel fed to ``model.predict``.
    feature_columns:
        Optional explicit list of pre-computed feature columns to consume
        from the bars frame (e.g. when an upstream Iceberg table already
        carries features).
    policy:
        ``"threshold"``, ``"top_k"``, or ``"rank"``.
    threshold_long, threshold_short:
        Score thresholds for the ``threshold`` policy.
    top_k:
        Number of symbols selected for the ``top_k`` policy.
    rebalance:
        ``None`` (every bar), ``"D"``, ``"W"``, ``"M"``, etc. Resampled
        rebalance frequency for top_k / rank policies.
    allow_short:
        Squashes shorts when False.
    use_size_in_signals:
        When True, populates ``SignalArrays.size`` proportionally to the
        score so position sizes reflect model confidence.
    score_clip:
        Optional ``(low, high)`` tuple to winsorize raw model outputs.
    """

    def __init__(
        self,
        model: Any | None = None,
        *,
        mlflow_uri: str | None = None,
        deployment_id: str | None = None,
        indicators: list[str] | None = None,
        feature_columns: list[str] | None = None,
        policy: str = "threshold",
        threshold_long: float = 0.0,
        threshold_short: float | None = None,
        top_k: int = 5,
        rebalance: str | None = None,
        allow_short: bool = True,
        use_size_in_signals: bool = True,
        score_clip: tuple[float, float] | None = None,
        prediction_horizon: int = 5,
    ) -> None:
        self._model_cfg = model
        self.mlflow_uri = mlflow_uri
        self.deployment_id = deployment_id
        self.indicators = list(indicators or [])
        self.feature_columns = list(feature_columns or [])
        self.policy = policy
        self.threshold_long = float(threshold_long)
        self.threshold_short = (
            float(threshold_short)
            if threshold_short is not None
            else -float(threshold_long)
        )
        self.top_k = int(top_k)
        self.rebalance = rebalance
        self.allow_short = bool(allow_short)
        self.use_size_in_signals = bool(use_size_in_signals)
        self.score_clip = score_clip
        self.prediction_horizon = int(prediction_horizon)

        self._model: Any | None = None
        self._stats: dict[str, int] = {"predict_calls": 0, "rebalances": 0}

    # ------------------------------------------------------------------
    # Model loading (lazy)
    # ------------------------------------------------------------------

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self.mlflow_uri:
            try:
                from aqp.mlops.serving.base import PreparedModel

                pm = PreparedModel.from_mlflow_uri(
                    self.mlflow_uri,
                    deployment_id=self.deployment_id,
                )
                self._model = pm.resolve_model()
            except Exception:
                logger.exception("failed to load model from MLflow URI %s", self.mlflow_uri)
                raise
        elif isinstance(self._model_cfg, dict):
            self._model = build_from_config(self._model_cfg)
        elif self._model_cfg is not None:
            self._model = self._model_cfg
        else:
            raise ValueError(
                "MLVbtAlpha requires one of: model, mlflow_uri, or deployment_id"
            )
        if not hasattr(self._model, "predict"):
            raise TypeError(
                f"resolved model {type(self._model).__name__} has no predict() method"
            )
        return self._model

    # ------------------------------------------------------------------
    # Panel path — the vbt-pro engine's preferred entry point
    # ------------------------------------------------------------------

    def generate_panel_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any] | None = None,
    ) -> SignalArrays:
        from aqp.backtest.vbtpro.signal_builder import SignalArrays

        ctx = context or {}
        close: pd.DataFrame | None = ctx.get("close")
        if close is None:
            close = (
                bars.copy()
                .assign(timestamp=lambda df: pd.to_datetime(df["timestamp"]))
                .pivot_table(
                    index="timestamp",
                    columns="vt_symbol",
                    values="close",
                    aggfunc="last",
                )
                .sort_index()
                .ffill()
            )

        scores = self._compute_score_panel(bars, close)
        scores = self._maybe_clip(scores)

        rebalance_mask = self._rebalance_mask(scores.index)

        entries = pd.DataFrame(False, index=close.index, columns=close.columns)
        exits = pd.DataFrame(False, index=close.index, columns=close.columns)
        short_entries = pd.DataFrame(False, index=close.index, columns=close.columns)
        short_exits = pd.DataFrame(False, index=close.index, columns=close.columns)
        size = pd.DataFrame(0.0, index=close.index, columns=close.columns) if self.use_size_in_signals else None

        previous_long: pd.Series = pd.Series(False, index=close.columns)
        previous_short: pd.Series = pd.Series(False, index=close.columns)

        for ts in close.index:
            if not rebalance_mask.loc[ts]:
                continue
            if ts not in scores.index:
                continue
            self._stats["rebalances"] += 1
            row = scores.loc[ts].dropna()
            new_long, new_short, sizes = self._signals_for_row(row)

            new_long = new_long.reindex(close.columns, fill_value=False)
            new_short = new_short.reindex(close.columns, fill_value=False)

            entries.loc[ts] = new_long & ~previous_long
            exits.loc[ts] = previous_long & ~new_long
            if self.allow_short:
                short_entries.loc[ts] = new_short & ~previous_short
                short_exits.loc[ts] = previous_short & ~new_short

            if size is not None:
                size.loc[ts] = sizes.reindex(close.columns, fill_value=0.0)

            previous_long = new_long
            previous_short = new_short

        return SignalArrays(
            entries=entries,
            exits=exits,
            short_entries=short_entries if self.allow_short else None,
            short_exits=short_exits if self.allow_short else None,
            size=size,
            signal_records=[],
        )

    # ------------------------------------------------------------------
    # Per-bar fallback for the event-driven engine
    # ------------------------------------------------------------------

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        ts = context.get("current_time") or context.get("timestamp")
        if ts is None and not bars.empty:
            ts = bars["timestamp"].max()
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()

        try:
            close = (
                bars.copy()
                .assign(timestamp=lambda df: pd.to_datetime(df["timestamp"]))
                .pivot_table(
                    index="timestamp",
                    columns="vt_symbol",
                    values="close",
                    aggfunc="last",
                )
                .sort_index()
                .ffill()
            )
        except Exception:
            return []
        scores = self._compute_score_panel(bars, close)
        scores = self._maybe_clip(scores)
        if scores.empty or scores.index[-1] != close.index[-1]:
            return []

        row = scores.iloc[-1].dropna()
        long_mask, short_mask, sizes = self._signals_for_row(row)
        signals: list[Signal] = []
        for sym in universe:
            vt = sym.vt_symbol
            if vt not in long_mask.index:
                continue
            if long_mask.loc[vt]:
                signals.append(self._signal(sym, ts, Direction.LONG, sizes.get(vt, 1.0)))
            elif self.allow_short and short_mask.loc[vt]:
                signals.append(self._signal(sym, ts, Direction.SHORT, sizes.get(vt, 1.0)))
        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_score_panel(
        self, bars: pd.DataFrame, close: pd.DataFrame
    ) -> pd.DataFrame:
        model = self._load_model()
        feature_panel = self._build_feature_panel(bars, close)
        if feature_panel.empty:
            return pd.DataFrame(0.0, index=close.index, columns=close.columns)

        scores = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
        for vt_symbol, sub in feature_panel.groupby(level="vt_symbol", sort=False):
            symbol_panel = sub.reset_index(level="vt_symbol", drop=True)
            try:
                preds = model.predict(symbol_panel)
            except TypeError:
                # Fall back to numpy interface for sklearn-style models.
                preds = model.predict(symbol_panel.values)
            preds_series = pd.Series(np.asarray(preds).reshape(-1), index=symbol_panel.index)
            scores.loc[preds_series.index, vt_symbol] = preds_series.values
            self._stats["predict_calls"] += 1
        return scores

    def _build_feature_panel(
        self, bars: pd.DataFrame, close: pd.DataFrame
    ) -> pd.DataFrame:
        if self.feature_columns and all(col in bars.columns for col in self.feature_columns):
            df = bars.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df.set_index(["timestamp", "vt_symbol"])[self.feature_columns]

        if self.indicators:
            try:
                from aqp.data.indicators_zoo import IndicatorZoo

                zoo = IndicatorZoo()
                feats = zoo.transform(bars.copy(), indicators=self.indicators)
            except Exception:
                logger.exception("IndicatorZoo.transform failed; falling back to bars")
                feats = bars.copy()
        else:
            feats = bars.copy()

        feats["timestamp"] = pd.to_datetime(feats["timestamp"])
        feats = feats.set_index(["timestamp", "vt_symbol"]).sort_index()
        # Drop OHLCV unless explicitly named in feature_columns; ML models
        # usually want indicator columns only.
        keep = [c for c in feats.columns if c not in {"open", "high", "low", "close", "volume"}]
        if self.feature_columns:
            keep = [c for c in self.feature_columns if c in feats.columns]
        if not keep:
            keep = list(feats.columns)
        return feats[keep].dropna(how="all")

    def _maybe_clip(self, scores: pd.DataFrame) -> pd.DataFrame:
        if self.score_clip is None:
            return scores
        low, high = self.score_clip
        return scores.clip(lower=low, upper=high)

    def _rebalance_mask(self, index: pd.DatetimeIndex) -> pd.Series:
        if self.rebalance is None:
            return pd.Series(True, index=index)
        rebalances = pd.date_range(
            start=index.min(),
            end=index.max(),
            freq=self.rebalance,
        )
        mask = pd.Series(False, index=index)
        for r in rebalances:
            # Snap to first index >= rebalance date.
            future = index[index >= r]
            if len(future):
                mask.loc[future[0]] = True
        if not mask.any() and len(index):
            mask.iloc[0] = True
        return mask

    def _signals_for_row(
        self, row: pd.Series
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        if self.policy == "threshold":
            long_mask = row > self.threshold_long
            short_mask = row < self.threshold_short
        elif self.policy == "top_k":
            ranked = row.sort_values(ascending=False)
            n = min(self.top_k, len(ranked))
            long_mask = pd.Series(False, index=row.index)
            long_mask.loc[ranked.head(n).index] = True
            short_mask = pd.Series(False, index=row.index)
            if self.allow_short:
                short_mask.loc[ranked.tail(n).index] = True
        elif self.policy == "rank":
            quantiles = row.rank(pct=True, method="average")
            long_mask = quantiles >= 0.8
            short_mask = quantiles <= 0.2 if self.allow_short else pd.Series(False, index=row.index)
        else:
            raise ValueError(f"Unknown policy: {self.policy!r}")

        if self.use_size_in_signals:
            magnitude = row.abs()
            total = magnitude.sum()
            sizes = magnitude / total if total else magnitude * 0.0
        else:
            n_total = max(1, int(long_mask.sum() + short_mask.sum()))
            sizes = pd.Series(1.0 / n_total, index=row.index)
        return long_mask, short_mask, sizes

    def _signal(
        self,
        sym: Symbol,
        ts: Any,
        direction: Direction,
        strength: float,
    ) -> Signal:
        return Signal(
            symbol=sym,
            strength=float(strength),
            direction=direction,
            timestamp=ts,
            confidence=float(min(1.0, max(0.0, strength))),
            horizon_days=self.prediction_horizon,
            source=f"MLVbtAlpha[{self.policy}]",
        )

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)


__all__ = ["MLVbtAlpha"]
