"""Kaniko in-cluster image build orchestrator.

Phase 1.2 of the control-plane maturation. Submits a Chainguard-Kaniko
``Job`` pod that builds a Dockerfile context and pushes the resulting
OCI image to the destination registry. Credentials resolve at runtime
via EKS Pod Identity / IRSA / Workload Identity Federation — never
through Kubernetes Secrets containing cloud credentials.

The orchestrator wraps every action in :class:`WorkloadRuntime`
(audit lifecycle + halt fan-out). Three source kinds ship today:

- :class:`GitBuildSource` — clones a repo via the Kaniko args.
- :class:`ConfigMapBuildSource` — mounts a ConfigMap that contains
  the Dockerfile + optional build context. Useful for the test
  suite + small Dockerfile-driven flows.
- :class:`S3BuildSource` — uses Kaniko's S3 context support; auth
  comes through the pod's IRSA / Workload Identity binding.

Reference: Kaniko's original GoogleContainerTools repository was
archived by Google in June 2025; the maintained successor is
``chainguard-dev/kaniko``. Pin the image SHA in production.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Default labels stamped on every Job for selector + audit consumption.
_DEFAULT_LABELS: dict[str, str] = {
    "aqp.io/component": "kaniko-builder",
    "aqp.io/managed-by": "aqp-control-plane",
}


class BuildSourceKind(str, Enum):
    GIT = "git"
    CONFIGMAP = "configmap"
    S3 = "s3"


@dataclass(frozen=True, slots=True)
class GitBuildSource:
    """Build context fetched from a Git repository.

    Kaniko translates ``--context=git://<repo>#refs/heads/<branch>`` to
    the equivalent ``--context`` flag. Authentication for private
    repos relies on the runner SA having a kubernetes-side Git
    credential helper installed; we do NOT inject tokens via the Job
    body.
    """

    repo_url: str
    branch: str = "main"
    sub_path: str = ""
    kind: BuildSourceKind = BuildSourceKind.GIT


@dataclass(frozen=True, slots=True)
class ConfigMapBuildSource:
    """Build context mounted from a ConfigMap.

    The ConfigMap MUST contain a ``Dockerfile`` key plus any
    additional context files. The Job mounts the ConfigMap at
    ``/workspace`` and passes ``--context=dir:///workspace``.
    """

    configmap_name: str
    kind: BuildSourceKind = BuildSourceKind.CONFIGMAP


@dataclass(frozen=True, slots=True)
class S3BuildSource:
    """Build context fetched from S3.

    Kaniko supports ``--context=s3://<bucket>/<key>`` with native
    auth via the pod's IRSA binding. The runner SA MUST have
    ``s3:GetObject`` on the bucket path.
    """

    bucket: str
    key: str
    region: str = ""
    kind: BuildSourceKind = BuildSourceKind.S3


BuildSource = GitBuildSource | ConfigMapBuildSource | S3BuildSource


@dataclass(slots=True)
class KanikoBuildSpec:
    """Inputs to :meth:`KanikoBuilder.submit`."""

    image_ref: str
    source: BuildSource
    namespace: str | None = None
    builder_sa: str | None = None
    image: str | None = None
    build_args: dict[str, str] = field(default_factory=dict)
    extra_kaniko_args: tuple[str, ...] = field(default_factory=tuple)
    cache_enabled: bool = True
    backoff_limit: int | None = None
    ttl_seconds_after_finished: int | None = None
    owner_uid: str | None = None
    owner_kind: str = "QuantAgent"
    owner_api_version: str = "aqp.io/v1"
    owner_name: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class KanikoBuildStatus:
    """Result of :meth:`KanikoBuilder.submit`."""

    job_name: str
    namespace: str
    image_ref: str
    submitted_at: datetime
    builder_image: str
    builder_sa: str
    selector: str
    source_kind: BuildSourceKind
    args: list[str] = field(default_factory=list)


def render_kaniko_job(
    spec: KanikoBuildSpec,
    *,
    default_image: str,
    default_namespace: str,
    default_builder_sa: str,
    default_ttl_seconds: int,
    default_backoff_limit: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Render a ``batch/v1`` Kaniko Job manifest as a dict.

    Pure function so unit tests can snapshot the manifest without
    spinning up Kubernetes. The Job:

    - Mounts the build context per the source kind.
    - Pins the kaniko image (Chainguard fork by default).
    - Drops the workspace ConfigMap into ``/workspace`` when needed.
    - Sets ``ttlSecondsAfterFinished`` so the cluster cleans itself
      up after the build completes.
    - Sets an ``ownerReferences`` block when ``owner_uid`` is set so
      the Job is GC'd alongside its parent CR / Deployment.
    """
    now = now or datetime.now(timezone.utc)
    namespace = spec.namespace or default_namespace
    builder_image = spec.image or default_image
    builder_sa = spec.builder_sa or default_builder_sa
    ttl = spec.ttl_seconds_after_finished or default_ttl_seconds
    backoff = spec.backoff_limit if spec.backoff_limit is not None else default_backoff_limit

    job_name = f"build-{uuid.uuid4().hex[:10]}"
    labels: dict[str, str] = {**_DEFAULT_LABELS, **spec.labels}
    annotations: dict[str, str] = {
        "aqp.io/image-ref": spec.image_ref,
        "aqp.io/source-kind": spec.source.kind.value,
        "aqp.io/submitted-at": now.isoformat(),
        **spec.annotations,
    }
    args = _build_kaniko_args(spec)

    container: dict[str, Any] = {
        "name": "kaniko",
        "image": builder_image,
        "args": args,
        "imagePullPolicy": "IfNotPresent",
        "env": [
            {"name": "AWS_SDK_LOAD_CONFIG", "value": "true"},
            {"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": ""},
        ],
        "securityContext": {
            "runAsNonRoot": False,  # kaniko needs root inside its rootless build.
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": False,
            "capabilities": {"drop": ["ALL"]},
        },
    }

    pod_spec: dict[str, Any] = {
        "restartPolicy": "Never",
        "serviceAccountName": builder_sa,
        "containers": [container],
        "volumes": [],
    }

    if isinstance(spec.source, ConfigMapBuildSource):
        container["volumeMounts"] = [
            {"name": "workspace", "mountPath": "/workspace"},
        ]
        pod_spec["volumes"].append(
            {
                "name": "workspace",
                "configMap": {"name": spec.source.configmap_name},
            }
        )

    metadata: dict[str, Any] = {
        "name": job_name,
        "namespace": namespace,
        "labels": labels,
        "annotations": annotations,
    }
    if spec.owner_uid:
        metadata["ownerReferences"] = [
            {
                "apiVersion": spec.owner_api_version,
                "kind": spec.owner_kind,
                "name": spec.owner_name or spec.image_ref.split(":", 1)[0].split("/")[-1],
                "uid": spec.owner_uid,
                "controller": True,
                "blockOwnerDeletion": True,
            }
        ]

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": metadata,
        "spec": {
            "ttlSecondsAfterFinished": ttl,
            "backoffLimit": backoff,
            "template": {
                "metadata": {"labels": labels},
                "spec": pod_spec,
            },
        },
    }


