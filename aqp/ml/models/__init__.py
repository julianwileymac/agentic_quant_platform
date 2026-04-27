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
with contextlib.suppress(Exception):
    from aqp.ml.models.highfreq_gbdt import HighFreqGBDT  # noqa: F401

# ---------------------------------------------------------------------------
# Tier-B PyTorch model ports — each is registered when ``torch`` is available.
# ---------------------------------------------------------------------------
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.hist import HISTModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.gats import GATsModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.tra import TRAModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.add import ADDModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.adarnn import ADARNNModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.tcts import TCTSModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.sfm import SFMModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.sandwich import SandwichModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.krnn import KRNNModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.igmtf import IGMTFModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.ts_aliases import (  # noqa: F401
        ALSTMTSModel,
        GATsTSModel,
        GRUTSModel,
        LSTMTSModel,
        LocalformerTSModel,
        TCNTSModel,
        TransformerTSModel,
    )
