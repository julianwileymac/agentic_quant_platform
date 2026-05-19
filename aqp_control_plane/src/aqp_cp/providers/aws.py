"""AWS :class:`InfrastructureProvider` — EKS (delegates to K8s) + ECS Fargate.

Phase 5 ships the registration scaffold + credential-chain probe. Full
ECS ``update_service`` / SSM ``put_parameter`` impl lands in a follow-up
PR — see ``docs/operations/add-new-provider.md`` for the contract.
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
    docs_link = "docs/operations/add-new-provider.md#aws"

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
