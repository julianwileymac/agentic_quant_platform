"""Native qlib-style ML framework for AQP.

Vendored abstractions (no qlib runtime dep) so ML models, feature handlers,
datasets, loaders, and record templates share a single contract across the
classical tree/linear stack and the PyTorch zoo.

Public surface (subset) — everything else is re-exported here so callers
can write::

    from aqp.ml import DatasetH, Alpha158, LGBModel, SignalRecord
"""
from __future__ import annotations

import contextlib

from aqp.ml.base import (
    BaseModel,
    EqualWeightReweighter,
    Model,
    ModelFT,
    Reweighter,
    Serializable,
)
from aqp.ml.dataset import Dataset, DatasetH, TSDataSampler, TSDatasetH
from aqp.ml.handler import (
    DK_I,
    DK_L,
    DK_R,
    DataHandler,
    DataHandlerABC,
    DataHandlerLP,
)
from aqp.ml.loader import AQPDataLoader, DataLoader, DLWParser
from aqp.ml.planning import PlannedSplit, artifacts_to_segments, build_split_plan
from aqp.ml.processors import (
    CSRankNorm,
    CSZScoreNorm,
    CoerceNumericColumns,
    DropnaLabel,
    Fillna,
    FilterCol,
    LagFeatureGenerator,
    MinMaxNorm,
    PanelForwardFill,
    PreprocessingSpec,
    Processor,
    RollingFeatureGenerator,
    SeasonalDecomposeFeatures,
    SklearnTransformerProcessor,
    WinsorizeByQuantile,
)
from aqp.ml.recorder import PortAnaRecord, RecordTemplate, SigAnaRecord, SignalRecord
from aqp.ml.splits import (
    TrainValTestWindow,
    chronological_train_val_test_split,
    quarterly_point_in_time_split,
    rolling_train_val_test_windows,
)

# Feature factories (Alpha158 / Alpha360) — expose for convenient imports.
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.features.alpha158 import Alpha158, Alpha158DL  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.features.alpha360 import Alpha360, Alpha360DL  # noqa: F401

# Tree / linear models (no torch).
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.tree import CatBoostModel, LGBModel, XGBModel  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.linear import LinearModel  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.ensemble import DEnsembleModel  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.sklearn import (  # noqa: F401
        SklearnClassifierModel,
        SklearnPipelineModel,
        SklearnRegressorModel,
    )
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.forecasting import (  # noqa: F401
        ProphetForecastModel,
        SktimeForecastModel,
        SktimeReductionForecastModel,
    )
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.anomaly import PyODAnomalyModel  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.keras import KerasLSTMModel, KerasMLPModel  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.huggingface import HuggingFaceTextSignalModel  # noqa: F401

# Inspiration rehydration sub-packages (SPM / notebooks / SAE) — import for
# @register side effects. Lazy ``contextlib.suppress`` so missing torch /
# statsmodels / arch don't break the whole package.
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models import spm as _spm_pkg  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models import notebooks as _notebooks_ml_pkg  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models import sae as _sae_ml_pkg  # noqa: F401
with contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.walk_forward import WalkForwardSplitter, WalkForwardTrainer, SimpleSliceDataset  # noqa: F401

__all__ = [
    "BaseModel",
    "DK_I",
    "DK_L",
    "DK_R",
    "DLWParser",
    "DataHandler",
    "DataHandlerABC",
    "DataHandlerLP",
    "DataLoader",
    "AQPDataLoader",
    "Dataset",
    "DatasetH",
    "DropnaLabel",
    "EqualWeightReweighter",
    "FilterCol",
    "Fillna",
    "LagFeatureGenerator",
    "CSRankNorm",
    "CSZScoreNorm",
    "CoerceNumericColumns",
    "MinMaxNorm",
    "Model",
    "ModelFT",
    "PanelForwardFill",
    "PortAnaRecord",
    "PlannedSplit",
    "PreprocessingSpec",
    "Processor",
    "RollingFeatureGenerator",
    "SeasonalDecomposeFeatures",
    "SklearnTransformerProcessor",
    "RecordTemplate",
    "Reweighter",
    "Serializable",
    "SigAnaRecord",
    "SignalRecord",
    "TSDataSampler",
    "TSDatasetH",
    "TrainValTestWindow",
    "WinsorizeByQuantile",
    "artifacts_to_segments",
    "build_split_plan",
    "chronological_train_val_test_split",
    "quarterly_point_in_time_split",
    "rolling_train_val_test_windows",
]
