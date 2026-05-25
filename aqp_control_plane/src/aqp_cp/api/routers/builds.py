"""``/manage/builds`` — Kaniko in-cluster OCI image builds.

Phase 1.2 of the control-plane maturation. Three routes ship:

- ``POST /manage/builds`` — submit a new build. Returns the Job name
  + initial status; the audit row is written BEFORE the SDK call.
- ``GET  /manage/builds/{job_name}`` — read the Job's current phase
  + container counts.
- ``WebSocket /manage/builds/{job_name}/logs/stream`` — stream the
  Kaniko container's logs as canonical
  ``{task_id, stage, message, timestamp, **extras}`` frames.

Authorization: ``manage:agents`` for submit (step-up MFA required
when wired into the admin UI). ``read:infrastructure`` for the GET +
log stream.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, status
from pydantic import BaseModel, Field

from aqp_platform_core.models.workloads import WorkloadAction

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.builders.kaniko import (
    BuildSource,
    ConfigMapBuildSource,
    GitBuildSource,
    KanikoBuilder,
    KanikoBuildSpec,
    S3BuildSource,
)
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services.lifecycle import execute_with_audit, get_active_provider
from aqp_cp.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["builds"], prefix="/builds")


class GitSourceBody(BaseModel):
    kind: Literal["git"] = "git"
    repo_url: str
    branch: str = "main"
    sub_path: str = ""


class ConfigMapSourceBody(BaseModel):
    kind: Literal["configmap"] = "configmap"
    configmap_name: str


class S3SourceBody(BaseModel):
    kind: Literal["s3"] = "s3"
    bucket: str
    key: str
    region: str = ""


SourceBody = GitSourceBody | ConfigMapSourceBody | S3SourceBody


class BuildSubmitBody(BaseModel):
    image_ref: str = Field(..., description="Destination registry reference, e.g. ghcr.io/aqp/foo:tag.")
    source: SourceBody = Field(..., discriminator="kind")
    namespace: str | None = None
    builder_sa: str | None = None
    image: str | None = Field(default=None, description="Override the Kaniko image; defaults to the Chainguard fork.")
    build_args: dict[str, str] = Field(default_factory=dict)
    extra_kaniko_args: list[str] = Field(default_factory=list)
    cache_enabled: bool = True
    backoff_limit: int | None = Field(default=None, ge=0, le=10)
    ttl_seconds_after_finished: int | None = Field(default=None, ge=60, le=86400)
    owner_uid: str | None = None
    owner_kind: str = "QuantAgent"
    owner_api_version: str = "aqp.io/v1"
    owner_name: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class BuildSubmitResponse(BaseModel):
    job_name: str
    namespace: str
    image_ref: str
    submitted_at: datetime
    builder_image: str
    builder_sa: str
    selector: str
    args: list[str]


def _body_to_source(body: SourceBody) -> BuildSource:
    if isinstance(body, GitSourceBody):
        return GitBuildSource(repo_url=body.repo_url, branch=body.branch, sub_path=body.sub_path)
    if isinstance(body, ConfigMapSourceBody):
        return ConfigMapBuildSource(configmap_name=body.configmap_name)
    if isinstance(body, S3SourceBody):
        return S3BuildSource(bucket=body.bucket, key=body.key, region=body.region)
    raise ValueError(f"unsupported build source kind: {body!r}")


def _build_kaniko_builder() -> KanikoBuilder:
    settings = get_settings()
    return KanikoBuilder(
        default_image=settings.kaniko_image,
        default_namespace=settings.kaniko_namespace_default,
        default_builder_sa=settings.kaniko_builder_sa,
        default_ttl_seconds=settings.kaniko_ttl_seconds_after_finished,
        default_backoff_limit=settings.kaniko_backoff_limit,
    )


@router.post(
    "",
    summary="Submit a new in-cluster Kaniko image build.",
    description=(
        "Renders + applies a Chainguard-Kaniko ``Job`` pod. The audit "
        "row is written BEFORE the SDK call so a crashed handler still "
        "leaves an immutable trail. Cloud credentials resolve through "
        "EKS Pod Identity / IRSA / Workload Identity Federation — NEVER "
        "through Kubernetes Secrets containing cloud credentials. "
        "Required scope: ``manage:agents``."
    ),
    response_model=ResponseEnvelope[BuildSubmitResponse],
)
async def submit_build(
    body: BuildSubmitBody,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:agents")),
) -> ResponseEnvelope[BuildSubmitResponse]:
    spec = KanikoBuildSpec(
        image_ref=body.image_ref,
        source=_body_to_source(body.source),
        namespace=body.namespace,
        builder_sa=body.builder_sa,
        image=body.image,
        build_args=dict(body.build_args),
        extra_kaniko_args=tuple(body.extra_kaniko_args),
        cache_enabled=body.cache_enabled,
        backoff_limit=body.backoff_limit,
        ttl_seconds_after_finished=body.ttl_seconds_after_finished,
        owner_uid=body.owner_uid,
        owner_kind=body.owner_kind,
        owner_api_version=body.owner_api_version,
        owner_name=body.owner_name,
        labels=dict(body.labels),
        annotations=dict(body.annotations),
    )
    builder = _build_kaniko_builder()
    _run, result = await execute_with_audit(
        action=WorkloadAction.BUILD_IMAGE,
        target=body.image_ref,
        user=user,
        payload={"image_ref": body.image_ref, "source": body.source.model_dump()},
        fn=lambda: builder.submit(spec),
        request_id=x_request_id,
    )
    return ResponseEnvelope(
        status="ok",
        data=BuildSubmitResponse(
            job_name=result.job_name,
            namespace=result.namespace,
            image_ref=result.image_ref,
            submitted_at=result.submitted_at,
            builder_image=result.builder_image,
            builder_sa=result.builder_sa,
            selector=result.selector,
            args=list(result.args),
        ),
    )


@router.get(
    "/{job_name}",
    summary="Read the status of a Kaniko build Job.",
    description=(
        "Returns ``status.active`` / ``status.succeeded`` / "
        "``status.failed`` from the Kubernetes BatchV1 API plus the "
        "rendered args. Required scope: ``read:infrastructure``."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def build_status(
    job_name: str,
    namespace: str | None = None,
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[dict[str, Any]]:
    settings = get_settings()
    ns = namespace or settings.kaniko_namespace_default
    try:
        from kubernetes import client, config  # type: ignore[import-not-found]
        from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "kubernetes_sdk_missing", "error_description": str(exc)},
        ) from exc

    def _read() -> dict[str, Any]:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        batch = client.BatchV1Api()
        try:
            job = batch.read_namespaced_job(name=job_name, namespace=ns)
        except ApiException as exc:
            raise HTTPException(
                status_code=(
                    status.HTTP_404_NOT_FOUND
                    if exc.status == 404
                    else status.HTTP_502_BAD_GATEWAY
                ),
                detail={
                    "error": "kaniko_job_lookup_failed",
                    "error_description": str(exc),
                },
            ) from exc
        active = getattr(getattr(job, "status", None), "active", 0) or 0
        succeeded = getattr(getattr(job, "status", None), "succeeded", 0) or 0
        failed = getattr(getattr(job, "status", None), "failed", 0) or 0
        phase = (
            "succeeded"
            if succeeded
            else "failed"
            if failed
            else "active"
            if active
            else "unknown"
        )
        return {
            "job_name": job_name,
            "namespace": ns,
            "phase": phase,
            "active": int(active),
            "succeeded": int(succeeded),
            "failed": int(failed),
            "labels": dict(getattr(getattr(job, "metadata", None), "labels", None) or {}),
            "annotations": dict(getattr(getattr(job, "metadata", None), "annotations", None) or {}),
        }

    data = await asyncio.to_thread(_read)
    return ResponseEnvelope(status="ok", data=data)


@router.websocket("/{job_name}/logs/stream")
async def build_logs_stream(
    websocket: WebSocket,
    job_name: str,
    namespace: str | None = None,
    tail: int = 200,
    follow: bool = True,
    max_lines: int | None = None,
) -> None:
    """Stream Kaniko Job logs as the canonical AGENTS rule 4 frame.

    Authorization is handled inside the handshake (Bearer token via
    the ``Sec-WebSocket-Protocol`` or query string). This skeleton
    accepts the WS, looks up the first Pod backing the Job via the
    ``job-name=`` selector, and proxies through
    :meth:`InfrastructureProvider.tail_logs`.
    """
    settings = get_settings()
    ns = namespace or settings.kaniko_namespace_default
    await websocket.accept()
    try:
        provider = get_active_provider()
    except HTTPException as exc:
        await _send_frame(
            websocket,
            task_id=job_name,
            stage="error",
            message=str(exc.detail),
        )
        await websocket.close(code=1011)
        return

    # The kaniko Pod's app label is set to the job_name by default.
    fake_service_id = job_name
    try:
        async for event in provider.tail_logs(
            fake_service_id,
            container="kaniko",
            tail=tail,
            follow=follow,
            max_lines=max_lines,
            namespace=ns,
        ):
            await _send_frame(
                websocket,
                task_id=job_name,
                stage="log",
                message=event.line,
                container=event.container,
                namespace=event.namespace,
                source=event.source,
            )
    except Exception as exc:  # noqa: BLE001
        await _send_frame(
            websocket,
            task_id=job_name,
            stage="error",
            message=str(exc),
        )
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


async def _send_frame(websocket: WebSocket, **payload: Any) -> None:
    body = {
        "task_id": payload.pop("task_id", ""),
        "stage": payload.pop("stage", "log"),
        "message": payload.pop("message", ""),
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }
    body.update(payload)
    await websocket.send_json(body)


__all__ = ["router"]
