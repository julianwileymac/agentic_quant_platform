"""Typed deployment topology loaded from ``configs/deployment/topology.yaml``."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aqp.config import settings

_K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (_repo_root() / path).resolve()


class StrictModel(BaseModel):
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

    @property
    def environment_path(self) -> Path:
        return _resolve_repo_path(self.environment_dir)

    @property
    def spec_file(self) -> Path:
        return _resolve_repo_path(self.spec_path)


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

    def terraform_vars(self) -> dict[str, Any]:
        """Return Terraform variable values derived from the topology target."""
        if self.id == "local":
            return {
                "environment": self.environment,
                "namespace": self.namespace,
                "cluster_name": self.cluster.name,
                "app_version": self.images.app_version,
                "registry_port": self.cluster.registry_port,
                "lb_http_port": self.cluster.lb_http_port,
                "lb_https_port": self.cluster.lb_https_port,
                "local_shell_interpreter": self._local_shell_interpreter(),
                "enabled_services": self.services,
            }
        if self.id == "rpi":
            return {
                "rpi_kubeconfig_path": self.cluster.kubeconfig_path,
                "rpi_kube_context": self.cluster.kube_context,
                "rpi_namespace": self.namespace,
                "app_version": self.images.app_version,
                "rpi_image_registry": self.images.registry,
                "rpi_ingress_host": self.cluster.ingress_host,
                "auth0_domain": self.auth.oidc_issuer.removeprefix("https://").removesuffix("/"),
                "auth0_audience": self.auth.audience,
                "auth0_client_id": self.auth.client_id,
                "auth_scim_m2m_audience": self.auth.audience,
                "enabled_services": self.services,
                "auth0_client_secret_secret_name": self.auth.secret_refs.get(
                    "client_secret", ""
                ),
                "auth_scim_bearer_token_hash_secret_name": self.auth.secret_refs.get(
                    "scim_bearer_token_hash", ""
                ),
            }
        return {}

    def terraform_var_env(self) -> dict[str, str]:
        """Return ``TF_VAR_*`` environment overrides for Terraform."""
        env: dict[str, str] = {}
        for key, value in self.terraform_vars().items():
            if value is None:
                continue
            if isinstance(value, bool):
                encoded = "true" if value else "false"
            elif isinstance(value, int | float):
                encoded = str(value)
            elif isinstance(value, list | dict):
                encoded = json.dumps(value)
            else:
                encoded = str(value)
            env[f"TF_VAR_{key}"] = encoded
        return env

    def _local_shell_interpreter(self) -> str:
        """Prefer Git Bash on Windows when topology declares a Bash prepend."""
        if os.name != "nt":
            return "bash"
        bash_dir = next(
            (
                Path(path)
                for path in get_deployment_topology().tooling.local_shell.windows_path_prepend
                if path
            ),
            None,
        )
        if bash_dir is None:
            return "bash"
        return str((bash_dir / "bash.exe").as_posix())


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
            if target.auth.secret_refs:
                # Keys describe secret slots; values must stay Kubernetes/secret-store
                # references. The actual credential material belongs in CredentialResolver.
                for key, value in target.auth.secret_refs.items():
                    if not value or not _K8S_NAME_RE.match(value):
                        raise ValueError(
                            f"target {target_id!r} secret ref {key!r} must be a Kubernetes secret name"
                        )
                    if any(marker in value.lower() for marker in (":", "/", "=", " ")):
                        raise ValueError(
                            f"target {target_id!r} secret ref {key!r} appears to contain inline secret material"
                        )
                if target.auth.provider == "local":
                    raise ValueError(f"local target {target_id!r} must not declare secret refs")
        terraform = self.tooling.terraform
        if terraform.provider_mirror_path == terraform.plugin_cache_path:
            raise ValueError("terraform provider mirror and plugin cache paths must differ")
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

    def terraform_env_overrides(self, target_id: str) -> dict[str, str]:
        """Return topology-derived env overrides for a Terraform target."""
        target = self.target(target_id)
        terraform = self.tooling.terraform
        env = target.terraform_var_env()
        mirror_path = _resolve_repo_path(terraform.provider_mirror_path)
        plugin_cache_path = _resolve_repo_path(terraform.plugin_cache_path)
        env["TF_PLUGIN_CACHE_DIR"] = str(plugin_cache_path)
        cli_config = _resolve_repo_path(terraform.cli_config_file)
        if not cli_config.exists():
            cli_config.parent.mkdir(parents=True, exist_ok=True)
            mirror_path.mkdir(parents=True, exist_ok=True)
            cli_config.write_text(
                "\n".join(
                    [
                        "provider_installation {",
                        "  filesystem_mirror {",
                        f'    path    = "{mirror_path.as_posix()}"',
                        '    include = ["registry.terraform.io/*/*"]',
                        "  }",
                        "  direct {",
                        '    exclude = ["registry.terraform.io/*/*"]',
                        "  }",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        env["TF_CLI_CONFIG_FILE"] = str(cli_config)
        path_prepend = [
            str(Path(path))
            for path in self.tooling.local_shell.windows_path_prepend
            if path
        ]
        if path_prepend:
            env["PATH"] = os.pathsep.join([*path_prepend, os.environ.get("PATH", "")])
        return env

    def services_for_target(self, target_id: str) -> list[ServiceDefinition]:
        target = self.target(target_id)
        services = self.service_map
        return [services[service_id] for service_id in target.services]

    def frontend_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "targets": [
                self.target_frontend_dict(target_id)
                for target_id in sorted(self.targets.keys())
            ],
            "tooling": self.tooling.model_dump(),
        }

    def target_frontend_dict(self, target_id: str) -> dict[str, Any]:
        target = self.target(target_id)
        return {
            **target.summary_dict(),
            "environment": target.environment,
            "cloud_provider": target.cloud_provider,
            "endpoints": target.endpoints,
            "auth": target.auth.model_dump(exclude={"secret_refs"}),
            "terraform": {
                "stack_slug": target.terraform.stack_slug,
                "environment_dir": target.terraform.environment_dir,
            },
            "services": [
                service.frontend_dict()
                for service in self.services_for_target(target_id)
            ],
        }


def topology_path(path: str | Path | None = None) -> Path:
    configured = path or settings.deployment_topology_path
    return _resolve_repo_path(configured)


@lru_cache(maxsize=1)
def get_deployment_topology(path: str | Path | None = None) -> DeploymentTopology:
    resolved = topology_path(path)
    with resolved.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return DeploymentTopology.model_validate(raw)


def reload_deployment_topology(path: str | Path | None = None) -> DeploymentTopology:
    get_deployment_topology.cache_clear()
    return get_deployment_topology(path)


def get_target(target_id: str) -> DeploymentTarget:
    return get_deployment_topology().target(target_id)


def list_targets() -> list[DeploymentTarget]:
    topology = get_deployment_topology()
    return [topology.targets[key] for key in sorted(topology.targets.keys())]


__all__ = [
    "DeploymentTarget",
    "DeploymentTopology",
    "ServiceDefinition",
    "get_deployment_topology",
    "get_target",
    "list_targets",
    "reload_deployment_topology",
    "topology_path",
]
