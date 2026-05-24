from __future__ import annotations

from pathlib import Path

import pytest


def test_deployment_topology_loads_default_manifest():
    from aqp.deployment.topology import get_deployment_topology

    topology = get_deployment_topology()
    assert topology.version == 1
    assert set(topology.targets) >= {"local", "rpi"}
    assert "aqp-api" in topology.service_map


def test_topology_resolves_target_services_and_terraform_vars():
    from aqp.deployment.topology import get_deployment_topology

    topology = get_deployment_topology()
    local = topology.target("local")
    rpi = topology.target("rpi")

    assert local.namespace == "aqp-local"
    assert local.terraform.environment_path.name == "local"
    assert local.terraform_vars()["cluster_name"] == "aqp-local"
    assert local.terraform_vars()["enabled_services"]
    assert local.terraform_vars()["local_shell_interpreter"]
    assert rpi.terraform_vars()["rpi_namespace"] == "aqp"
    assert rpi.terraform_vars()["auth0_audience"] == "https://aqp/api"
    assert rpi.terraform_vars()["auth0_client_secret_secret_name"] == "auth0-client-secret"

    services = topology.services_for_target("rpi")
    assert {service.id for service in services} >= {"aqp-api", "redis", "postgres"}
    assert all(service.selector().startswith("app=") for service in services)


def test_topology_frontend_payload_excludes_secret_refs():
    from aqp.deployment.topology import get_deployment_topology

    payload = get_deployment_topology().frontend_dict()
    rpi = next(target for target in payload["targets"] if target["id"] == "rpi")
    assert rpi["namespace"] == "aqp"
    assert rpi["services"]
    assert "secret_refs" not in rpi["auth"]


def test_topology_terraform_env_overrides_are_authoritative():
    from aqp.deployment.topology import get_deployment_topology

    env = get_deployment_topology().terraform_env_overrides("local")
    assert env["TF_CLI_CONFIG_FILE"].endswith("data\\terraform\\terraform.tfrc") or env[
        "TF_CLI_CONFIG_FILE"
    ].endswith("data/terraform/terraform.tfrc")
    assert env["TF_PLUGIN_CACHE_DIR"] != env["TF_CLI_CONFIG_FILE"]
    assert env["TF_VAR_enabled_services"].startswith("[")
    assert "TF_VAR_local_shell_interpreter" in env


def test_topology_rejects_inline_secret_refs(tmp_path: Path):
    from aqp.deployment.topology import get_deployment_topology, reload_deployment_topology

    source = Path("aqp_platform/configs/deployment/topology.yaml")
    copied = tmp_path / "topology.yaml"
    text = source.read_text(encoding="utf-8").replace(
        "client_secret: auth0-client-secret",
        "client_secret: inline secret value",
    )
    copied.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="must be a Kubernetes secret name"):
        get_deployment_topology(str(copied))
    reload_deployment_topology()


def test_topology_path_can_load_explicit_file(tmp_path: Path):
    from aqp.deployment.topology import get_deployment_topology, reload_deployment_topology

    source = Path("aqp_platform/configs/deployment/topology.yaml")
    copied = tmp_path / "topology.yaml"
    copied.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    topology = get_deployment_topology(str(copied))
    assert topology.target("local").terraform.stack_slug == "aqp-local"
    reload_deployment_topology()
