"""ML-based stock-selection alpha (FinRL-Trading style).

Ports the pattern from
``inspiration/FinRL-Trading-master/src/strategies/ml_strategy.py``:

1. Train a regression model (RF / GBM / Linear / XGB / LGBM) on a
   tidy bars + indicator panel produced by :class:`IndicatorZoo` or a
   persisted :class:`FeatureSet`.
2. Score every symbol on the most recent timestamp.
3. Pick the top ``top_quantile`` slice by predicted return.
4. Allocate weights via ``equal``, ``min_variance``, or
   ``risk_parity``.
5. Emit one :class:`Signal` per kept symbol.

Two surfaces:

- :class:`MLStockSelectionAlpha` — vanilla version.
- :class:`SectorNeutralMLAlpha` — bucket selection by sector before
  allocating weights, so the resulting portfolio stays sector-balanced.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


_NON_FEATURE_COLS = {
    "timestamp",
    "vt_symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "target",
    "label",
}


WeightMethod = Literal["equal", "min_variance", "risk_parity"]


def _features_panel(
    bars: pd.DataFrame,
    *,
    feature_set_name: str | None,
    feature_specs: list[str] | None,
) -> pd.DataFrame:
    """Build the feature panel using FeatureSet first, then IndicatorZoo."""
    if feature_set_name:
        try:
            from aqp.data.feature_sets import FeatureSetService

            service = FeatureSetService()
            summary = service.get_by_name(feature_set_name)
            if summary is not None:
                return service.materialize(summary.id, bars)
            logger.info(
                "MLStockSelection: feature_set %s not found; falling back to IndicatorZoo",
                feature_set_name,
            )
        except Exception:
            logger.exception("MLStockSelection: feature-set lookup failed")
    from aqp.data.indicators_zoo import IndicatorZoo

    return IndicatorZoo().transform(bars, indicators=feature_specs or None)


def _build_supervised_dataset(
    panel: pd.DataFrame,
    forward_horizon_days: int,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Build X / y for training; target = forward return."""
    panel = panel.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)
    panel["target"] = (
        panel.groupby("vt_symbol")["close"].shift(-int(forward_horizon_days))
        / panel["close"]
        - 1
    )
    train = panel.dropna(subset=["target"]).copy()
    feature_cols = [c for c in train.columns if c.lower() not in _NON_FEATURE_COLS]
    X = train[feature_cols].fillna(0.0)
    y = train["target"].fillna(0.0)
    return X, y, feature_cols


def _train_model(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    model_kind: str,
    model_kwargs: dict[str, Any] | None,
):
    kw = dict(model_kwargs or {})
    kind = (model_kind or "random_forest").lower()
    if kind in ("rf", "random_forest"):
        from sklearn.ensemble import RandomForestRegressor

        kw.setdefault("n_estimators", 100)
        kw.setdefault("random_state", 42)
        return RandomForestRegressor(**kw).fit(X.values, y.values)
    if kind in ("gbm", "gradient_boosting"):
        from sklearn.ensemble import GradientBoostingRegressor

        kw.setdefault("n_estimators", 100)
        kw.setdefault("random_state", 42)
        return GradientBoostingRegressor(**kw).fit(X.values, y.values)
    if kind in ("linear", "ridge"):
        from sklearn.linear_model import Ridge

        kw.setdefault("alpha", 1.0)
        return Ridge(**kw).fit(X.values, y.values)
    if kind in ("xgb", "xgboost"):
        from xgboost import XGBRegressor

        kw.setdefault("n_estimators", 200)
        kw.setdefault("max_depth", 5)
        kw.setdefault("learning_rate", 0.05)
        kw.setdefault("n_jobs", -1)
        return XGBRegressor(**kw).fit(X.values, y.values)
    if kind in ("lgbm", "lightgbm"):
        from lightgbm import LGBMRegressor

        kw.setdefault("n_estimators", 200)
        kw.setdefault("learning_rate", 0.05)
        kw.setdefault("num_leaves", 31)
        kw.setdefault("verbose", -1)
        return LGBMRegressor(**kw).fit(X.values, y.values)
    raise ValueError(f"unsupported ML model_kind: {model_kind!r}")


def _equal_weights(tickers: Iterable[str]) -> dict[str, float]:
    syms = list(tickers)
    if not syms:
        return {}
    w = 1.0 / len(syms)
    return {s: w for s in syms}


