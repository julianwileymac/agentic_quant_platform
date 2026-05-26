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
            # Phase J — derive a task definition from the DeploymentSpec.
            # Operators who want full control still pass
            # ``metadata.task_definition``; everyone else gets a
            # sensible derived def + a registered revision.
            task_def = self._register_task_definition_from_spec(spec)

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

    def _register_task_definition_from_spec(self, spec: DeploymentSpec) -> str:
        """Derive + register an ECS task definition from a ``DeploymentSpec``.

        Used when the caller hasn't pre-registered one. Honors
        :attr:`DeploymentSpec.metadata` overrides for IAM roles,
        log group, and capacity provider:

        - ``metadata.execution_role_arn``  — required for ECR pulls + SM reads
        - ``metadata.task_role_arn``       — required for in-task IAM
        - ``metadata.cpu_architecture``    — ``ARM64`` | ``X86_64`` (default ARM64)
        - ``metadata.log_group``           — defaults to ``/aws/ecs/<service_id>``
        - ``metadata.runtime_platform``    — overrides the OS family
        - ``metadata.secrets``             — Secrets Manager ARN list ([{name, valueFrom}])

        Returns the task definition ARN that ``create_service`` /
        ``update_service`` can reference. Raises
        :class:`InfrastructureProviderError` when execution_role_arn
        is unset (ECR pulls would fail with no IAM identity).
        """
        execution_role_arn = spec.metadata.get("execution_role_arn")
        if not execution_role_arn:
            raise InfrastructureProviderError(
                "DeploymentSpec.metadata.execution_role_arn is required "
                "when no pre-registered task_definition is supplied — ECR pulls "
                "need an IAM identity. Pre-register via the "
                "modules/ecs-fargate-control-plane Terraform module or supply "
                "the role ARN here.",
                provider=self.provider_alias,
                code="missing_execution_role",
            )
        task_role_arn = spec.metadata.get("task_role_arn")

        region = os.environ.get("AWS_REGION") or "us-east-1"
        log_group = spec.metadata.get("log_group") or f"/aws/ecs/{spec.service_id}"
        cpu_arch = str(spec.metadata.get("cpu_architecture") or "ARM64").upper()
        family = f"aqp-derived-{spec.service_id}"

        port_mappings = [
            {"containerPort": int(p), "protocol": "tcp"} for p in spec.ports
        ]
        environment = [
            {"name": k, "value": v} for k, v in (spec.env or {}).items()
        ]
        secrets = list(spec.metadata.get("secrets") or [])

        container_def = {
            "name": spec.service_id,
            "image": spec.image,
            "essential": True,
            "portMappings": port_mappings,
            "environment": environment,
            "secrets": secrets,
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": log_group,
                    "awslogs-region": region,
                    "awslogs-stream-prefix": spec.service_id,
                    "awslogs-create-group": "true",
                },
            },
        }
        if spec.command:
            container_def["entryPoint"] = list(spec.command)
        if spec.args:
            container_def["command"] = list(spec.args)
        if spec.health_check_path and spec.health_check_port:
            container_def["healthCheck"] = {
                "command": [
                    "CMD-SHELL",
                    f"curl -fsS http://127.0.0.1:{spec.health_check_port}{spec.health_check_path} || exit 1",
                ],
                "interval": 30,
                "timeout": 10,
                "retries": 3,
                "startPeriod": 30,
            }

        # ECS Fargate CPU+memory must be a valid Fargate combination —
        # default to 0.5 vCPU + 1 GiB which is the cheapest line.
        fargate_cpu = str(spec.metadata.get("fargate_cpu") or "512")
        fargate_memory = str(spec.metadata.get("fargate_memory") or "1024")

        register_kwargs: dict[str, Any] = {
            "family": family,
            "networkMode": "awsvpc",
            "requiresCompatibilities": ["FARGATE"],
            "cpu": fargate_cpu,
            "memory": fargate_memory,
            "executionRoleArn": execution_role_arn,
            "containerDefinitions": [container_def],
            "runtimePlatform": {
                "operatingSystemFamily": "LINUX",
                "cpuArchitecture": cpu_arch,
            },
            "tags": [
                {"key": k, "value": v}
                for k, v in (spec.labels or {}).items()
            ],
        }
        if task_role_arn:
            register_kwargs["taskRoleArn"] = task_role_arn

        ecs = self._client("ecs")
        try:
            response = ecs.register_task_definition(**register_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise InfrastructureProviderError(
                f"ECS register_task_definition failed for family={family}: {exc}",
                provider=self.provider_alias,
                code="register_task_definition_failed",
                details={"family": family},
            ) from exc
        td = response.get("taskDefinition") or {}
        arn = td.get("taskDefinitionArn") or ""
        if not arn:
            raise InfrastructureProviderError(
                "register_task_definition returned no taskDefinitionArn",
                provider=self.provider_alias,
                code="register_task_definition_no_arn",
            )
        logger.info(
            "Registered derived ECS task definition family=%s revision=%s",
            family,
            td.get("revision"),
        )
        return arn

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
        """Run ``command`` inside a running task; capture stdout if possible.

        Two paths:

        1. **Preferred** — ``aws ecs execute-command`` via the CLI, which
           shells out to the SSM Session Manager plugin and returns the
           captured stdout/stderr/returncode on completion. Requires the
           ``session-manager-plugin`` to be on PATH in the CP image.
        2. **Fallback** — direct ``boto3.client('ecs').execute_command``
           which only acknowledges the session start (the SSM session
           streams output back through a separate channel that boto3
           doesn't surface). Returns ``returncode=None`` with empty
           output but lets the operator know the command WAS dispatched.

        The CLI path is opt-in via ``AQP_AWS_ECS_EXEC_CAPTURE_OUTPUT=true``
        because it requires the session-manager-plugin binary in the
        CP container (not in the base Chainguard image).
        """
        import shutil
        import subprocess

        ecs = self._client("ecs")
        cluster, name = _split_service_ref(service_id, namespace)
        listed = ecs.list_tasks(cluster=cluster, serviceName=name, desiredStatus="RUNNING")
        task_arns = listed.get("taskArns") or []
        if not task_arns:
            raise InfrastructureProviderError(
                f"ECS service {name!r} has no running tasks; nothing to exec into",
                provider=self.provider_alias,
                code="no_tasks_running",
            )
        task_arn = task_arns[0]
        cmd_str = " ".join(command)
        started_at = datetime.now(timezone.utc)

        capture_output = (
            os.environ.get("AQP_AWS_ECS_EXEC_CAPTURE_OUTPUT", "").lower()
            in ("1", "true", "yes")
            and shutil.which("aws") is not None
            and shutil.which("session-manager-plugin") is not None
        )

        if capture_output:
            # Real stdout/stderr capture via the AWS CLI + SSM plugin.
            cli_argv = [
                "aws", "ecs", "execute-command",
                "--cluster", cluster,
                "--task", task_arn,
                "--command", cmd_str,
                "--interactive",
                "--region", os.environ.get("AWS_REGION") or "us-east-1",
            ]
            if container:
                cli_argv.extend(["--container", container])
            try:
                completed = subprocess.run(  # noqa: S603 - exec is the sanctioned caller
                    cli_argv,
                    capture_output=True,
                    text=True,
                    timeout=int(timeout_seconds),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                finished_at = datetime.now(timezone.utc)
                return WorkloadExecResult(
                    service_id=name,
                    namespace=cluster,
                    container=container,
                    command=command,
                    stdout=exc.stdout or "",
                    stderr=(exc.stderr or "") + "\n[timeout]",
                    returncode=124,
                    elapsed_ms=(finished_at - started_at).total_seconds() * 1000.0,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            finished_at = datetime.now(timezone.utc)
            return WorkloadExecResult(
                service_id=name,
                namespace=cluster,
                container=container,
                command=command,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
                returncode=int(completed.returncode),
                elapsed_ms=(finished_at - started_at).total_seconds() * 1000.0,
                started_at=started_at,
                finished_at=finished_at,
            )

        # Boto3 fallback — session ack only.
        try:
            ecs.execute_command(
                cluster=cluster,
                task=task_arn,
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
        logger.warning(
            "ECS exec dispatched without output capture "
            "(set AQP_AWS_ECS_EXEC_CAPTURE_OUTPUT=true + install "
            "session-manager-plugin to capture stdout/stderr)."
        )
        return WorkloadExecResult(
            service_id=name,
            namespace=cluster,
            container=container,
            command=command,
            stdout="",
            stderr="",
            returncode=None,
            elapsed_ms=(finished_at - started_at).total_seconds() * 1000.0,
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
        """Stream CloudWatch Logs events for an ECS service.

        Phase J fix — the prior impl re-described streams every loop AND
        re-fetched from the head every time, re-yielding the same lines
        forever and hammering the CloudWatch read budget. The new impl:

        1. Discovers candidate streams ONCE (matching ``container``
           prefix when set, else the service name prefix).
        2. Tracks per-stream ``nextForwardToken`` so each subsequent
           ``get_log_events`` call returns only NEW events.
        3. Sleeps 2s between poll rounds when ``follow=True``.
        4. Honors ``max_lines`` as a hard ceiling across every stream.

        Log group resolution order:

        - ``AQP_AWS_ECS_LOG_GROUP_OVERRIDE`` env var (forces a single LG)
        - ``spec.metadata.log_group`` (unused here — set on the task def)
        - default: ``/aws/ecs/<service>``
        """
        cluster, name = _split_service_ref(service_id, namespace)
        log_group = os.environ.get(
            "AQP_AWS_ECS_LOG_GROUP_OVERRIDE",
            _bedrock_log_group(name),
        )
        client = self._client("logs")
        stream_prefix = container or name

        async def _gen() -> AsyncIterator[WorkloadLogEvent]:
            start_time_ms: int | None = None
            if since_seconds is not None:
                start_time_ms = int((time.time() - int(since_seconds)) * 1000)

            # Discover the candidate streams once.
            try:
                streams_resp = await asyncio.to_thread(
                    client.describe_log_streams,
                    logGroupName=log_group,
                    logStreamNamePrefix=stream_prefix,
                    orderBy="LastEventTime",
                    descending=True,
                    limit=5,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "CloudWatch describe_log_streams failed log_group=%s prefix=%s: %s",
                    log_group,
                    stream_prefix,
                    exc,
                )
                return
            stream_names = [
                str(s.get("logStreamName") or "")
                for s in (streams_resp.get("logStreams") or [])
                if s.get("logStreamName")
            ]
            if not stream_names:
                return

            # Per-stream forward token; None means "start at startFromHead".
            forward_tokens: dict[str, str | None] = {s: None for s in stream_names}
            line_budget = int(max_lines or 0)
            yielded = 0

            while True:
                any_yielded_this_round = False
                for stream_name in stream_names:
                    kwargs: dict[str, Any] = {
                        "logGroupName": log_group,
                        "logStreamName": stream_name,
                        "limit": int(tail or 200),
                        "startFromHead": True,
                    }
                    token = forward_tokens.get(stream_name)
                    if token:
                        kwargs["nextToken"] = token
                    elif start_time_ms is not None:
                        kwargs["startTime"] = start_time_ms
                    try:
                        events_resp = await asyncio.to_thread(
                            client.get_log_events, **kwargs
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "CloudWatch get_log_events failed stream=%s: %s",
                            stream_name,
                            exc,
                        )
                        continue
                    for ev in events_resp.get("events") or []:
                        ts = ev.get("timestamp")
                        any_yielded_this_round = True
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
                    new_token = events_resp.get("nextForwardToken")
                    if new_token and new_token != token:
                        forward_tokens[stream_name] = new_token
                if not follow:
                    return
                # 2s poll cadence — matches the K8s adapter's default.
                # When no new events landed last round, back off slightly
                # to be kinder to the CloudWatch read budget.
                await asyncio.sleep(2.0 if any_yielded_this_round else 5.0)

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
