"""KubernetesAdapter exception hierarchy."""
from __future__ import annotations


class KubernetesAdapterError(RuntimeError):
    """Base class for adapter-side failures (HTTP errors, kubeconfig)."""


class KubernetesAdapterUnavailable(KubernetesAdapterError):
    """Raised when an adapter cannot service a specific call.

    The "none" adapter raises this for every method; feature-incomplete
    adapters raise it for unsupported methods. FastAPI routes catch
    it and return ``HTTP 503``.
    """


__all__ = ["KubernetesAdapterError", "KubernetesAdapterUnavailable"]
