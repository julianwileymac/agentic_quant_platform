"""DataMCP tools backing the Phase 1 pod-level Kubernetes / Docker SDK
surface.

Agents reach pod listing, exec, log slices, and tar archive ops only
through these tools (AGENTS rule 22). The tools dispatch through
:func:`aqp.kubernetes.get_kubernetes_adapter` so they automatically
pick ``none`` / ``rpi_cluster`` / ``in_cluster`` / ``local_compose``
per ``settings.kubernetes_adapter`` (AGENTS rule 28 — the adapter is
the only sanctioned cluster-side surface).
"""
from __future__ import annotations

import base64
import logging
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.kubernetes import (
    KubernetesAdapterError,
    KubernetesAdapterUnavailable,
    get_kubernetes_adapter,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.kubernetes.list_pods
# ---------------------------------------------------------------------------


class ListPodsInput(BaseModel):
    namespace: str = Field(..., description="Kubernetes namespace or docker-compose project name.")
    label_selector: str | None = Field(
        default=None,
        description="Optional Kubernetes-style label selector (e.g. 'app=alpha-vantage').",
    )


@register_data_mcp_tool
class ListPodsTool(DataMCPTool):
    name = "data.kubernetes.list_pods"
    description = (
        "List pods (or docker-compose service containers) in a namespace. "
        "Returns compact descriptors with phase, node, IP, containers, and labels."
    )
    args_schema = ListPodsInput
    category = "kubernetes"
    tags = ("kubernetes", "pods", "browse")
    required_scopes = ("cluster:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        label_selector: str | None = None,
    ) -> MCPToolResult:
        adapter = get_kubernetes_adapter()
        try:
            pods = adapter.list_pods(namespace=namespace, label_selector=label_selector)
        except KubernetesAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=f"adapter unavailable: {exc}", summary="list_pods unavailable"
            )
        except KubernetesAdapterError as exc:
            return MCPToolResult(
                ok=False, error=str(exc), summary="list_pods failed"
            )
        data = [asdict(p) for p in pods]
        return MCPToolResult(
            ok=True,
            data={"namespace": namespace, "pods": data},
            rows_returned=len(data),
            summary=f"listed {len(data)} pods in {namespace}",
        )


# ---------------------------------------------------------------------------
# data.kubernetes.exec_in_pod
# ---------------------------------------------------------------------------


class ExecInPodInput(BaseModel):
    namespace: str
    name: str = Field(..., description="Pod name (k8s) or service / container name (compose).")
    command: list[str] = Field(..., min_length=1, description="Argv list.")
    container: str | None = Field(default=None)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    stdin_b64: str | None = Field(
        default=None,
        description="Optional base64-encoded stdin payload (in_cluster adapter only).",
    )


@register_data_mcp_tool
class ExecInPodTool(DataMCPTool):
    name = "data.kubernetes.exec_in_pod"
    description = (
        "Execute a command inside a running pod or container. Mutating. "
        "Returns stdout, stderr, returncode, and elapsed_ms."
    )
    args_schema = ExecInPodInput
    category = "kubernetes"
    tags = ("kubernetes", "exec")
    required_scopes = ("cluster:exec",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        name: str,
        command: list[str],
        container: str | None = None,
        timeout_seconds: int | None = None,
        stdin_b64: str | None = None,
    ) -> MCPToolResult:
        try:
            from aqp.config import settings

            default_timeout = int(getattr(settings, "k8s_exec_default_timeout", 120) or 120)
        except Exception:  # noqa: BLE001
            default_timeout = 120
        stdin: bytes | None = None
        if stdin_b64:
            try:
                stdin = base64.b64decode(stdin_b64)
            except Exception as exc:  # noqa: BLE001
                return MCPToolResult(
                    ok=False, error=f"invalid stdin_b64: {exc}", summary="bad stdin"
                )
        adapter = get_kubernetes_adapter()
        try:
            result = adapter.exec_in_pod(
                namespace=namespace,
                name=name,
                command=list(command),
                container=container,
                timeout_seconds=int(timeout_seconds or default_timeout),
                stdin=stdin,
            )
        except KubernetesAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=f"adapter unavailable: {exc}", summary="exec unavailable"
            )
        except KubernetesAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="exec failed")
        return MCPToolResult(
            ok=True,
            data=asdict(result),
            summary=(
                f"exec rc={result.returncode} stdout={len(result.stdout)}b "
                f"stderr={len(result.stderr)}b"
            ),
        )


# ---------------------------------------------------------------------------
# data.kubernetes.stream_pod_logs
# ---------------------------------------------------------------------------


class StreamPodLogsInput(BaseModel):
    namespace: str
    name: str
    container: str | None = None
    since_seconds: int | None = Field(default=None, ge=1, le=86400)
    tail_lines: int | None = Field(default=200, ge=1, le=50000)
    follow: bool = Field(default=False, description="Set false for a one-shot slice.")
    max_lines: int | None = Field(default=500, ge=1, le=50000)


