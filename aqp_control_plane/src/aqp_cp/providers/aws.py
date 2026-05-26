"""AWS :class:`InfrastructureProvider` — EKS delegate + ECS Fargate mutating ops.

Phase B of the CP control-plane maturation lights up the workload-runtime
surface (AGENTS rule 45) against Amazon ECS Fargate. Read paths
(``health``, ``list_deployments``, ``status``) keep delegating to the
registered ``kubernetes`` provider when ``AQP_CP_AWS_DELEGATE_K8S=true``
so the operator surface keeps working for EKS clusters; the new
mutating paths target ECS Fargate so the AgentCore reverse proxy + the
``aqp-admin`` BFF can be driven through the canonical
:class:`WorkloadRuntime` audit lifecycle.

ECS Fargate mapping:

| ABC method        | boto3 call                                          |
|-------------------|-----------------------------------------------------|
| ``start``         | ``ecs.create_service`` (idempotent: switches to     |
|                   | ``update_service`` when the service already exists) |
| ``stop``          | ``ecs.update_service(desiredCount=0)``              |
| ``scale``         | ``ecs.update_service(desiredCount=N)``              |
| ``restart``       | ``ecs.update_service(forceNewDeployment=True)``     |
| ``status``        | ``ecs.describe_services``                            |
| ``list_deployments``| ``ecs.list_services`` + ``describe_services``     |
| ``exec``          | ``ecs.execute_command`` (SSM Session Manager —      |
|                   | gated by ``AQP_AWS_ECS_EXEC_ENABLED=true``)         |
| ``tail_logs``     | ``logs.get_log_events`` (CloudWatch Logs)           |
| ``rotate_secret`` | ``secretsmanager.rotate_secret`` (prefix-guarded)   |
| ``apply_config``  | ``ssm.put_parameter`` (denylist-guarded)            |

Service ID may be either a short name or a full ARN; namespace is the
ECS cluster name (defaults to ``aqp-<environment>`` per
:attr:`Settings.aws_eks_cluster_name` fallback). Per the management-engine
credential-safety rule, no secret value (kubeconfig, Cf-Access JWT,
broker secret) is ever logged.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from aqp_platform_core.models.config import ConfigMapPatch
from aqp_platform_core.models.deployment import (
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
)
from aqp_platform_core.models.workloads import (
    SecretRotationResult,
    WorkloadExecResult,
    WorkloadLogEvent,
)
from aqp_platform_core.providers.protocol import (
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    ProviderKind,
)
from aqp_platform_core.providers.registry import register_provider_class

from aqp_cp.providers._cloud_stub import CloudProviderStub

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — denylist patterns for apply_config + secret rotation guard
# ---------------------------------------------------------------------------

# Keys that must never be written through ``apply_config`` — the operator
# is trying to push a secret through the non-secret SSM Parameter Store
# path. Mirrors :func:`WorkloadRuntime.redact_payload`'s denylist so
# `/manage/config/...` and `/manage/workloads/{id}/apply-config` agree
# on what's "secret".
_SECRET_LIKE_KEY_TOKENS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "key",
    "credential",
    "private",
    "authorization",
    "kubeconfig",
    "client_secret",
    "api_token",
    "api_key",
    "jwt",
    "refresh_token",
    "access_token",
)

# Pattern used by rotate_secret — only secrets under aqp/<env>/... or
# the configured prefix are rotatable from this provider. Prevents an
# operator from rotating an arbitrary secret in the account (Stripe,
# Snowflake, anything not owned by AQP) through the management API.
_ROTATABLE_SECRET_PREFIX_ENV: str = "AQP_AWS_ROTATABLE_SECRET_PREFIX"
_DEFAULT_ROTATABLE_PREFIX: str = "aqp/"


# ECS service ARN parser (returns short name when given a full ARN).
_ECS_SERVICE_ARN_RE = re.compile(
    r"^arn:aws:ecs:[^:]+:[0-9]+:service/(?P<cluster>[^/]+)/(?P<name>.+)$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_secret_like(key: str) -> bool:
    """True when the key name implies it carries secret material."""
    lowered = key.lower()
    return any(token in lowered for token in _SECRET_LIKE_KEY_TOKENS)


def _split_service_ref(service_id: str, namespace: str | None) -> tuple[str, str]:
    """Resolve (cluster, service_name) from either a short name or an ARN."""
    match = _ECS_SERVICE_ARN_RE.match(service_id)
    if match:
        return match.group("cluster"), match.group("name")
    return namespace or "default", service_id


def _phase_from_ecs(status_str: str | None) -> DeploymentLifecyclePhase:
    """Map ECS service status -> normalised DeploymentLifecyclePhase."""
    s = (status_str or "").upper()
    if s in ("ACTIVE",):
        return DeploymentLifecyclePhase.RUNNING
    if s in ("DRAINING",):
        return DeploymentLifecyclePhase.STOPPING
    if s in ("INACTIVE",):
        return DeploymentLifecyclePhase.STOPPED
    return DeploymentLifecyclePhase.UNKNOWN


def _ecs_service_to_status(
    service_payload: dict[str, Any],
    *,
    provider_alias: str,
) -> DeploymentStatus:
    """Translate a boto3 ECS service dict to :class:`DeploymentStatus`."""
    deployments = service_payload.get("deployments") or []
    image = None
    if deployments:
        # ECS doesn't surface a single image on the service; fall back
        # to the first task definition arn so the operator sees what's
        # deployed.
        image = deployments[0].get("taskDefinition")
    raw = dict(service_payload)
    # Trim noisy fields that bloat the wire payload.
    for noisy in ("events", "deployments", "loadBalancers", "serviceRegistries"):
        raw.pop(noisy, None)
    return DeploymentStatus(
        service_id=service_payload.get("serviceName") or "",
        provider=provider_alias,
        phase=_phase_from_ecs(service_payload.get("status")),
        replicas_desired=int(service_payload.get("desiredCount") or 0),
        replicas_ready=int(service_payload.get("runningCount") or 0),
        image=image,
        namespace=service_payload.get("clusterArn"),
        raw=raw,
    )


def _bedrock_log_group(service_id: str) -> str:
    return f"/aws/ecs/{service_id}"


# ---------------------------------------------------------------------------
# AwsProvider — full ECS Fargate impl + EKS read delegation
# ---------------------------------------------------------------------------


@register_provider_class("aws", replace=True)
class AwsProvider(CloudProviderStub):
    """AWS provider — EKS delegate + ECS Fargate workload runtime ops."""

    provider_kind = ProviderKind.AWS
    provider_alias = "aws"
    cloud_name = "AWS"
    follow_up_pr = "aqp-control-plane#aws-impl"
    docs_link = "aqp_docs/docs/how-to/operations/aws-deploy.md"
    delegate_kubernetes_alias = (
        "kubernetes"
        if os.environ.get("AQP_CP_AWS_DELEGATE_K8S", "").lower() in ("1", "true", "yes")
        else None
    )

    # --- Credential / health probes (unchanged from Phase 5) -----------

    def _real_health_probe(self) -> tuple[bool, dict | None, str | None]:
        """Single STS GetCallerIdentity call when boto3 is available."""
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
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
            "supports": [
                "EKS (via kubernetes provider)",
                "ECS Fargate (start/stop/scale/restart/exec/logs/rotate_secret/apply_config)",
            ],
        }

    # --- boto3 client helpers -----------------------------------------

    def _client(self, service: str):  # type: ignore[no-untyped-def]
        """Lazy-construct a boto3 client; raise unavailable when boto3 missing."""
        try:
            import boto3
        except ImportError as exc:
            raise InfrastructureProviderUnavailable(
                "boto3 not installed in the CP image — pip install aqp-control-plane[aws]",
                provider=self.provider_alias,
                details={"missing": "boto3"},
            ) from exc
        region = os.environ.get("AWS_REGION") or None
        return boto3.client(service, region_name=region)

    # --- start / stop / scale / restart ------------------------------

    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        """Create or update the ECS service for ``spec``.

        Idempotent: when the service exists we issue ``update_service``
        with the new desired count; otherwise ``create_service`` is
        called. The task-definition ARN is read from
        ``spec.metadata['task_definition']`` — operators register task
        defs through the standard ``aws ecs register-task-definition``
        flow (or the Terraform ``aws_ecs_task_definition`` resource
        rendered by the codegen tree).
        """
        return await asyncio.to_thread(self._start_sync, spec)

    def _start_sync(self, spec: DeploymentSpec) -> DeploymentStatus:
        ecs = self._client("ecs")
        cluster, service_name = _split_service_ref(spec.service_id, spec.namespace)
        task_def = spec.metadata.get("task_definition")
        if not task_def:
            raise InfrastructureProviderError(
                "spec.metadata['task_definition'] is required for AwsProvider.start",
                provider=self.provider_alias,
                code="invalid_spec",
                details={"service_id": spec.service_id},
            )

        # describe first to decide create vs update
        try:
            described = ecs.describe_services(cluster=cluster, services=[service_name])
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"ECS describe_services failed: {exc}",
                provider=self.provider_alias,
                code="ecs_error",
            ) from exc

        services = described.get("services") or []
        active = [s for s in services if s.get("status") == "ACTIVE"]
        if active:
            updated = ecs.update_service(
                cluster=cluster,
                service=service_name,
                taskDefinition=task_def,
                desiredCount=int(spec.replicas),
            )
            return _ecs_service_to_status(
                updated.get("service") or {}, provider_alias=self.provider_alias
            )
        created = ecs.create_service(
            cluster=cluster,
            serviceName=service_name,
            taskDefinition=task_def,
            desiredCount=int(spec.replicas),
            launchType=spec.metadata.get("launch_type", "FARGATE"),
            networkConfiguration=spec.metadata.get("network_configuration") or {},
            enableExecuteCommand=bool(spec.metadata.get("enable_execute_command", False)),
            tags=[
                {"key": k, "value": v}
                for k, v in (spec.labels or {}).items()
            ],
        )
        return _ecs_service_to_status(
            created.get("service") or {}, provider_alias=self.provider_alias
        )

    async def stop(self, service_id: str, *, namespace: str | None = None) -> DeploymentStatus:
        return await asyncio.to_thread(self._scale_sync, service_id, 0, namespace)

    async def scale(
        self,
        service_id: str,
        replicas: int,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        if replicas < 0:
            raise InfrastructureProviderError(
                "replicas must be >= 0",
                provider=self.provider_alias,
                code="invalid_replicas",
            )
        return await asyncio.to_thread(self._scale_sync, service_id, replicas, namespace)

    def _scale_sync(
        self, service_id: str, replicas: int, namespace: str | None
    ) -> DeploymentStatus:
        ecs = self._client("ecs")
        cluster, name = _split_service_ref(service_id, namespace)
        try:
            response = ecs.update_service(
                cluster=cluster,
                service=name,
                desiredCount=int(replicas),
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"ECS update_service failed: {exc}",
                provider=self.provider_alias,
                code="ecs_error",
            ) from exc
        return _ecs_service_to_status(
            response.get("service") or {}, provider_alias=self.provider_alias
        )

    async def restart(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
    ) -> DeploymentStatus:
        return await asyncio.to_thread(self._restart_sync, service_id, namespace)

    def _restart_sync(self, service_id: str, namespace: str | None) -> DeploymentStatus:
        ecs = self._client("ecs")
        cluster, name = _split_service_ref(service_id, namespace)
        try:
            response = ecs.update_service(
                cluster=cluster,
                service=name,
                forceNewDeployment=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"ECS update_service(forceNewDeployment=True) failed: {exc}",
                provider=self.provider_alias,
                code="ecs_error",
            ) from exc
        return _ecs_service_to_status(
            response.get("service") or {}, provider_alias=self.provider_alias
        )

    # --- status / list_deployments ------------------------------------

    async def status(
        self, service_id: str, *, namespace: str | None = None
    ) -> DeploymentStatus:
        # Try the EKS delegate first when configured (matches existing behaviour).
        k8s = self._maybe_kubernetes_provider()
        if k8s is not None:
            try:
                return await k8s.status(service_id, namespace=namespace)
            except Exception:  # noqa: BLE001
                logger.debug("EKS status delegate failed; falling back to ECS", exc_info=True)
        return await asyncio.to_thread(self._status_sync, service_id, namespace)

    def _status_sync(self, service_id: str, namespace: str | None) -> DeploymentStatus:
        ecs = self._client("ecs")
        cluster, name = _split_service_ref(service_id, namespace)
        described = ecs.describe_services(cluster=cluster, services=[name])
        services = described.get("services") or []
        if not services:
            return DeploymentStatus(
                service_id=name,
                provider=self.provider_alias,
                phase=DeploymentLifecyclePhase.UNKNOWN,
                namespace=cluster,
            )
        return _ecs_service_to_status(services[0], provider_alias=self.provider_alias)

    async def list_deployments(
        self, *, namespace: str | None = None
    ) -> list[DeploymentStatus]:
        k8s = self._maybe_kubernetes_provider()
        if k8s is not None:
            try:
                return await k8s.list_deployments(namespace=namespace)
            except Exception:  # noqa: BLE001
                logger.debug("EKS list_deployments delegate failed; falling back to ECS", exc_info=True)
        return await asyncio.to_thread(self._list_sync, namespace)

    def _list_sync(self, namespace: str | None) -> list[DeploymentStatus]:
        ecs = self._client("ecs")
        cluster = namespace or os.environ.get("AQP_AWS_ECS_DEFAULT_CLUSTER", "default")
        paginator = ecs.get_paginator("list_services")
        arns: list[str] = []
        for page in paginator.paginate(cluster=cluster):
            arns.extend(page.get("serviceArns") or [])
        results: list[DeploymentStatus] = []
        # describe_services takes at most 10 services per call.
        for i in range(0, len(arns), 10):
            chunk = arns[i : i + 10]
            described = ecs.describe_services(cluster=cluster, services=chunk)
            for svc in described.get("services") or []:
                results.append(
                    _ecs_service_to_status(svc, provider_alias=self.provider_alias)
                )
        return results

    # --- exec (SSM ECS Exec) -----------------------------------------

    async def exec(
        self,
        service_id: str,
        *,
        command: list[str],
        container: str | None = None,
        timeout_seconds: int = 60,
        stdin: bytes | None = None,
        namespace: str | None = None,
    ) -> WorkloadExecResult:
        if os.environ.get("AQP_AWS_ECS_EXEC_ENABLED", "").lower() not in ("1", "true", "yes"):
            raise InfrastructureProviderUnavailable(
                "ECS Exec disabled. Set AQP_AWS_ECS_EXEC_ENABLED=true and "
                "ensure the task definition has 'enableExecuteCommand=true'.",
                provider=self.provider_alias,
                details={"action": "exec"},
            )
        return await asyncio.to_thread(
            self._exec_sync,
            service_id=service_id,
            command=command,
            container=container,
            timeout_seconds=timeout_seconds,
            namespace=namespace,
        )

    def _exec_sync(
        self,
        *,
        service_id: str,
        command: list[str],
        container: str | None,
        timeout_seconds: int,
        namespace: str | None,
    ) -> WorkloadExecResult:
        ecs = self._client("ecs")
        cluster, name = _split_service_ref(service_id, namespace)
        # Pick the first task of the service.
        listed = ecs.list_tasks(cluster=cluster, serviceName=name, desiredStatus="RUNNING")
        task_arns = listed.get("taskArns") or []
        if not task_arns:
            raise InfrastructureProviderError(
                f"ECS service {name!r} has no running tasks; nothing to exec into",
                provider=self.provider_alias,
                code="no_tasks_running",
            )
        # Joined command string per boto3 ecs.execute_command contract.
        cmd_str = " ".join(command)
        started_at = datetime.now(timezone.utc)
        try:
            response = ecs.execute_command(
                cluster=cluster,
                task=task_arns[0],
                container=container or "",
                command=cmd_str,
                interactive=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"ECS execute_command failed: {exc}",
                provider=self.provider_alias,
                code="ecs_exec_error",
            ) from exc
        finished_at = datetime.now(timezone.utc)
        # Per AWS API: execute_command does NOT return stdout/stderr in
        # the response — operators stream output through the returned
        # SSM session. The Management Engine treats the response as a
        # success acknowledgement (returncode=None) so the audit row
        # captures the action even though no output is returned.
        elapsed_ms = (finished_at - started_at).total_seconds() * 1000.0
        return WorkloadExecResult(
            service_id=name,
            namespace=cluster,
            container=container,
            command=command,
            stdout="",
            stderr="",
            returncode=None,
            elapsed_ms=elapsed_ms,
            started_at=started_at,
            finished_at=finished_at,
        )

    # --- tail_logs (CloudWatch Logs) ---------------------------------

    async def tail_logs(
        self,
        service_id: str,
        *,
        container: str | None = None,
        since_seconds: int | None = None,
        tail: int | None = 200,
        follow: bool = False,
        max_lines: int | None = None,
        namespace: str | None = None,
    ) -> AsyncIterator[WorkloadLogEvent]:
        cluster, name = _split_service_ref(service_id, namespace)
        log_group = os.environ.get(
            "AQP_AWS_ECS_LOG_GROUP_OVERRIDE",
            _bedrock_log_group(name),
        )
        client = self._client("logs")

        async def _gen() -> AsyncIterator[WorkloadLogEvent]:
            start_time_ms: int | None = None
            if since_seconds is not None:
                start_time_ms = int((time.time() - int(since_seconds)) * 1000)

            next_token: str | None = None
            line_budget = int(max_lines or 0)
            yielded = 0
            while True:
                kwargs: dict[str, Any] = {
                    "logGroupName": log_group,
                    "logStreamNamePrefix": container or name,
                    "limit": int(tail or 200),
                }
                if start_time_ms is not None:
                    kwargs["startTime"] = start_time_ms
                if next_token:
                    kwargs["nextToken"] = next_token
                try:
                    streams = await asyncio.to_thread(
                        client.describe_log_streams, **{
                            "logGroupName": log_group,
                            "logStreamNamePrefix": container or name,
                            "orderBy": "LastEventTime",
                            "descending": True,
                            "limit": 5,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("CloudWatch describe_log_streams failed: %s", exc)
                    return
                stream_names = [s["logStreamName"] for s in streams.get("logStreams") or []]
                if not stream_names:
                    return
                for stream_name in stream_names:
                    try:
                        events = await asyncio.to_thread(
                            client.get_log_events,
                            logGroupName=log_group,
                            logStreamName=stream_name,
                            startFromHead=True,
                            limit=int(tail or 200),
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "CloudWatch get_log_events failed for %s: %s",
                            stream_name,
                            exc,
                        )
                        continue
                    for ev in events.get("events") or []:
                        ts = ev.get("timestamp")
                        yield WorkloadLogEvent(
                            service_id=name,
                            namespace=cluster,
                            container=container,
                            line=str(ev.get("message", "")),
                            timestamp=(
                                datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
                                if ts is not None
                                else None
                            ),
                            source="stdout",
                        )
                        yielded += 1
                        if line_budget and yielded >= line_budget:
                            return
                if not follow:
                    return
                # Poll cadence — matches the existing K8s adapter's
                # default and respects the platform-core throttling
                # contract (avoid burning CloudWatch read budget).
                await asyncio.sleep(2.0)

        return _gen()

    # --- rotate_secret -----------------------------------------------

    async def rotate_secret(
        self,
        service_id: str,
        *,
        secret_name: str,
        namespace: str | None = None,
        backend: str | None = None,
    ) -> SecretRotationResult:
        return await asyncio.to_thread(
            self._rotate_secret_sync,
            service_id=service_id,
            secret_name=secret_name,
            namespace=namespace,
        )

    def _rotate_secret_sync(
        self,
        *,
        service_id: str,
        secret_name: str,
        namespace: str | None,
    ) -> SecretRotationResult:
        prefix = os.environ.get(
            _ROTATABLE_SECRET_PREFIX_ENV, _DEFAULT_ROTATABLE_PREFIX
        )
        if not secret_name.startswith(prefix):
            raise InfrastructureProviderError(
                (
                    f"AWS rotate_secret refused: secret name {secret_name!r} is "
                    f"outside the rotatable prefix {prefix!r}. Set "
                    f"{_ROTATABLE_SECRET_PREFIX_ENV} to override (audit-reviewed)."
                ),
                provider=self.provider_alias,
                code="secret_outside_prefix",
                details={"prefix": prefix, "secret_name": secret_name},
            )
        sm = self._client("secretsmanager")
        try:
            response = sm.rotate_secret(SecretId=secret_name)
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"Secrets Manager rotate_secret failed: {exc}",
                provider=self.provider_alias,
                code="rotation_failed",
            ) from exc
        return SecretRotationResult(
            service_id=service_id,
            secret_name=secret_name,
            backend="aws_secretsmanager",
            rotation_id=response.get("VersionId"),
            new_version=response.get("VersionId"),
            rotated_at=datetime.now(timezone.utc),
            metadata={"arn": response.get("ARN")},
        )

    # --- apply_config (SSM Parameter Store, denylist-guarded) --------

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        return await asyncio.to_thread(self._apply_config_sync, patch)

    def _apply_config_sync(self, patch: ConfigMapPatch) -> bool:
        bad_keys = [k for k in (patch.values or {}) if _is_secret_like(k)]
        if bad_keys:
            raise InfrastructureProviderError(
                (
                    "apply_config refused: key names look secret-like. Use "
                    "rotate_secret + Secrets Manager for these instead: "
                    f"{sorted(bad_keys)}"
                ),
                provider=self.provider_alias,
                code="secret_like_key",
                details={"keys": sorted(bad_keys)},
            )
        ssm = self._client("ssm")
        env = os.environ.get("AQP_CP_TOPOLOGY_TARGET_ID") or os.environ.get(
            "AQP_ENVIRONMENT", "dev"
        )
        prefix = f"/aqp/{env}/services/{patch.service_id}/"
        written = 0
        for key, value in (patch.values or {}).items():
            try:
                ssm.put_parameter(
                    Name=prefix + key,
                    Value=str(value),
                    Type="String",
                    Overwrite=True,
                )
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SSM put_parameter failed for %s: %s", prefix + key, exc
                )
        for key in patch.delete_keys or []:
            try:
                ssm.delete_parameter(Name=prefix + key)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "SSM delete_parameter ignored for %s: %s",
                    prefix + key,
                    exc,
                )
        return written > 0


__all__ = ["AwsProvider"]
