"""Jinja2-rendered tenant-namespace bundle (rule 42 footnote).

When the admin BFF promotes an :class:`EntraTenantLink` from
``pending`` to ``active`` (rule 44), the management engine asks the
CP-side :class:`TerraformRuntime` to provision the per-tenant
namespace + IAM role + secrets binding via this builder.

The bundle is deliberately small — it composes existing reusable
``aws_iam_role`` + ``aws_secretsmanager_secret`` + ``kubernetes_namespace``
resources rather than spinning up new shared infra. The shared
landing-zone services (VPC, EKS cluster, Cognito User Pool, MSK)
live in :file:`infrastructure/modules/` and are pre-existing
prerequisites.
"""

from aqp_cp.terraform.builders.manifests.tenant_namespace import (
    build_tenant_namespace_spec,
)

__all__ = ["build_tenant_namespace_spec"]