@register_data_mcp_tool
class StreamPodLogsTool(DataMCPTool):
    name = "data.kubernetes.stream_pod_logs"
    description = (
        "Fetch a bounded slice of pod / container logs (read-only). For a "
        "true live tail, connect to the /cluster/pods/{ns}/{name}/logs/stream "
        "WebSocket route — this MCP tool returns a snapshot suitable for "
        "agent reasoning."
    )
    args_schema = StreamPodLogsInput
    category = "kubernetes"
    tags = ("kubernetes", "logs")
    required_scopes = ("cluster:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        name: str,
        container: str | None = None,
        since_seconds: int | None = None,
        tail_lines: int | None = 200,
        follow: bool = False,
        max_lines: int | None = 500,
    ) -> MCPToolResult:
        adapter = get_kubernetes_adapter()
        events: list[dict[str, Any]] = []
        try:
            it = adapter.stream_pod_logs(
                namespace=namespace,
                name=name,
                container=container,
                since_seconds=since_seconds,
                tail_lines=tail_lines,
                follow=bool(follow),
                max_lines=max_lines,
            )
            for ev in it:
                events.append(asdict(ev))
                if max_lines is not None and len(events) >= int(max_lines):
                    break
        except KubernetesAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=f"adapter unavailable: {exc}", summary="logs unavailable"
            )
        except KubernetesAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="logs failed")
        return MCPToolResult(
            ok=True,
            data={"namespace": namespace, "name": name, "events": events},
            rows_returned=len(events),
            summary=f"streamed {len(events)} log lines",
        )


# ---------------------------------------------------------------------------
# data.kubernetes.get_pod_archive
# ---------------------------------------------------------------------------


class GetPodArchiveInput(BaseModel):
    namespace: str
    name: str
    path: str = Field(..., description="Path inside the pod to tar+download.")
    container: str | None = None
    max_bytes: int = Field(
        default=10_000_000,
        ge=1,
        le=1_000_000_000,
        description="Hard cap on the returned tarball size (refuse anything larger).",
    )


@register_data_mcp_tool
class GetPodArchiveTool(DataMCPTool):
    name = "data.kubernetes.get_pod_archive"
    description = (
        "Download a tarball of a path inside a pod / container as base64. "
        "Refuses payloads larger than max_bytes to protect the agent context. "
        "Callers unpack via io.BytesIO + tarfile.open."
    )
    args_schema = GetPodArchiveInput
    category = "kubernetes"
    tags = ("kubernetes", "archive", "read")
    required_scopes = ("cluster:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        name: str,
        path: str,
        container: str | None = None,
        max_bytes: int = 10_000_000,
    ) -> MCPToolResult:
        adapter = get_kubernetes_adapter()
        try:
            payload = adapter.get_pod_archive(
                namespace=namespace, name=name, path=path, container=container
            )
        except KubernetesAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=f"adapter unavailable: {exc}", summary="archive unavailable"
            )
        except KubernetesAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="get_archive failed")
        if len(payload) > int(max_bytes):
            return MCPToolResult(
                ok=False,
                error=f"archive {len(payload)}b exceeds max_bytes={max_bytes}",
                summary="archive too large",
            )
        return MCPToolResult(
            ok=True,
            data={
                "namespace": namespace,
                "name": name,
                "path": path,
                "container": container,
                "bytes": len(payload),
                "tar_b64": base64.b64encode(payload).decode("ascii"),
            },
            summary=f"fetched {len(payload)}b tar",
        )


# ---------------------------------------------------------------------------
# data.kubernetes.put_pod_archive
# ---------------------------------------------------------------------------


class PutPodArchiveInput(BaseModel):
    namespace: str
    name: str
    path: str
    data_b64: str = Field(..., description="Base64-encoded tar bytes to extract at `path`.")
    container: str | None = None


@register_data_mcp_tool
class PutPodArchiveTool(DataMCPTool):
    name = "data.kubernetes.put_pod_archive"
    description = (
        "Inject a tarball (base64-encoded) into a path inside a pod / container. "
        "The adapter validates that the bytes are a parseable tar stream before "
        "pushing them to the container to prevent silent filesystem corruption."
    )
    args_schema = PutPodArchiveInput
    category = "kubernetes"
    tags = ("kubernetes", "archive", "write")
    required_scopes = ("cluster:write",)
    mutates = True

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str,
        name: str,
        path: str,
        data_b64: str,
        container: str | None = None,
    ) -> MCPToolResult:
        try:
            data = base64.b64decode(data_b64)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"invalid data_b64: {exc}", summary="bad payload"
            )
        adapter = get_kubernetes_adapter()
        try:
            res = adapter.put_pod_archive(
                namespace=namespace,
                name=name,
                path=path,
                data=data,
                container=container,
            )
        except KubernetesAdapterUnavailable as exc:
            return MCPToolResult(
                ok=False, error=f"adapter unavailable: {exc}", summary="archive unavailable"
            )
        except KubernetesAdapterError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="put_archive failed")
        return MCPToolResult(
            ok=True,
            data=res,
            summary=f"pushed {len(data)}b tar into {path}",
        )


__all__: list[str] = []
