"""Time-series (``_ts``) aliases for sequence-based models.

Qlib's contrib zoo distinguishes ``LSTM`` (frame-shaped ``DatasetH``)
from ``LSTM_TS`` (sliding-window ``TSDatasetH``). In AQP, all of our
sequence models share the same ``BaseTorchModel`` with ``is_sequence =
True`` and consume ``TSDataSampler`` via ``_common._sequence_tensors``,
so the architectures are already TS-aware.

This module registers explicit ``*TSModel`` aliases so YAML recipes
can spell them out, mirroring qlib filenames (``pytorch_lstm_ts.py``,
``pytorch_gru_ts.py``, ``pytorch_alstm_ts.py``, ``pytorch_tcn_ts.py``,
``pytorch_localformer_ts.py``, ``pytorch_transformer_ts.py``,
``pytorch_gats_ts.py``).
"""
from __future__ import annotations

from aqp.core.registry import register
from aqp.ml.models.torch.alstm import ALSTMModel
from aqp.ml.models.torch.gats import GATsModel
from aqp.ml.models.torch.gru import GRUModel
from aqp.ml.models.torch.localformer import LocalformerModel
from aqp.ml.models.torch.lstm import LSTMModel
from aqp.ml.models.torch.tcn import TCNModel
from aqp.ml.models.torch.transformer import TransformerModel


@register("LSTMTSModel")
class LSTMTSModel(LSTMModel):
    """LSTM TS variant — same architecture, explicit TS naming."""


@register("GRUTSModel")
class GRUTSModel(GRUModel):
    """GRU TS variant."""


@register("ALSTMTSModel")
class ALSTMTSModel(ALSTMModel):
    """ALSTM TS variant."""


@register("TCNTSModel")
class TCNTSModel(TCNModel):
    """TCN TS variant."""


@register("LocalformerTSModel")
class LocalformerTSModel(LocalformerModel):
    """Localformer TS variant."""


@register("TransformerTSModel")
class TransformerTSModel(TransformerModel):
    """Transformer TS variant."""


@register("GATsTSModel")
class GATsTSModel(GATsModel):
    """GATs TS variant."""


__all__ = [
    "ALSTMTSModel",
    "GATsTSModel",
    "GRUTSModel",
    "LSTMTSModel",
    "LocalformerTSModel",
    "TCNTSModel",
    "TransformerTSModel",
]
