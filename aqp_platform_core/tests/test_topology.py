"""Topology model smoke tests — parse the canonical YAML."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aqp_platform_core.topology import DeploymentTopology

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOPOLOGY_YAML = _REPO_ROOT / "configs" / "deployment" / "topology.yaml"


@pytest.mark.skipif(
    not _TOPOLOGY_YAML.exists(),
    reason="canonical topology.yaml not present in this checkout",
)
def test_canonical_topology_parses() -> None:
    raw = yaml.safe_load(_TOPOLOGY_YAML.read_text(encoding="utf-8"))
    topology = DeploymentTopology.model_validate(raw)
    assert topology.version == 1
    assert "local" in topology.targets
    assert "rpi" in topology.targets

    local = topology.target("local")
    assert local.kind == "local"
    assert local.namespace == "aqp-local"


def test_unknown_service_reference_raises() -> None:
    bad_topology = {
        "version": 1,
        "services": [
            {
                "id": "aqp-api",
                "label": "AQP API",
                "role": "api",
                "workload": "deployment",
                "app_label": "aqp-api",
            }
        ],
        "targets": {
            "local": {
                "id": "local",
                "label": "Local",
                "kind": "local",
                "environment": "local",
                "cloud_provider": "local",
                "namespace": "aqp-local",
                "terraform": {
                    "stack_slug": "aqp-local",
                    "spec_path": "x.yaml",
                    "environment_dir": "x",
                },
                "cluster": {"name": "aqp-local"},
                "services": ["aqp-api", "ghost-service"],
            }
        },
    }
    with pytest.raises(ValueError, match="ghost-service"):
        DeploymentTopology.model_validate(bad_topology)


def test_target_key_mismatch_rejected() -> None:
    bad = {
        "version": 1,
        "services": [],
        "targets": {
            "local": {
                "id": "different-id",
                "label": "Local",
                "kind": "local",
                "environment": "local",
                "cloud_provider": "local",
                "namespace": "aqp-local",
                "terraform": {
                    "stack_slug": "aqp-local",
                    "spec_path": "x.yaml",
                    "environment_dir": "x",
                },
                "cluster": {"name": "aqp-local"},
                "services": [],
            }
        },
    }
    with pytest.raises(ValueError, match="does not match target id"):
        DeploymentTopology.model_validate(bad)
