"""No-op :class:`KubernetesAdapter`.

The default. Every cluster-side method raises
:class:`KubernetesAdapterUnavailable`, which routes catch and translate
to ``HTTP 503``. Use this when AQP runs without any Kubernetes attach
(pure Docker-Compose / laptop dev).
"""
from __future__ import annotations

from aqp.kubernetes.protocol import KubernetesAdapter


class NoneAdapter(KubernetesAdapter):
    """No cluster attach; everything degrades to 503."""

    adapter_kind = "none"
    adapter_alias = "NoneAdapter"

    def is_available(self) -> bool:
        return False


__all__ = ["NoneAdapter"]
