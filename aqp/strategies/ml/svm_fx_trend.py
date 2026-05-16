"""Support-vector-machine FX trend-following alpha.

Inspired by MS&E 448 (Stanford 2016) "ML Trend Following" project:
fit an SVM classifier on lagged FX-specific features (returns,
realised vol, EMAs) to predict next-bar return sign, then trade only
when the class-probability margin exceeds a threshold.

The model is trained lazily on first use, on the in-sample tail of
the bars passed to ``generate_signals``. For production deployment
the trained ``sklearn.svm.SVC`` (with ``probability=True``) can be
supplied externally via the ``model`` argument and the strategy will
skip training.

scikit-learn is required for training/inference; the strategy
degrades to a `_noop` no-signal mode if sklearn isn't installed so
imports stay cheap.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

try:  # pragma: no cover - exercised by the import test
    from sklearn.preprocessing import StandardScaler  # type: ignore[import-not-found]
    from sklearn.svm import SVC  # type: ignore[import-not-found]

    _SKLEARN_AVAILABLE = True
except Exception:  # noqa: BLE001
    StandardScaler = None  # type: ignore[assignment]
    SVC = None  # type: ignore[assignment]
    _SKLEARN_AVAILABLE = False


def _fx_features(sub: pd.DataFrame, *, lags: int = 5) -> np.ndarray:
    """Stack lagged log-returns, EMA, and realised-vol features."""
    close = sub["close"].astype(float).to_numpy()
    if close.size < lags + 12:
        return np.empty((0, 0))
    ret = np.diff(np.log(np.maximum(close, 1e-12)))
    feats: list[np.ndarray] = []
    for lag in range(1, lags + 1):
        feats.append(np.r_[np.full(lag, np.nan), ret[:-lag] if lag else ret])
    # EMA over 5 and 20 bars (windowed mean for portability).
    feats.append(pd.Series(ret).ewm(span=5, adjust=False).mean().to_numpy())
    feats.append(pd.Series(ret).ewm(span=20, adjust=False).mean().to_numpy())
    # Realised volatility (rolling std of returns).
    feats.append(pd.Series(ret).rolling(10).std().to_numpy())
    feats.append(pd.Series(ret).rolling(30).std().to_numpy())
    stacked = np.stack(feats, axis=1)
    # Align to a common shape: drop the first 30 rows so all feats are
    # populated.
    return stacked


@register(
    "SVMFXTrendAlpha",
    source="research_report_2026",
    category="machine_learning",
    kind="strategy",
)
class SVMFXTrendAlpha(IAlphaModel):
    """SVM-classifier-based FX trend signal.

    Parameters
    ----------
    lags
        Number of lagged log-return features.
    train_window
        Bars to use for in-sample training when ``model`` is None.
    margin_threshold
        Minimum |P(long) - P(short)| required to emit a signal.
    hold_bars
        Forecast horizon.
    C
        SVM regularisation parameter.
    model
        Pre-trained ``sklearn.svm.SVC`` (with ``probability=True``)
        and an optional ``"scaler"`` paired in a tuple; if supplied,
        training is skipped.
    """

    def __init__(
        self,
        lags: int = 5,
        train_window: int = 300,
        margin_threshold: float = 0.1,
        hold_bars: int = 1,
        C: float = 1.0,
        model: tuple[Any, Any] | None = None,
    ) -> None:
        self.lags = int(lags)
        self.train_window = int(train_window)
        self.margin_threshold = float(margin_threshold)
        self.hold_bars = int(hold_bars)
        self.C = float(C)
        self._model = model
        self._scaler = None

    def _ensure_fitted(self, sub: pd.DataFrame) -> bool:
        if self._model is not None:
            return True
        if not _SKLEARN_AVAILABLE:
            return False
        feats = _fx_features(sub.tail(self.train_window), lags=self.lags)
        if feats.size == 0 or feats.shape[0] < 50:
            return False
        # Build labels from forward 1-bar return sign.
        close = sub["close"].astype(float).to_numpy()
        ret_next = np.diff(np.log(np.maximum(close, 1e-12)))
        ret_next = ret_next[-feats.shape[0] :]
        valid = np.isfinite(feats).all(axis=1) & np.isfinite(ret_next)
        feats = feats[valid]
        labels = (ret_next[valid] > 0).astype(int)
        if feats.shape[0] < 30 or np.unique(labels).size < 2:
            return False
        scaler = StandardScaler().fit(feats)
        X = scaler.transform(feats)
        svc = SVC(kernel="rbf", C=self.C, probability=True)
        svc.fit(X, labels)
        self._model = (svc, scaler)
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
            svc, scaler = self._model
            feats = _fx_features(sub, lags=self.lags)
            if feats.size == 0:
                continue
            last_feats = feats[-1:]
            if not np.isfinite(last_feats).all():
                continue
            X = scaler.transform(last_feats)
            probs = svc.predict_proba(X)[0]
            # Standard sklearn binary order is [class_0, class_1].
            p_short = float(probs[0])
            p_long = float(probs[1])
            margin = p_long - p_short
            if abs(margin) < self.margin_threshold:
                continue
            direction = Direction.LONG if margin > 0 else Direction.SHORT
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt_symbol),
                    strength=float(min(abs(margin), 1.0)),
                    direction=direction,
                    timestamp=now or sub["timestamp"].iloc[-1],
                    confidence=float(max(p_long, p_short)),
                    horizon_days=self.hold_bars,
                    source="SVMFXTrendAlpha",
                    rationale=(
                        f"p_long={p_long:.3f} p_short={p_short:.3f} "
                        f"margin={margin:.3f}"
                    ),
                )
            )
        return signals
