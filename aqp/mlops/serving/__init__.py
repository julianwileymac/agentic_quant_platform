"""Model-serving adapters — MLflow Serve, Ray Serve, TorchServe.

Every deployment implements :class:`ModelDeployment` so higher-level code
can register a single ``aqp serve <backend> <model-uri>`` CLI / API that
is agnostic to the runtime.
"""
from __future__ import annotations

from aqp.mlops.serving.base import (
    DeploymentInfo,
    ModelDeployment,
    PreparedModel,
)

__all__ = [
    "DeploymentInfo",
    "ModelDeployment",
    "PreparedModel",
]
