"""Deployment topology helpers.

The Pydantic data classes (`DeploymentTarget`, `DeploymentTopology`,
`ServiceDefinition`, etc.) have a JSON-compatible mirror in
`aqp_platform_core.topology` (the shared package consumed by
`aqp_control_plane`). The two model trees are byte-identical at the
JSON layer. Code inside `aqp/` keeps using these classes; the
control plane uses `aqp_platform_core.topology` instances. Migration
to a single shared class hierarchy happens in a follow-up PR.

See `aqp_docs/architecture/decisions/005-separated-control-plane.md`.
"""
from __future__ import annotations

from aqp.deployment.topology import (
    DeploymentTarget,
    DeploymentTopology,
    ServiceDefinition,
    get_deployment_topology,
    get_target,
    list_targets,
)

__all__ = [
    "DeploymentTarget",
    "DeploymentTopology",
    "ServiceDefinition",
    "get_deployment_topology",
    "get_target",
    "list_targets",
]
