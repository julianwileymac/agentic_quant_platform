"""Smoke tests for the local Terraform modules.

These tests don't run a real ``terraform validate`` (it would require
Docker + cluster + a populated provider lockfile) — they assert the
hand-authored composition is structurally well-formed:

- The new module dirs exist with a main.tf + variables.tf + outputs.tf.
- The local environment composition references the new modules.
- The aqp-local TerraformStackSpec hydrates from the registry / YAML.
- TerraformExecutor honours the ``prerendered_workspace_dir`` opt-out.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def test_local_cluster_module_files_exist():
    base = _repo_root() / "terraform" / "modules" / "local_cluster"
    for fname in ("main.tf", "variables.tf", "outputs.tf"):
        assert (base / fname).is_file(), f"missing {fname}"
    assert "k3d cluster create" in (base / "main.tf").read_text(encoding="utf-8")


def test_aqp_images_module_files_exist():
    base = _repo_root() / "terraform" / "modules" / "aqp_images"
    for fname in ("main.tf", "variables.tf", "outputs.tf"):
        assert (base / fname).is_file()
    text = (base / "main.tf").read_text(encoding="utf-8")
    # Sanity: each canonical service (api / worker / frontend) is referenced.
    assert "aqp-api" in text or "aqp-${each.key}" in text
    assert "frontend" in text


def test_aqp_workloads_module_files_exist():
    base = _repo_root() / "terraform" / "modules" / "aqp_workloads"
    for fname in ("main.tf", "variables.tf", "outputs.tf"):
        assert (base / fname).is_file()
    text = (base / "main.tf").read_text(encoding="utf-8")
    # The composition declares Deployments + StatefulSets for the
    # canonical services.
    for needle in (
        "kubernetes_stateful_set",
        "kubernetes_deployment",
        "kubernetes_service",
        "kubernetes_ingress_v1",
    ):
        assert needle in text, f"expected {needle} in aqp_workloads main.tf"


def test_local_environment_wires_new_modules():
    main = _repo_root() / "terraform" / "environments" / "local" / "main.tf"
    text = main.read_text(encoding="utf-8")
    assert 'module "local_cluster"' in text
    assert 'module "aqp_images"' in text
    assert 'module "aqp_workloads"' in text


def test_local_environment_outputs_endpoints():
    outputs = _repo_root() / "terraform" / "environments" / "local" / "outputs.tf"
    text = outputs.read_text(encoding="utf-8")
    for needle in ("api_url", "frontend_url", "namespace", "endpoints"):
        assert needle in text, f"expected {needle} in local/outputs.tf"


def test_root_main_tf_references_local_modules():
    """The root composition exposes the new modules on cloud_provider=local."""
    root = _repo_root() / "terraform" / "main.tf"
    text = root.read_text(encoding="utf-8")
    assert 'module "local_cluster"' in text
    assert 'module "aqp_images"' in text
    assert 'module "aqp_workloads"' in text


def test_aqp_local_spec_loads_from_registry():
    """The canonical aqp-local YAML auto-registers when the registry scans configs/."""
    from aqp.terraform.registry import (
        get_terraform_spec,
        reload_yaml_dir,
    )

    yaml_dir = _repo_root() / "configs" / "terraform"
    if not yaml_dir.exists():
        pytest.skip("aqp_platform/configs/terraform/ not present")
    reload_yaml_dir(yaml_dir)
    spec = get_terraform_spec("aqp-local")
    assert spec.cloud_provider == "local"
    assert spec.environment == "local"
    assert spec.module_kind == "composite"
    # Hash is deterministic across reloads.
    assert spec.snapshot_hash() == get_terraform_spec("aqp-local").snapshot_hash()


def test_terraform_executor_honors_prerendered_workspace_dir(tmp_path):
    """The executor skips render_spec + uses the override path."""
    from aqp.terraform.runner import TerraformExecutor
    from aqp.terraform.spec import TerraformStackSpec

    spec = TerraformStackSpec(
        name="aqp-local",
        slug="aqp-local",
        module_kind="composite",
        environment="local",
        cloud_provider="local",
    )

    # Touch a fake workspace so prepare() doesn't raise.
    (tmp_path / "main.tf").write_text("# placeholder", encoding="utf-8")

    executor = TerraformExecutor(
        workspace_slug="aqp-local",
        spec=spec,
        prerendered_workspace_dir=str(tmp_path),
    )

    wd = executor.prepare()
    assert wd == tmp_path
    # Calling prepare again must not clobber the supplied main.tf.
    assert (tmp_path / "main.tf").read_text(encoding="utf-8") == "# placeholder"