def _cov_from_panel(panel: pd.DataFrame, lookback: int) -> tuple[np.ndarray, list[str]]:
    """Per-symbol covariance over the most recent ``lookback`` rows."""
    pivot = panel.pivot_table(
        index="timestamp", columns="vt_symbol", values="close"
    ).sort_index()
    pivot = pivot.tail(int(lookback)).pct_change().dropna()
    if pivot.empty or pivot.shape[1] < 2:
        return np.zeros((0, 0)), []
    cov = pivot.cov().values
    syms = list(pivot.columns)
    return cov, syms


def _min_variance_weights(
    cov: np.ndarray,
    *,
    max_weight: float = 1.0,
    long_only: bool = True,
) -> np.ndarray:
    """Closed-form min-variance with weights summing to 1.

    ``w = inv(C) 1 / (1^T inv(C) 1)``. We then clip to ``[0, max_weight]``
    when ``long_only`` and renormalise so the cap survives.
    """
    if cov.size == 0:
        return np.array([])
    n = cov.shape[0]
    try:
        inv = np.linalg.pinv(cov)
        ones = np.ones(n)
        raw = inv @ ones
        w = raw / (ones @ raw)
    except Exception:
        w = np.ones(n) / n
    if long_only:
        w = np.clip(w, 0.0, max_weight)
        s = w.sum()
        w = w / s if s > 0 else np.ones(n) / n
    return w


def _risk_parity_weights(cov: np.ndarray) -> np.ndarray:
    """Cheap diagonal-risk-parity (1/sigma)."""
    if cov.size == 0:
        return np.array([])
    sigmas = np.sqrt(np.maximum(np.diag(cov), 1e-12))
    inv = 1.0 / sigmas
    return inv / inv.sum()


def _allocate_weights(
    selected: list[str],
    panel: pd.DataFrame,
    *,
    method: WeightMethod,
    lookback_periods: int,
    max_weight: float,
) -> dict[str, float]:
    if method == "equal" or len(selected) <= 1:
        return _equal_weights(selected)
    sub = panel[panel["vt_symbol"].isin(selected)]
    cov, syms = _cov_from_panel(sub, lookback_periods)
    if not syms or len(syms) < 2:
        logger.info("min_variance: insufficient cov data — falling back to equal weights")
        return _equal_weights(selected)
    if method == "risk_parity":
        weights = _risk_parity_weights(cov)
    else:  # min_variance
        weights = _min_variance_weights(cov, max_weight=max_weight)
    out = {sym: float(w) for sym, w in zip(syms, weights)}
    # If some selected symbols dropped due to NaNs, fill them with 0.
    for s in selected:
        out.setdefault(s, 0.0)
    # Re-normalise.
    total = sum(out.values())
    if total > 0:
        out = {k: v / total for k, v in out.items()}
    return out