def _build_kaniko_args(spec: KanikoBuildSpec) -> list[str]:
    args: list[str] = [
        "--dockerfile=/workspace/Dockerfile"
        if isinstance(spec.source, ConfigMapBuildSource)
        else "--dockerfile=Dockerfile",
        f"--destination={spec.image_ref}",
        "--snapshot-mode=redo",
        "--use-new-run",
    ]
    if spec.cache_enabled:
        args.append("--cache=true")
    if isinstance(spec.source, GitBuildSource):
        ref = f"{spec.source.repo_url}#refs/heads/{spec.source.branch}"
        if spec.source.sub_path:
            ref = f"{ref}:{spec.source.sub_path}"
        args.append(f"--context=git://{ref}")
    elif isinstance(spec.source, ConfigMapBuildSource):
        args.append("--context=dir:///workspace")
    elif isinstance(spec.source, S3BuildSource):
        args.append(f"--context=s3://{spec.source.bucket}/{spec.source.key}")
        if spec.source.region:
            args.append(f"--region={spec.source.region}")
    for key, value in spec.build_args.items():
        args.append(f"--build-arg={key}={value}")
    args.extend(spec.extra_kaniko_args)
    return args


class KanikoBuilder:
    """Submit + observe Kaniko Job runs in-cluster.

    Wraps the official ``kubernetes`` Python client BatchV1Api so the
    builder shares the same import-on-first-use behaviour as the
    :class:`aqp_cp.providers.kubernetes.KubernetesProvider`.

    Use the :meth:`render` static helper from tests + dry-run paths so
    the manifest can be inspected without touching the cluster.
    """

    def __init__(
        self,
        *,
        default_image: str,
        default_namespace: str,
        default_builder_sa: str,
        default_ttl_seconds: int = 600,
        default_backoff_limit: int = 2,
    ) -> None:
        self._default_image = default_image
        self._default_namespace = default_namespace
        self._default_builder_sa = default_builder_sa
        self._default_ttl_seconds = default_ttl_seconds
        self._default_backoff_limit = default_backoff_limit

    def render(self, spec: KanikoBuildSpec, *, now: datetime | None = None) -> dict[str, Any]:
        return render_kaniko_job(
            spec,
            default_image=self._default_image,
            default_namespace=self._default_namespace,
            default_builder_sa=self._default_builder_sa,
            default_ttl_seconds=self._default_ttl_seconds,
            default_backoff_limit=self._default_backoff_limit,
            now=now,
        )

    async def submit(self, spec: KanikoBuildSpec) -> KanikoBuildStatus:
        """Submit the rendered Job and return a :class:`KanikoBuildStatus`.

        Raises :class:`RuntimeError` when the kubernetes SDK is not
        installed (the CP can ship a slim image without it).
        """
        import asyncio  # local import to avoid the SDK at module load.

        try:
            from kubernetes import client, config  # type: ignore[import-not-found]
            from kubernetes.client.exceptions import ApiException  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "kubernetes SDK not installed (pip install 'aqp-control-plane[kubernetes]')",
            ) from exc

        manifest = self.render(spec)

        def _apply() -> str:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            batch = client.BatchV1Api()
            try:
                batch.create_namespaced_job(
                    namespace=manifest["metadata"]["namespace"],
                    body=manifest,
                )
            except ApiException as exc:
                raise RuntimeError(
                    f"kaniko job create failed: HTTP {exc.status} {exc.reason}: {exc.body}"
                ) from exc
            return str(manifest["metadata"]["name"])

        job_name = await asyncio.to_thread(_apply)
        return KanikoBuildStatus(
            job_name=job_name,
            namespace=manifest["metadata"]["namespace"],
            image_ref=spec.image_ref,
            submitted_at=datetime.now(timezone.utc),
            builder_image=manifest["spec"]["template"]["spec"]["containers"][0]["image"],
            builder_sa=manifest["spec"]["template"]["spec"]["serviceAccountName"],
            selector=f"job-name={job_name}",
            source_kind=spec.source.kind,
            args=list(manifest["spec"]["template"]["spec"]["containers"][0]["args"]),
        )


__all__ = [
    "BuildSource",
    "BuildSourceKind",
    "ConfigMapBuildSource",
    "GitBuildSource",
    "KanikoBuilder",
    "KanikoBuildSpec",
    "KanikoBuildStatus",
    "S3BuildSource",
    "render_kaniko_job",
]
