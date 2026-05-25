"""External-registry adapters for model + tokenizer + example imports.

The adapters wrap third-party model registries (Hugging Face Hub,
TorchHub) behind a small AQP-shaped surface so the agent layer + the
operator UI don't reach for the libraries directly. Every adapter:

* Resolves any required auth tokens through
  :class:`aqp.credentials.CredentialResolver` (Hard Rule 26).
* Caches downloaded artifacts on the same local volume the
  :class:`aqp_models.handlers.CacheHandler` watches.
* Verifies SHA-256 / commit checksums where the upstream registry
  exposes them so a tampered binary cannot reach the serving layer.
* Returns a uniform :class:`PullResult` dataclass.

Adapters self-register via :class:`RegistryAdapterMeta` so adding a new
backing registry (e.g. an internal artifact store) is one class.
"""
from __future__ import annotations

from aqp_models.adapters.base import (
    RegistryAdapter,
    RegistryAdapterMeta,
    PullResult,
    get_adapter,
    list_adapters,
)
from aqp_models.adapters.huggingface_adapter import HuggingFaceAdapter
from aqp_models.adapters.torchhub_adapter import TorchHubAdapter

__all__ = [
    "HuggingFaceAdapter",
    "PullResult",
    "RegistryAdapter",
    "RegistryAdapterMeta",
    "TorchHubAdapter",
    "get_adapter",
    "list_adapters",
]
