"""Config / secret reference wire-format models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SecretRef(BaseModel):
    """Reference to a secret managed outside the control plane.

    The control plane never stores the secret value — only the
    reference. Resolution happens in the provider via the active
    :class:`SecretStore` chain.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Secret name as known to the provider.")
    backend: str = Field(
        description=(
            "Secret backend kind: 'k8s_secret', 'aws_ssm', "
            "'aws_secretsmanager', 'azure_keyvault', 'gcp_secretmanager', "
            "'docker_env'."
        )
    )
    keys: list[str] = Field(
        default_factory=list,
        description="Specific keys within the secret to expose; empty = all.",
    )


class ConfigMapPatch(BaseModel):
    """Partial update to a service's configuration.

    Applied via :meth:`InfrastructureProvider.apply_config`. The
    provider re-creates the underlying ConfigMap (K8s) / Parameter
    Store entry (AWS SSM) / App Configuration (Azure) / Secret Manager
    secret (GCP) / env file (Compose) and triggers a rolling restart
    if necessary.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    values: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Non-secret key/value pairs. Secrets must be added via "
            "SecretRef + a separate ServiceConfig.secret_refs entry."
        ),
    )
    delete_keys: list[str] = Field(
        default_factory=list,
        description="Keys to remove from the config map.",
    )
    secret_refs: list[SecretRef] = Field(
        default_factory=list,
        description="Secret references to attach.",
    )
    trigger_restart: bool = Field(
        default=True,
        description=(
            "When True, the provider rolls the deployment so the new "
            "config takes effect immediately. When False, the change "
            "is applied lazily on the next deploy."
        ),
    )


class ServiceConfig(BaseModel):
    """Read-only view of a service's current configuration.

    Returned by ``GET /manage/config/{service_id}``. Secret values are
    redacted — only the reference is shown.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    values: dict[str, str] = Field(default_factory=dict)
    secret_refs: list[SecretRef] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


__all__ = ["ConfigMapPatch", "SecretRef", "ServiceConfig"]
