"""ML model contracts — native ports of qlib's ``Model`` / ``ModelFT``.

These abstract base classes are what every concrete model in
:mod:`aqp.ml.models` implements. The contract is deliberately narrow so both
a LightGBM booster and a PyTorch Transformer present the exact same fit /
predict surface, keeping ``train_ml_model`` / ``SignalRecord`` generic.

Reference: ``inspiration/qlib-main/qlib/model/base.py``.
"""
from __future__ import annotations

import logging
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialisable — pickle helper base used by datasets + models.
# ---------------------------------------------------------------------------


class Serializable:
    """Tiny pickle helper. ``to_pickle`` / ``from_pickle`` mirror qlib."""

    default_dump_all = False
    exclude_attrs: tuple[str, ...] = ()

    def __getstate__(self) -> dict[str, Any]:
        state = dict(self.__dict__)
        for attr in self.exclude_attrs:
            state.pop(attr, None)
        return state

    def to_pickle(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh)

    @classmethod
    def from_pickle(cls, path: str | Path):
        with open(path, "rb") as fh:
            return pickle.load(fh)


# ---------------------------------------------------------------------------
# Reweighter — optional sample-weight policy fed into ``Model.fit``.
# ---------------------------------------------------------------------------


class Reweighter(ABC):
    """Contract for per-sample weighting strategies."""

    @abstractmethod
    def reweight(self, data: Any) -> np.ndarray:
        """Return a 1D array of non-negative weights aligned with ``data``."""


class EqualWeightReweighter(Reweighter):
    """Default no-op reweighter — every sample gets weight 1.0."""

    def reweight(self, data: Any) -> np.ndarray:
        length = getattr(data, "shape", (len(data),))[0]
        return np.ones(int(length), dtype=float)


# ---------------------------------------------------------------------------
# Model contracts.
# ---------------------------------------------------------------------------


class BaseModel(Serializable, ABC):
    """Root abstract model — every concrete class implements ``predict``."""

    # Attached when the model has been trained through a fitted processor
    # chain (see :class:`aqp.ml.processors.PreprocessingSpec`). ``None`` is
    # a valid value and simply means "no preprocessing was recorded".
    preprocessing_spec: Any | None = None

    @abstractmethod
    def predict(self, *args: Any, **kwargs: Any) -> Any:
        """Produce predictions. Signature varies by concrete subclass."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.predict(*args, **kwargs)

    def with_preprocessing(self, spec: Any) -> BaseModel:
        """Attach a :class:`aqp.ml.processors.PreprocessingSpec` and return
        ``self`` so call-sites can chain ``model.fit(...).with_preprocessing(spec)``.
        """
        self.preprocessing_spec = spec
        return self


class Model(BaseModel, ABC):
    """Standard ML model contract.

    Subclasses are expected to consume an :class:`aqp.ml.dataset.DatasetH`
    (or any object with a compatible ``prepare()`` method). The ``predict``
    method returns a ``pd.Series`` indexed by ``(datetime, vt_symbol)`` so
    it is immediately usable as an alpha signal.
    """

    @abstractmethod
    def fit(
        self,
        dataset: Any,
        reweighter: Reweighter | None = None,
    ) -> Model:
        """Train the model on ``dataset``. Must return ``self``."""

    @abstractmethod
    def predict(
        self,
        dataset: Any,
        segment: str | slice = "test",
    ) -> pd.Series:
        """Score the requested segment; returns ``(date, symbol) -> score``."""


class ModelFT(Model, ABC):
    """Model with a ``finetune`` hook for online / incremental updates."""

    @abstractmethod
    def finetune(self, dataset: Any) -> Model:
        """Incrementally retrain the model on the supplied dataset."""


__all__ = [
    "BaseModel",
    "EqualWeightReweighter",
    "Model",
    "ModelFT",
    "Reweighter",
    "Serializable",
]
