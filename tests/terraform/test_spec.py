"""Tests for :class:`aqp.terraform.spec.TerraformStackSpec` hash + YAML."""
from __future__ import annotations

import pytest

from aqp.terraform.spec import (
    TerraformBackendRef,
    TerraformModuleRef,
    TerraformStackSpec,
    TerraformVariableRef,
)


def _sample_spec() -> TerraformStackSpec:
    return TerraformStackSpec(
        name="Sample",
        slug="sample",
        module_kind="storage",
        environment="local",
        cloud_provider="local",
        variables=[TerraformVariableRef(name="region", type="string", default="us-east-1")],
        modules=[
            TerraformModuleRef(
                name="storage",
                source="../modules/storage",
                variables={"cloud_provider": "local"},
            )
        ],
        backend=TerraformBackendRef(kind="local", config={"path": "./tfstate"}),
    )


def test_slug_inferred_from_name():
    spec = TerraformStackSpec(name="Hello World Stack")
    assert spec.slug == "hello-world-stack"


def test_snapshot_hash_stable_across_equal_specs():
    a = _sample_spec()
    b = _sample_spec()
    assert a.snapshot_hash() == b.snapshot_hash()


def test_snapshot_hash_changes_on_variable_edit():
    a = _sample_spec()
    b = _sample_spec()
    b.variables[0].default = "eu-west-1"
    assert a.snapshot_hash() != b.snapshot_hash()


def test_yaml_round_trip():
    spec = _sample_spec()
    rendered = spec.to_yaml()
    restored = TerraformStackSpec.from_yaml_str(rendered)
    assert restored.snapshot_hash() == spec.snapshot_hash()


def test_module_kind_validated():
    with pytest.raises(Exception):
        TerraformStackSpec(name="bad", module_kind="not-a-real-kind")  # type: ignore[arg-type]
