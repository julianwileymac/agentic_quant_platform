"""Pydantic models for the AQP deployment topology.

Mirrors the data classes in :mod:`aqp.deployment.topology` but
without the YAML loader (the loader stays in ``aqp/`` so it can read
from ``settings.deployment_topology_path``). Both planes import the
same models so a topology object built by ``aqp/`` round-trips
unchanged into the control plane.
"""
from __future__ import annotations

from aqp_platform_core.topology.loader import (
    TopologyLoadError,
    load_topology,
    reload_topology,
    reset_topology_cache,
    resolve_topology_path,
)
from aqp_platform_core.topology.models import (
    AuthDefinition,
    ClusterDefinition,
    DeploymentTarget,
    DeploymentTopology,
    ImageDefinition,
    LocalShellTooling,
    ServiceDefinition,
    StrictModel,
    TerraformTarget,
    TerraformTooling,
    Tooling,
    TopologyDefaults,
)

__all__ = [
    "AuthDefinition",
    "ClusterDefinition",
    "DeploymentTarget",
    "DeploymentTopology",
    "ImageDefinition",
    "LocalShellTooling",
    "ServiceDefinition",
    "StrictModel",
    "TerraformTarget",
    "TerraformTooling",
    "Tooling",
    "TopologyDefaults",
    "TopologyLoadError",
    "load_topology",
    "reload_topology",
    "reset_topology_cache",
    "resolve_topology_path",
]