@register(
    "MLStockSelectionAlpha",
    kind="strategy",
    tags=("ml", "stock_selection", "supervised"),
    source="finrl_trading",
    category="ml_selection",
)
class MLStockSelectionAlpha(IAlphaModel):
    """Pick top-quantile names by predicted return + allocate weights.

    Trains the model on the supplied bars (single backtest pass) — for
    multi-fold training use the platform's ML training task. The model
    is re-fit only when ``retrain_each_call=True`` (default ``False``);
    otherwise it caches between bars.
    """

    def __init__(
        self,
        model_kind: str = "random_forest",
        model_kwargs: dict[str, Any] | None = None,
        feature_specs: list[str] | None = None,
        feature_set_name: str | None = None,
        forward_horizon_days: int = 21,
        top_quantile: float = 0.75,
        weight_method: str = "equal",
        lookback_periods: int = 252,
        max_weight: float = 1.0,
        long_only: bool = True,
        min_pred_return: float = 0.0,
        retrain_each_call: bool = False,
    ) -> None:
        self.model_kind = str(model_kind)
        self.model_kwargs = dict(model_kwargs or {})
        self.feature_specs = list(feature_specs or [])
        self.feature_set_name = feature_set_name
        self.forward_horizon_days = int(forward_horizon_days)
        self.top_quantile = float(top_quantile)
        self.weight_method = str(weight_method)
        self.lookback_periods = int(lookback_periods)
        self.max_weight = float(max_weight)
        self.long_only = bool(long_only)
        self.min_pred_return = float(min_pred_return)
        self.retrain_each_call = bool(retrain_each_call)
        self._model: Any = None
        self._feature_cols: list[str] = []

    # -------------------------------------------------------- helpers --

    def _ensure_model(self, panel: pd.DataFrame) -> None:
        if self._model is not None and not self.retrain_each_call:
            return
        X, y, cols = _build_supervised_dataset(panel, self.forward_horizon_days)
        if X.empty:
            self._model = None
            self._feature_cols = []
            return
        try:
            self._model = _train_model(
                X,
                y,
                model_kind=self.model_kind,
                model_kwargs=self.model_kwargs,
            )
            self._feature_cols = cols
        except Exception:
            logger.exception("MLStockSelectionAlpha: training failed")
            self._model = None
            self._feature_cols = []

    def _select(self, latest: pd.DataFrame, preds: np.ndarray) -> tuple[list[str], dict[str, float]]:
        if not len(preds):
            return [], {}
        scored = pd.DataFrame(
            {
                "vt_symbol": latest["vt_symbol"].values,
                "score": preds,
            }
        )
        threshold = scored["score"].quantile(float(self.top_quantile))
        scored = scored[scored["score"] >= threshold]
        scored = scored[scored["score"] >= self.min_pred_return]
        if scored.empty:
            return [], {}
        scored = scored.sort_values("score", ascending=False)
        selected = scored["vt_symbol"].tolist()
        return selected, dict(zip(scored["vt_symbol"], scored["score"]))

    # ----------------------------------------- IAlphaModel.generate_signals --

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        panel = _features_panel(
            bars,
            feature_set_name=self.feature_set_name,
            feature_specs=self.feature_specs,
        )
        self._ensure_model(panel)
        if self._model is None:
            return []
        latest = (
            panel.sort_values("timestamp")
            .groupby("vt_symbol")
            .tail(1)
            .reset_index(drop=True)
        )
        if latest.empty or not self._feature_cols:
            return []
        cols = [c for c in self._feature_cols if c in latest.columns]
        if not cols:
            return []
        try:
            preds = self._model.predict(latest[cols].fillna(0.0).values)
        except Exception:
            logger.exception("MLStockSelectionAlpha: predict failed")
            return []
        preds = np.asarray(preds, dtype=float).reshape(-1)
        universe_set = {s.vt_symbol for s in universe}
        latest = latest[latest["vt_symbol"].isin(universe_set)].reset_index(drop=True)
        if latest.empty:
            return []
        # Keep preds aligned to the filtered ``latest``.
        symbol_to_pred = dict(zip(latest["vt_symbol"], preds[: len(latest)]))
        latest_preds = np.array([symbol_to_pred[s] for s in latest["vt_symbol"]])
        selected, scores = self._select(latest, latest_preds)
        if not selected:
            return []
        weights = _allocate_weights(
            selected,
            panel,
            method=self.weight_method,  # type: ignore[arg-type]
            lookback_periods=self.lookback_periods,
            max_weight=self.max_weight,
        )
        ts = context.get("current_time")
        if ts is None and not bars.empty:
            ts = pd.to_datetime(bars["timestamp"]).max()
        out: list[Signal] = []
        for sym in selected:
            w = float(weights.get(sym, 0.0))
            if w <= 0:
                continue
            score = float(scores.get(sym, 0.0))
            direction = (
                Direction.LONG if score >= 0 or self.long_only else Direction.SHORT
            )
            out.append(
                Signal(
                    symbol=Symbol.parse(sym),
                    strength=float(min(1.0, max(0.0, w))),
                    direction=direction,
                    timestamp=ts,
                    confidence=float(min(1.0, abs(score) * 5)),
                    horizon_days=self.forward_horizon_days,
                    source=type(self).__name__,
                    rationale=(
                        f"pred={score:.4f} weight={w:.3f} method={self.weight_method}"
                    ),
                )
            )
        return out


