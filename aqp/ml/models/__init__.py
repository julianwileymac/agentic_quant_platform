"""Model zoo — tree / linear / ensemble + PyTorch subfamilies.

Import is intentionally permissive: if an optional extra is missing
(``xgboost``, ``lightgbm``, ``torch``, etc.) the module still imports so
the YAML registry keeps working for other models.
"""
from __future__ import annotations

import contextlib

with contextlib.suppress(Exception):
    from aqp.ml.models.tree import CatBoostModel, LGBModel, XGBModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.linear import LinearModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.ensemble import DEnsembleModel  # noqa: F401
