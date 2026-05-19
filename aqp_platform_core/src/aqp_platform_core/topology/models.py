"""Pydantic v2 models for AQP deployment topology.

These models live here so both ``aqp/`` and ``aqp_control_plane/``
agree on the wire format of ``configs/deployment/topology.yaml``.
The YAML loader (:func:`get_deployment_topology`) stays in
``aqp/deployment/topology.py`` because it depends on
``aqp.config.settings`` for the path lookup.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base for every topology model — forbid unknown fields."""

    model_config = ConfigDict(extra="forbid")


class TopologyDefaults(StrictModel):
    organization_slug: str = "wiley-tech"
    workspace_slug: str = "main"
    app_version: str = "latest"
    labels: dict[str, str] = Field(default_factory=dict)


class TerraformTooling(StrictModel):
    binary_setting: str = "AQP_TERRAFORM_BINARY"
    min_version: str = "1.10"
    provider_mirror_path: str = "data/terraform/plugin-cache"
    plugin_cache_path: str = "data/terraform/plugin-cache-runtime"
    cli_config_file: str = "data/terraform/terraform.tfrc"


class LocalShellTooling(StrictModel):
    command: str = "bash"
    windows_path_prepend: list[str] = Field(default_factory=list)


class Tooling(StrictModel):
    terraform: TerraformTooling = Field(default_factory=TerraformTooling)
    local_shell: LocalShellTooling = Field(default_factory=LocalShellTooling)


class ServiceDefinition(StrictModel):
    id: str
    label: str
    role: str
    workload: Literal["deployment", "statefulset", "daemonset", "job", "external"]
    app_label: str
    container: str = ""
    image_key: str = ""
    port: int | None = None
    health_path: str = ""
    storage: str = ""
    restartable: bool = False
    logs_enabled: bool = True

    def selector(self) -> str:
        return f"app={self.app_label}"

    def frontend_dict(self) -> dict[str, Any]:
        data = self.model_dump()
        data["selector"] = self.selector()
        return data


class TerraformTarget(StrictModel):
    stack_slug: str
    spec_path: str
    environment_dir: str
    tfvars_path: str = ""
    backend_state_path: str = ""


class ClusterDefinition(StrictModel):
    name: str
    kubeconfig_path: str = ""
    kube_context: str = ""
    k3d_image: str = ""
    registry_name: str = ""
    registry_port: int | None = None
    registry_host: str = ""
    registry_localhost: str = ""
    lb_http_port: int | None = None
    lb_https_port: int | None = None
    ingress_class: str = ""
    ingress_host: str = ""


class ImageDefinition(StrictModel):
    registry: str = ""
    app_version: str = "latest"
    build_locally: bool = False
    services: dict[str, str] = Field(default_factory=dict)


class AuthDefinition(StrictModel):
    provider: str = "local"
    required: bool = False
    oidc_issuer: str = ""
    audience: str = ""
    client_id: str = ""
    scim_enabled: bool = False
    secret_refs: dict[str, str] = Field(default_factory=dict)


class DeploymentTarget(StrictModel):
    id: str
    label: str
    kind: str
    environment: str
    cloud_provider: str
    namespace: str
    adapter_preference: list[str] = Field(default_factory=list)
    terraform: TerraformTarget
    cluster: ClusterDefinition
    endpoints: dict[str, str] = Field(default_factory=dict)
    images: ImageDefinition = Field(default_factory=ImageDefinition)
    auth: AuthDefinition = Field(default_factory=AuthDefinition)
    services: list[str] = Field(default_factory=list)

    def summary_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "namespace": self.namespace,
        }


class DeploymentTopology(StrictModel):
    version: int
    defaults: TopologyDefaults = Field(default_factory=TopologyDefaults)
    tooling: Tooling = Field(default_factory=Tooling)
    services: list[ServiceDefinition]
    targets: dict[str, DeploymentTarget]

    @model_validator(mode="after")
    def _validate_references(self) -> DeploymentTopology:
        service_ids = {service.id for service in self.services}
        for target_id, target in self.targets.items():
            if target.id != target_id:
                raise ValueError(
                    f"target key {target_id!r} does not match target id {target.id!r}"
                )
            missing = sorted(set(target.services) - service_ids)
            if missing:
                raise ValueError(
                    f"target {target_id!r} references unknown services: {missing}"
                )
        terraform = self.tooling.terraform
        if terraform.provider_mirror_path == terraform.plugin_cache_path:
            raise ValueError(
                "terraform provider mirror and plugin cache paths must differ"
            )
        return self

    @property
    def service_map(self) -> dict[str, ServiceDefinition]:
        return {service.id: service for service in self.services}

    def target(self, target_id: str) -> DeploymentTarget:
        try:
            return self.targets[target_id]
        except KeyError as exc:
            raise KeyError(f"unknown deployment target {target_id!r}") from exc

    def target_by_stack_slug(self, stack_slug: str) -> DeploymentTarget | None:
        for target in self.targets.values():
            if target.terraform.stack_slug == stack_slug:
                return target
        return None

    def services_for_target(self, target_id: str) -> list[ServiceDefinition]:
        target = self.target(target_id)
        services = self.service_map
        return [services[service_id] for service_id in target.services]


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
]
