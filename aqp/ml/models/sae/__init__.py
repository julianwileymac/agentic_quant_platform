"""ML model ports from stock-analysis-engine."""
from __future__ import annotations

import contextlib as _contextlib

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.sae.keras_mlp_regressor import KerasMLPRegressor  # noqa: F401
