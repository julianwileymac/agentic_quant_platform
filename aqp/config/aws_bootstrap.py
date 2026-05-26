"""Hydrate :class:`Settings` from AWS SSM Parameter Store on application boot.

Phase J of the AWS hybrid rollout. Every Terraform module that lands a
managed-service handle publishes it to ``/aqp/${env}/<key>`` in SSM
(see the ``ssm_parameters`` output convention on every
``infrastructure/modules/*`` and ``aqp_platform/terraform/environments/*``).
This helper reads that namespace once at boot and applies the values
to the active :class:`Settings` instance so the rest of the codebase
keeps reading ``settings.<knob>`` exactly as it does locally.

The helper is **soft-optional**:

- When ``AQP_DEPLOY_TARGET`` is unset or any value other than ``aws``,
  the bootstrap is a no-op (local-first / Docker / EKS-only operators
  see no behavior change).
- When ``boto3`` is missing it logs a warning + returns ``{}``.
- When SSM is unreachable it logs each failed parameter at WARNING +
  continues with whatever loaded successfully.

Per the management-engine credential-safety rule, the helper NEVER
logs the resolved values — only the names. Secret-flavoured
parameters (any name containing ``secret``, ``password``, ``token``,
``key``, ``credential``) are pulled WithDecryption=True but never
printed.

Call from the FastAPI lifespan + the Celery worker bootstrap:

.. code-block:: python

    from aqp.config.aws_bootstrap import hydrate_settings_from_ssm

    @asynccontextmanager
    async def lifespan(app):
        hydrate_settings_from_ssm()
        yield
"""
from __future__ import annotations

import logging
import os
from typing import Any, Mapping

from aqp.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default mapping — SSM key suffix -> Settings attr name.
# ---------------------------------------------------------------------------

# Add a new entry to this map when a new Terraform module starts
# publishing a handle the application reads at boot. The mapping is
# environment-agnostic — every key lives at ``/aqp/${env}/<suffix>``.
# Empty Settings attrs (``""``) tell the bootstrap to read the SSM
# value into the process env vars instead — useful for libraries that
# don't go through :class:`Settings`.
DEFAULT_SSM_MAP: Mapping[str, str] = {
    # Network handles
    "vpc_id": "aws_vpc_id",
    "ecr_registry": "aws_ecr_registry",
    "ecs_cluster_name": "aws_ecs_cluster_name",
    # Storage handles
    "rds_endpoint": "aws_rds_endpoint",
    "redis_primary_endpoint": "aws_redis_primary_endpoint",
    # Identity handles
    "cognito_user_pool_id": "cognito_user_pool_id",
    "cognito_user_pool_endpoint": "auth_oidc_issuer",
    "cognito_shared_client_id": "auth_oidc_audience",
    # Edge handles
    "alb_dns_name": "aws_alb_dns_name",
    "cloudfront_domain": "aws_cloudfront_domain",
    # Bedrock + AgentCore handles
    "agentcore_runtime_arn": "agentcore_runtime_arn",
    "agentcore_gateway_arn": "agentcore_gateway_arn",
    "agentcore_memory_id": "agentcore_memory_id",
    "agentcore_gateway_tool_config_uri": "agentcore_gateway_tool_config_uri",
    "kb_collection_arn": "kb_collection_arn",
    "kb_knowledge_base_id": "kb_knowledge_base_id",
    "kb_source_bucket": "kb_source_bucket",
    # Orchestration handles
    "nightly_sfn_arn": "aws_nightly_sfn_arn",
    "kb_sync_lambda_arn": "aws_kb_sync_lambda_arn",
}

_SECRET_LIKE_NAME_TOKENS: tuple[str, ...] = (
    "secret",
    "password",
    "token",
    "key",
    "credential",
)


def _is_secret_like(name: str) -> bool:
    lowered = (name or "").lower()
    return any(tok in lowered for tok in _SECRET_LIKE_NAME_TOKENS)


def _resolve_environment() -> str:
    env = os.environ.get("AQP_ENVIRONMENT", "").strip()
    if env:
        return env
    return str(getattr(settings, "environment", "") or "").strip() or "dev"


