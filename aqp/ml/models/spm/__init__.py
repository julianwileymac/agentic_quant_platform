"""SPM (huseinzol05/Stock-Prediction-Models) ports.

Architectures originally written in TF1 graph mode, ported to PyTorch
via :mod:`aqp.ml.models.spm._torch_base`. See
``extractions/stock_prediction_models/REFERENCE.md`` for per-model notes
and known-issues caveats.
"""
from __future__ import annotations

import contextlib as _contextlib

# Side-effect: register all forecaster classes via @register decorators.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.spm.forecasters import (  # noqa: F401
        AttentionOnlyForecaster,
        BERTForecaster,
        BidirectionalGRU,
        BidirectionalLSTM,
        Conv1DForecaster,
        GRUForecaster,
        LSTMAttention,
        LSTMForecaster,
        LSTMGRUHybrid,
        MonteCarloDropoutForecaster,
        StackedLSTM,
        TCNForecaster,
        TransformerForecaster,
        VanillaRNN,
    )

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.ml.models.spm.classical import (  # noqa: F401
        ARIMAForecaster,
        BayesianRidgeForecaster,
        GARCHForecaster,
        ProphetForecaster,
    )
