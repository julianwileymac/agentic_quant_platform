"""ML model ports from notebooks-master."""
from __future__ import annotations

import contextlib as _contextlib

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.notebooks.ridge_voc import RidgeVoCForecaster  # noqa: F401
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.notebooks.logistic_walk_forward import LogisticWalkForwardClassifier  # noqa: F401
