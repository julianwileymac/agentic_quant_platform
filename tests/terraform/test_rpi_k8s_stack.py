"""Structural tests for the rpi_kubernetes Terraform target."""
from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def test_rpi_environment_files_exist():
    base = _repo_root() / "terraform" / "environments" / "rpi"
    for name in ("main.tf", "variables.tf", "outputs.tf", "backend.tf", "terraform.tfvars"):
        assert (base / name).is_file(), f"missing {name}"


def test_rpi_environment_uses_kubernetes_provider_and_aqp_workloads():
    text = (_repo_root() / "terraform" / "environments" / "rpi" / "main.tf").read_text(encoding="utf-8")
    assert 'provider "kubernetes"' in text
    assert 'module "target"' in text
    assert 'module "aqp_workloads"' in text
    assert re.search(r'cloud_provider\s*=\s*"rpi_cluster"', text)


def test_auth0_identity_module_exists():
    base = _repo_root() / "terraform" / "modules" / "auth0_identity"
    assert (base / "main.tf").is_file()
    text = (base / "main.tf").read_text(encoding="utf-8")
    assert 'resource "auth0_client" "spa"' in text
    assert 'resource "auth0_resource_server" "api"' in text
    assert 'resource "auth0_action" "post_login_claims"' in text


def test_rpi_terraform_spec_loads():
    from aqp.terraform.registry import get_terraform_spec, reload_yaml_dir

    reload_yaml_dir(_repo_root() / "configs" / "terraform")
    spec = get_terraform_spec("aqp-rpi-kubernetes")
    assert spec.cloud_provider == "rpi_cluster"
    assert spec.module_kind == "composite"


def test_auth0_terraform_spec_loads():
    from aqp.terraform.registry import get_terraform_spec, reload_yaml_dir

    reload_yaml_dir(_repo_root() / "configs" / "terraform")
    spec = get_terraform_spec("aqp-auth0-identity")
    assert spec.cloud_provider == "auth0"
    assert spec.module_kind == "composite"
