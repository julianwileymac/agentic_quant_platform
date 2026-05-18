"""Tests for the Jinja2 HCL codegen pipeline.

These tests don't shell out to terraform — they assert the rendered
HCL contains the canonical blocks the operator expects (terraform {},
locals.common_tags, module / resource blocks, etc).
"""
from __future__ import annotations

import pytest

from aqp.terraform.codegen import render_module, render_spec
from aqp.terraform.codegen.base import hcl_string, hcl_value
from aqp.terraform.spec import (
    TerraformBackendRef,
    TerraformModuleRef,
    TerraformOutputRef,
    TerraformResourceRef,
    TerraformStackSpec,
    TerraformVariableRef,
)


def test_hcl_string_escapes_double_quotes():
    assert hcl_string('hello "world"') == r'"hello \"world\""'


def test_hcl_value_bool_null_int():
    assert hcl_value(True) == "true"
    assert hcl_value(None) == "null"
    assert hcl_value(42) == "42"


def test_hcl_value_list_emits_json():
    assert hcl_value(["a", "b"]) == '["a", "b"]'


def test_render_spec_contains_canonical_blocks():
    spec = TerraformStackSpec(
        name="Cluster",
        slug="cluster",
        module_kind="kubernetes",
        environment="local",
        cloud_provider="local",
        common_tags={"owner": "julian"},
        modules=[
            TerraformModuleRef(
                name="cluster",
                source="../modules/kubernetes",
                variables={"namespace_count": 4},
            )
        ],
        backend=TerraformBackendRef(kind="local", config={"path": "tfstate"}),
        variables=[TerraformVariableRef(name="cluster_name", type="string", default="aqp-local")],
        outputs=[TerraformOutputRef(name="kubeconfig", value="module.cluster.kubeconfig")],
        resources=[
            TerraformResourceRef(
                type="null_resource",
                name="bootstrap",
                body={"triggers": {"slug": "cluster"}},
            )
        ],
    )
    hcl = render_spec(spec)
    assert "terraform {" in hcl
    assert 'backend "local"' in hcl
    assert "locals {" in hcl
    assert "common_tags" in hcl
    assert 'variable "cluster_name"' in hcl
    assert 'module "cluster"' in hcl
    assert 'resource "null_resource" "bootstrap"' in hcl
    assert 'output "kubeconfig"' in hcl


def test_render_module_falls_back_when_template_missing():
    """No template for an unknown kind -> a NOTE comment, not a crash."""
    out = render_module(module_kind="nonexistent", cloud_provider="local")
    assert "No template found" in out


def test_render_module_picks_per_cloud_template():
    """storage_local.tf.j2 exists; renders Docker containers."""
    spec = TerraformStackSpec(
        name="Storage local", slug="storage-local",
        module_kind="storage", environment="local", cloud_provider="local",
    )
    hcl = render_spec(spec)
    # The storage_local template should contribute docker_container blocks.
    assert "docker_container" in hcl