@register(
    "SectorNeutralMLAlpha",
    kind="strategy",
    tags=("ml", "stock_selection", "supervised", "sector_neutral"),
    source="finrl_trading",
    category="ml_selection",
)
class SectorNeutralMLAlpha(MLStockSelectionAlpha):
    """Sector-neutral version: select per-sector quantiles.

    Resolves sectors from
    :class:`aqp.persistence.models_entities.IndustryClassification`
    when available; otherwise falls back to :class:`Instrument.sector`.
    """

    def __init__(
        self,
        per_sector_quantile: float | None = None,
        target_sector_weights: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.per_sector_quantile = (
            float(per_sector_quantile) if per_sector_quantile is not None else self.top_quantile
        )
        self.target_sector_weights = target_sector_weights or {}

    def _sector_map(self, vt_symbols: list[str]) -> dict[str, str]:
        if not vt_symbols:
            return {}
        try:
            from sqlalchemy import select as _sel

            from aqp.persistence.db import get_session
            from aqp.persistence.models import Instrument

            with get_session() as session:
                rows = session.execute(
                    _sel(Instrument).where(Instrument.vt_symbol.in_(vt_symbols))
                ).scalars().all()
            return {r.vt_symbol: (r.sector or "unknown") for r in rows}
        except Exception:
            logger.info("SectorNeutralMLAlpha: sector map lookup failed", exc_info=True)
            return {}

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        panel = _features_panel(
            bars,
            feature_set_name=self.feature_set_name,
            feature_specs=self.feature_specs,
        )
        self._ensure_model(panel)
        if self._model is None:
            return []
        latest = (
            panel.sort_values("timestamp")
            .groupby("vt_symbol")
            .tail(1)
            .reset_index(drop=True)
        )
        cols = [c for c in self._feature_cols if c in latest.columns]
        if not cols or latest.empty:
            return []
        try:
            preds = self._model.predict(latest[cols].fillna(0.0).values)
        except Exception:
            logger.exception("SectorNeutralMLAlpha: predict failed")
            return []
        latest = latest.copy()
        latest["score"] = np.asarray(preds, dtype=float)[: len(latest)]
        sector_map = self._sector_map(latest["vt_symbol"].tolist())
        latest["sector"] = latest["vt_symbol"].map(lambda s: sector_map.get(s, "unknown"))
        kept_rows: list[pd.DataFrame] = []
        for sector, group in latest.groupby("sector", sort=False):
            if group.empty:
                continue
            thr = group["score"].quantile(self.per_sector_quantile)
            sub = group[group["score"] >= thr]
            sub = sub[sub["score"] >= self.min_pred_return]
            kept_rows.append(sub)
        kept = pd.concat(kept_rows, ignore_index=True) if kept_rows else pd.DataFrame()
        if kept.empty:
            return []
        # Sector-target re-weighting
        if self.target_sector_weights:
            sector_weights: dict[str, float] = {}
            for sector, target_w in self.target_sector_weights.items():
                members = kept[kept["sector"] == sector]
                if members.empty:
                    continue
                inner_w = 1.0 / len(members)
                for _, row in members.iterrows():
                    sector_weights[row["vt_symbol"]] = float(target_w) * inner_w
            if sector_weights:
                total = sum(sector_weights.values())
                if total > 0:
                    sector_weights = {k: v / total for k, v in sector_weights.items()}
                weights = sector_weights
            else:
                weights = _allocate_weights(
                    kept["vt_symbol"].tolist(),
                    panel,
                    method=self.weight_method,  # type: ignore[arg-type]
                    lookback_periods=self.lookback_periods,
                    max_weight=self.max_weight,
                )
        else:
            weights = _allocate_weights(
                kept["vt_symbol"].tolist(),
                panel,
                method=self.weight_method,  # type: ignore[arg-type]
                lookback_periods=self.lookback_periods,
                max_weight=self.max_weight,
            )
        ts = context.get("current_time")
        if ts is None and not bars.empty:
            ts = pd.to_datetime(bars["timestamp"]).max()
        out: list[Signal] = []
        scores = dict(zip(kept["vt_symbol"], kept["score"]))
        for sym, w in weights.items():
            if w <= 0:
                continue
            score = float(scores.get(sym, 0.0))
            out.append(
                Signal(
                    symbol=Symbol.parse(sym),
                    strength=float(min(1.0, max(0.0, w))),
                    direction=Direction.LONG,
                    timestamp=ts,
                    confidence=float(min(1.0, abs(score) * 5)),
                    horizon_days=self.forward_horizon_days,
                    source=type(self).__name__,
                    rationale=f"sector={sector_map.get(sym, 'unknown')} pred={score:.4f} w={w:.3f}",
                )
            )
        return out


__all__ = [
    "MLStockSelectionAlpha",
    "SectorNeutralMLAlpha",
]
