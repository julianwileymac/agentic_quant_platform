"""MLOps lifecycle handlers.

This subpackage owns the six report-mandated handler classes that
manage a model's lifecycle once it leaves the training task and starts
serving live agent traffic:

* :class:`CacheHandler` — LRU + safetensors-first in-memory cache of
  loaded model artifacts, sized by configurable VRAM / entry budget.
* :class:`LoadHandler` — cryptographic verification + deserialisation
  of a registered :class:`aqp.persistence.models.ModelVersion` artifact.
* :class:`SaveHandler` — serialise an in-memory model's state dict to
  disk (mirrors the qlib :meth:`Serializable.to_pickle` contract).
* :class:`StoreHandler` — async upload of saved artifacts into the
  object store + lineage tagging.
* :class:`ProductionizeHandler` — compile a trained model to ONNX /
  TensorRT / TorchScript via :mod:`aqp_models.productionize`.
* :class:`ServeHandler` — queue-based continuous-batching inference
  server. The default scheduler is a simple latency-bounded micro-batch
  loop; advanced backends (vLLM, TGI) hook in via
  :mod:`aqp_models.serving`.

All handlers share :class:`MLOpsHandler`'s ``policy_check`` + lineage
hooks so every lifecycle operation lands on the same audit surface.
"""
from __future__ import annotations

from aqp_models.handlers.base import (
    HandlerPolicyError,
    HandlerResult,
    MLOpsHandler,
)
from aqp_models.handlers.cache_handler import CacheHandler, CachedModel
from aqp_models.handlers.load_handler import LoadHandler, LoadResult
from aqp_models.handlers.productionize_handler import (
    ProductionizeHandler,
    ProductionizeResult,
)
from aqp_models.handlers.save_handler import SaveHandler, SaveResult
from aqp_models.handlers.serve_handler import (
    ServeHandler,
    ServingSession,
    ServingRequest,
)
from aqp_models.handlers.store_handler import StoreHandler, StoreResult

__all__ = [
    "CacheHandler",
    "CachedModel",
    "HandlerPolicyError",
    "HandlerResult",
    "LoadHandler",
    "LoadResult",
    "MLOpsHandler",
    "ProductionizeHandler",
    "ProductionizeResult",
    "SaveHandler",
    "SaveResult",
    "ServeHandler",
    "ServingRequest",
    "ServingSession",
    "StoreHandler",
    "StoreResult",
]
