"""Build a :class:`TerraformStackSpec` for one tenant namespace bundle.

Per the AGENTS rule 42 footnote, this Python-side helper replaces the
deprecated CDKTF path (HashiCorp deprecated CDKTF on 2025-12-10). It
renders the per-tenant bundle through the Jinja2 templates under
:file:`templates/` and returns a :class:`TerraformStackSpec` ready to
hand to :meth:`TerraformRuntime.execute`.

The bundle creates four resource groups per tenant:

1. ``kubernetes_namespace`` — ``tenant-<tenant_id>`` (prefix from
   :attr:`ControlPlaneSettings.tenant_namespace_prefix`).
2. ``aws_iam_role`` — tenant-scoped IRSA role with a least-privilege
   policy mounting only the secrets + KB segments the tenant owns.
3. ``aws_secretsmanager_secret`` — empty secret container under
   ``aqp/<environment>/tenants/<tenant_id>/...`` so the operator can
   ``put-secret-value`` later without a re-apply.
4. ``cognito_user_pool_client`` — per-tenant app client bound to the
   shared Cognito User Pool (the ALB OIDC integration filters by
   ``client_id`` to enforce isolation).

The bundle does NOT create per-tenant VPCs / RDS / EKS clusters —
those are shared cluster-wide and isolated at the application layer
(RLS in Postgres, namespace + NetworkPolicy in K8s, OIDC client_id
in the ALB integration). See
:file:`aqp_docs/docs/concepts/identity/management-engine.md` for the
tenancy strategy trade-offs.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from aqp_platform_core.models.terraform import (
    TerraformStackSpec,
    TerraformStateBackend,
)

logger = logging.getLogger(__name__)


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES_DIR),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
    )


def build_tenant_namespace_spec(
    *,
    tenant_id: str,
    environment: str,
    cluster_name: str,
    cognito_user_pool_id: str,
    callback_urls: list[str],
    namespace_prefix: str = "tenant",
    secret_arn_prefix: str = "aqp",
    state_backend: TerraformStateBackend = TerraformStateBackend.LOCAL,
    state_backend_config: dict[str, str] | None = None,
    extra_variables: dict[str, Any] | None = None,
) -> TerraformStackSpec:
    """Render the bundle and wrap it in a :class:`TerraformStackSpec`.

    The returned spec carries:

    - ``stack_name = "aqp-tenant-<tenant_id>"``
    - ``workspace_id = "<environment>-<tenant_id>"``
    - ``hcl_modules`` populated with ``main.tf`` + ``modules.tf``
    - ``variables`` echoing the inputs so the rendered HCL can read
      them via ``var.*`` if the operator post-edits the bundle.

    The spec is frozen + hash-locked by Pydantic; re-rendering with
    identical inputs yields an identical ``spec_hash``.
    """
    env = _env()
    template_vars: dict[str, Any] = {
        "tenant_id": tenant_id,
        "environment": environment,
        "namespace": f"{namespace_prefix}-{tenant_id}",
        "cluster_name": cluster_name,
        "cognito_user_pool_id": cognito_user_pool_id,
        "callback_urls": callback_urls,
        "secret_arn_prefix": secret_arn_prefix,
    }
    if extra_variables:
        template_vars.update(extra_variables)

    main_tf = env.get_template("main.tf.j2").render(**template_vars)
    modules_tf = env.get_template("modules.tf.j2").render(**template_vars)

    return TerraformStackSpec(
        stack_name=f"aqp-tenant-{tenant_id}",
        workspace_id=f"{environment}-{tenant_id}",
        state_backend=state_backend,
        state_backend_config=dict(state_backend_config or {}),
        hcl_modules={
            "main.tf": main_tf,
            "modules.tf": modules_tf,
        },
        variables=dict(template_vars),
    )


__all__ = ["build_tenant_namespace_spec"]
