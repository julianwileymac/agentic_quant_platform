"""Lightweight, notebook-friendly ad-hoc helpers for ML libraries.

These ``quick_*`` functions wrap common one-off uses of scikit-learn,
sktime, Prophet, PyOD, and HuggingFace so analysts can iterate in a
Jupyter cell without spelling out a full ``Experiment`` config:

>>> from aqp.ml.adhoc import quick_ridge, quick_iforest, quick_prophet
>>> ridge = quick_ridge(features_df, target_series)
>>> ridge.score
0.42

Every helper returns a small dataclass with the key results so the
analyst can pivot quickly between libraries.
"""
from __future__ import annotations

from aqp.ml.adhoc.anomaly import (  # noqa: F401
    quick_ecod,
    quick_iforest,
    quick_lof,
)
from aqp.ml.adhoc.embeddings import (  # noqa: F401
    quick_finbert_sentiment,
    quick_text_embed,
)
from aqp.ml.adhoc.forecast import (  # noqa: F401
    quick_naive_baseline,
    quick_theta,
)
from aqp.ml.adhoc.regression import (  # noqa: F401
    quick_elasticnet,
    quick_panel_fixed_effects,
    quick_ridge,
)
from aqp.ml.adhoc.timeseries import (  # noqa: F401
    quick_arima,
    quick_decompose,
    quick_ets,
    quick_prophet,
)

__all__ = [
    "quick_arima",
    "quick_decompose",
    "quick_ecod",
    "quick_elasticnet",
    "quick_ets",
    "quick_finbert_sentiment",
    "quick_iforest",
    "quick_lof",
    "quick_naive_baseline",
    "quick_panel_fixed_effects",
    "quick_prophet",
    "quick_ridge",
    "quick_text_embed",
    "quick_theta",
]
