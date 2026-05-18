"""Tests for the IcebergNamespacePolicy OpenMetadata model."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from aqp.metadata.openmetadata import IcebergNamespacePolicy


def test_iceberg_namespace_policy_round_trips_json() -> None:
    """Valid policy payloads should round-trip through model_dump/model_validate."""
    policy = IcebergNamespacePolicy(
        urn="urn:aqp:namespace_policy:prod:w1",
        policy_name="Workspace W1 policy",
        bronze_prefix="tenant_w1_bronze_",
        silver_prefix="tenant_w1_silver_",
        gold_prefix="tenant_w1_gold_",
        applies_to_workspace_id="w1",
        priority=10,
    )

    reloaded = IcebergNamespacePolicy.model_validate(policy.model_dump(mode="json"))
    assert reloaded.urn == "urn:aqp:namespace_policy:prod:w1"
    assert reloaded.bronze_prefix == "tenant_w1_bronze_"
    assert reloaded.applies_to_workspace_id == "w1"


def test_iceberg_namespace_policy_prefixes_require_trailing_underscore() -> None:
    """Namespace prefixes must end with an underscore."""
    with pytest.raises(ValidationError):
        IcebergNamespacePolicy(
            urn="urn:aqp:namespace_policy:prod:w1",
            policy_name="Workspace W1 policy",
            bronze_prefix="tenant_w1_bronze",
            silver_prefix="tenant_w1_silver_",
            gold_prefix="tenant_w1_gold_",
        )
