"""In-cluster builders + manifest renderers for the control plane.

Two builders ship today:

- :mod:`aqp_cp.builders.tenant` — renders the canonical four-object
  tenant namespace bundle (Namespace + ResourceQuota + LimitRange +
  NetworkPolicy) via Jinja.
- :mod:`aqp_cp.builders.kaniko` — submits Chainguard-Kaniko ``Job``
  pods for in-cluster OCI image builds.

Both consume :class:`aqp_platform_core.providers.InfrastructureProvider`
implementations (typically :class:`aqp_cp.providers.kubernetes.KubernetesProvider`)
and respect the :class:`aqp_platform_core.runtime.WorkloadRuntime`
audit lifecycle.
"""
from __future__ import annotations

__all__: list[str] = []
