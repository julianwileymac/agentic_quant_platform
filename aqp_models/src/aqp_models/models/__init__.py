"""Model zoo — tree / linear / ensemble + PyTorch subfamilies.

Import is intentionally permissive: if an optional extra is missing
(``xgboost``, ``lightgbm``, ``torch``, etc.) the module still imports so
the YAML registry keeps working for other models.
"""
from __future__ import annotations

import contextlib

with contextlib.suppress(Exception):
    from aqp_models.models.tree import CatBoostModel, LGBModel, XGBModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.naive_bayes import NaiveBayesSentimentModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.linear import LinearModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.ensemble import DEnsembleModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.highfreq_gbdt import HighFreqGBDT  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.sklearn import (  # noqa: F401
        SklearnAutoPipelineModel,
        SklearnClassifierModel,
        SklearnPipelineModel,
        SklearnRegressorModel,
        SklearnStackingModel,
    )
with contextlib.suppress(Exception):
    from aqp_models.models.forecasting import (  # noqa: F401
        AutoARIMAForecastModel,
        AutoETSForecastModel,
        BatsTbatsForecastModel,
        ProphetForecastModel,
        SktimeForecastModel,
        SktimeReductionForecastModel,
        ThetaForecastModel,
    )
with contextlib.suppress(Exception):
    from aqp_models.models.anomaly import PyODAnomalyModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.keras import (  # noqa: F401
        KerasFunctionalModel,
        KerasLSTMModel,
        KerasMLPModel,
        KerasTabTransformerModel,
    )
with contextlib.suppress(Exception):
    from aqp_models.models.tensorflow import TFEstimatorModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.huggingface import (  # noqa: F401
        HuggingFaceFinBertSentimentModel,
        HuggingFaceGenerativeForecastModel,
        HuggingFaceTextSignalModel,
        HuggingFaceTimeSeriesModel,
    )

# ---------------------------------------------------------------------------
# Tier-B PyTorch model ports — each is registered when ``torch`` is available.
# ---------------------------------------------------------------------------
with contextlib.suppress(Exception):
    from aqp_models.models.torch.hist import HISTModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.gats import GATsModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.tra import TRAModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.add import ADDModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.adarnn import ADARNNModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.tcts import TCTSModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.sfm import SFMModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.sandwich import SandwichModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.krnn import KRNNModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.igmtf import IGMTFModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp_models.models.torch.ts_aliases import (  # noqa: F401
        ALSTMTSModel,
        GATsTSModel,
        GRUTSModel,
        LSTMTSModel,
        LocalformerTSModel,
        TCNTSModel,
        TransformerTSModel,
    )
