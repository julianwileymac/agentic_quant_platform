"""PyTorch model zoo — imported lazily so the base install does not need torch.

Tier A (Dense / RNN / Transformer / TCN / TabNet / Localformer / Seq2Seq)
ship with full implementations. Tier B (GATs / HIST / TRA / ADD / ADARNN /
TCTS / SFM / Sandwich / KRNN / IGMTF) register correctly but raise
``NotImplementedError`` on ``fit`` so downstream code (Strategy Browser,
YAML registry) can still enumerate them.
"""
from __future__ import annotations

import contextlib

with contextlib.suppress(Exception):
    from aqp.ml.models.torch.dnn import DNNModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.lstm import LSTMModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.gru import GRUModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.alstm import ALSTMModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.transformer import TransformerModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.tcn import TCNModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.tabnet import TabNetModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.localformer import LocalformerModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.general_nn import GeneralPTNN  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.seq2seq import (  # noqa: F401
        DilatedCNNSeq2Seq,
        GRUSeq2Seq,
        LSTMSeq2Seq,
        LSTMSeq2SeqVAE,
        TransformerForecaster,
    )

# Stock-Prediction-Models expansions.
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.bidirectional import (  # noqa: F401
        BidirectionalGRUModel,
        BidirectionalLSTMModel,
    )
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.two_path import TwoPathGRUModel, TwoPathLSTMModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.vanilla_rnn import VanillaRNNModel  # noqa: F401
with contextlib.suppress(Exception):
    from aqp.ml.models.torch.attention_all import AttentionAllModel  # noqa: F401

# Tier B stubs — always register even if torch isn't installed so YAMLs
# referencing these classes surface a clear error message rather than a
# ``ClassNotFound`` during config load.
with contextlib.suppress(Exception):
    from aqp.ml.models.torch import stubs  # noqa: F401
