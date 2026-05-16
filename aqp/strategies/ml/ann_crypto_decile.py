"""ANN crypto decile-classifier alpha.

Inspired by the crypto-direction prediction recipe in the 151
Trading Strategies survey (Kakushadze 2016) and the 2026 research
report: train a small MLP on normalised technical features to
predict the *decile* of next-bar return, then long the top decile
and short the bottom decile.

The model is a tiny scikit-learn `MLPClassifier` (or a user-supplied
``sklearn``-compatible classifier with `predict_proba`). Features
are deliberately framework-light so the strategy stays import-cheap
when sklearn isn't installed.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

try:  # pragma: no cover - import-time check
    from sklearn.neural_network import MLPClassifier  # type: ignore[import-not-found]
    from sklearn.preprocessing import StandardScaler  # type: ignore[import-not-found]

    _SKLEARN_AVAILABLE = True
except Exception:  # noqa: BLE001
    MLPClassifier = None  # type: ignore[assignment]
    StandardScaler = None  # type: ignore[assignment]
    _SKLEARN_AVAILABLE = False


def _crypto_features(sub: pd.DataFrame, *, lookback: int = 30) -> np.ndarray:
    """Standardised technical features for a crypto bar series."""
    close = sub["close"].astype(float).to_numpy()
    if close.size < lookback + 5:
        return np.empty((0, 0))
    ret = pd.Series(np.diff(np.log(np.maximum(close, 1e-12))))
    feats = pd.DataFrame(
        {
            "ema_short": ret.ewm(span=5, adjust=False).mean(),
            "ema_long": ret.ewm(span=30, adjust=False).mean(),
            "vol_short": ret.rolling(10).std(),
            "vol_long": ret.rolling(30).std(),
            "momentum_5": ret.rolling(5).sum(),
            "momentum_20": ret.rolling(20).sum(),
        }
    )
    return feats.to_numpy()


def _decile(values: np.ndarray, n_deciles: int = 10) -> np.ndarray:
    """Return decile index in [0, n_deciles-1] for each value."""
    quantiles = np.linspace(0.0, 1.0, n_deciles + 1)
    edges = np.quantile(values, quantiles)
    return np.clip(np.digitize(values, edges[1:-1]), 0, n_deciles - 1)


@register(
    "ANNCryptoDecileAlpha",
    source="research_report_2026",
    category="machine_learning",
    kind="strategy",
)
class ANNCryptoDecileAlpha(IAlphaModel):
    """Top/bottom decile classifier-driven crypto alpha.

    Parameters
    ----------
    hidden_layer_sizes
        MLP architecture, passed through to sklearn.
    train_window
        Bars used for in-sample training when ``model`` is None.
    decile_threshold
        Probability mass on the top decile beyond which we go long
        (and similarly for the bottom).
    hold_bars
        Forecast horizon.
    """

    def __init__(
        self,
        hidden_layer_sizes: tuple[int, ...] = (32, 16),
        train_window: int = 500,
        decile_threshold: float = 0.2,
        n_deciles: int = 10,
        hold_bars: int = 1,
        model: tuple[Any, Any] | None = None,
    ) -> None:
        self.hidden_layer_sizes = tuple(int(h) for h in hidden_layer_sizes)
        self.train_window = int(train_window)
        self.decile_threshold = float(decile_threshold)
        self.n_deciles = int(n_deciles)
        self.hold_bars = int(hold_bars)
        self._model = model

    def _ensure_fitted(self, sub: pd.DataFrame) -> bool:
        if self._model is not None:
            return True
        if not _SKLEARN_AVAILABLE:
            return False
        feats = _crypto_features(sub.tail(self.train_window))
        close = sub["close"].astype(float).to_numpy()
        ret_next = np.diff(np.log(np.maximum(close, 1e-12)))
        ret_next = ret_next[-feats.shape[0] :]
        valid = np.isfinite(feats).all(axis=1) & np.isfinite(ret_next)
        if valid.sum() < 50:
            return False
        feats = feats[valid]
        ret_next = ret_next[valid]
        labels = _decile(ret_next, self.n_deciles)
        if np.unique(labels).size < 2:
            return False
        scaler = StandardScaler().fit(feats)
        X = scaler.transform(feats)
        mlp = MLPClassifier(
            hidden_layer_sizes=self.hidden_layer_sizes,
            max_iter=200,
            random_state=42,
        )
        mlp.fit(X, labels)
        self._model = (mlp, scaler)
        return True

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: Sequence[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        signals: list[Signal] = []
        now = context.get("current_time")
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if not self._ensure_fitted(sub):
                continue
            assert self._model is not None
            mlp, scaler = self._model
            feats = _crypto_features(sub)
            if feats.size == 0:
                continue
            last = feats[-1:]
            if not np.isfinite(last).all():
                continue
            X = scaler.transform(last)
            probs = mlp.predict_proba(X)[0]
            # Map MLP's class index back to its actual decile label.
            mapping = list(mlp.classes_)
            try:
                idx_top = mapping.index(self.n_deciles - 1)
            except ValueError:
                continue
            try:
                idx_bot = mapping.index(0)
            except ValueError:
                continue
            p_top = float(probs[idx_top])
            p_bot = float(probs[idx_bot])
            if p_top > self.decile_threshold and p_top > p_bot:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(p_top, 1.0)),
                        direction=Direction.LONG,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=float(p_top),
                        horizon_days=self.hold_bars,
                        source="ANNCryptoDecileAlpha",
                        rationale=f"P(top decile)={p_top:.3f}",
                    )
                )
            elif p_bot > self.decile_threshold and p_bot > p_top:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(p_bot, 1.0)),
                        direction=Direction.SHORT,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=float(p_bot),
                        horizon_days=self.hold_bars,
                        source="ANNCryptoDecileAlpha",
                        rationale=f"P(bottom decile)={p_bot:.3f}",
                    )
                )
        return signals
