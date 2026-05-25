"""AWS :class:`InfrastructureProvider` — EKS (delegates to K8s) + ECS Fargate.

Phase 5 ships the registration scaffold + credential-chain probe. Full
ECS ``update_service`` / SSM ``put_parameter`` impl lands in a follow-up
PR — see ``aqp_docs/docs/how-to/operations/add-new-provider.md`` for the contract.
"""
from __future__ import annotations

import logging
import os

from aqp_platform_core.providers.protocol import ProviderKind
from aqp_platform_core.providers.registry import register_provider_class

from aqp_cp.providers._cloud_stub import CloudProviderStub

logger = logging.getLogger(__name__)


@register_provider_class("aws", replace=True)
class AwsProvider(CloudProviderStub):
    """AWS provider — EKS delegate + ECS Fargate scaffold."""

    provider_kind = ProviderKind.AWS
    provider_alias = "aws"
    cloud_name = "AWS"
    follow_up_pr = "aqp-control-plane#aws-impl"
    docs_link = "aqp_docs/docs/how-to/operations/add-new-provider.md#aws"
    delegate_kubernetes_alias = (
        "kubernetes"
        if os.environ.get("AQP_CP_AWS_DELEGATE_K8S", "").lower() in ("1", "true", "yes")
        else None
    )

    def _real_health_probe(self) -> tuple[bool, dict | None, str | None]:
        """Single STS GetCallerIdentity call when boto3 is available."""
        try:
            import boto3  # type: ignore[import-not-found]
            from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-not-found]
        except ImportError:
            return False, None, "boto3 not installed"
        try:
            sts = boto3.client("sts")
            ident = sts.get_caller_identity()
            return True, {
                "account": ident.get("Account"),
                "arn": ident.get("Arn"),
                "region": os.environ.get("AWS_REGION", ""),
            }, None
        except (BotoCoreError, ClientError) as exc:
            return False, None, f"STS GetCallerIdentity failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            return False, None, str(exc)

    def _check_credentials(self) -> tuple[bool, str | None]:
        # boto3 walks the standard credential chain itself; we only do
        # a cheap "is anything in the environment" check here so the
        # health probe doesn't make a real STS call on every poll.
        if any(
            os.environ.get(key)
            for key in (
                "AWS_ACCESS_KEY_ID",
                "AWS_PROFILE",
                "AWS_ROLE_ARN",
                "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
            )
        ):
            return True, None
        return False, (
            "AWS credentials not found (set AWS_ACCESS_KEY_ID / AWS_PROFILE / "
            "AWS_ROLE_ARN or run inside an EC2/EKS pod with an attached role)."
        )

    def _describe_target(self) -> dict:
        return {
            "region": os.environ.get("AWS_REGION", ""),
            "supports": ["EKS (via kubernetes provider)", "ECS Fargate (pending impl)"],
        }


__all__ = ["AwsProvider"]