def _resolve_target() -> str:
    raw = os.environ.get("AQP_DEPLOY_TARGET", "").strip()
    if raw:
        return raw.lower()
    return str(getattr(settings, "aqp_deploy_target", "") or "").strip().lower()


def _safe_set_setting(attr: str, value: str) -> bool:
    """Apply ``value`` to ``settings.<attr>`` when the field accepts it.

    Returns ``True`` when the assignment succeeded. Skips silently
    when the attr doesn't exist on the active :class:`Settings`
    instance (older deployment + newer Terraform — graceful).
    """
    if not attr or not hasattr(settings, attr):
        return False
    try:
        setattr(settings, attr, value)
        return True
    except Exception:  # noqa: BLE001
        logger.debug("settings.%s rejected SSM value", attr, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def hydrate_settings_from_ssm(
    *,
    environment: str | None = None,
    extra_mappings: Mapping[str, str] | None = None,
    deploy_target: str | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Read ``/aqp/${env}/*`` into the active :class:`Settings` instance.

    Returns the mapping of ``Settings`` attribute -> the SSM parameter
    name we sourced it from, so the caller can audit-log what landed
    (the values themselves are never logged).

    Arguments:

    - ``environment`` — override the auto-detected env slug.
    - ``extra_mappings`` — additional SSM-suffix -> Settings-attr entries.
    - ``deploy_target`` — when set to anything other than ``aws``,
      the function returns ``{}`` without making any SSM calls.
    - ``force`` — bypass the deploy-target gate (used by smoke tests).
    """
    target = (deploy_target or _resolve_target()).lower()
    if not force and target != "aws":
        logger.debug(
            "AWS SSM bootstrap skipped: AQP_DEPLOY_TARGET=%r (need 'aws')",
            target,
        )
        return {}

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        logger.warning(
            "AWS SSM bootstrap skipped: boto3 not installed (pip install boto3)"
        )
        return {}

    env = environment or _resolve_environment()
    region = (
        os.environ.get("AWS_REGION")
        or str(getattr(settings, "aws_region", "") or "")
        or "us-east-1"
    )
    mapping: dict[str, str] = dict(DEFAULT_SSM_MAP)
    if extra_mappings:
        mapping.update(extra_mappings)

    ssm = boto3.client("ssm", region_name=region)
    applied: dict[str, str] = {}
    for suffix, attr in mapping.items():
        name = f"/aqp/{env}/{suffix}"
        try:
            response = ssm.get_parameter(
                Name=name,
                WithDecryption=True,
            )
        except (BotoCoreError, ClientError) as exc:
            code = getattr(getattr(exc, "response", None) or {}, "get", lambda *_: {})(
                "Error", {}
            ).get("Code") or ""
            if code == "ParameterNotFound":
                logger.debug("SSM bootstrap: %s not set; skipping", name)
            else:
                logger.warning(
                    "SSM bootstrap: get_parameter(%s) failed code=%s; skipping",
                    name,
                    code or type(exc).__name__,
                )
            continue
        param = response.get("Parameter") or {}
        value = str(param.get("Value") or "")
        if not value:
            continue

        if attr:
            if _safe_set_setting(attr, value):
                applied[attr] = name
                if _is_secret_like(name):
                    logger.info(
                        "ssm_bootstrap applied SecureString -> settings.%s (value redacted)",
                        attr,
                    )
                else:
                    logger.info("ssm_bootstrap applied -> settings.%s", attr)
        else:
            # Empty attr -> stuff into env vars (for libs that read
            # straight from os.environ). Use the suffix uppercased
            # with the AQP_ prefix.
            env_name = "AQP_" + suffix.upper()
            os.environ.setdefault(env_name, value)
            applied[env_name] = name
            if not _is_secret_like(name):
                logger.info("ssm_bootstrap applied -> env %s", env_name)

    logger.info(
        "AWS SSM bootstrap completed env=%s region=%s applied=%d/%d",
        env,
        region,
        len(applied),
        len(mapping),
    )
    return applied


__all__ = [
    "DEFAULT_SSM_MAP",
    "hydrate_settings_from_ssm",
]
