"""Value types returned by :class:`aqp_platform_core.kubernetes.KubernetesAdapter`.

Pure dataclasses, JSON-serialisable, no FastAPI / Pydantic
dependency. Stable wire format — adding fields is fine, renaming or
removing is a major-version bump.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PodExecResult:
    """Result of an in-pod or in-container command execution.

    ``returncode`` may be ``None`` when the underlying transport does
    not surface an explicit exit code (best-effort for Docker SDK
    streaming). Routes / MCP tools should treat ``None`` as "completed
    without numeric code" and inspect ``stderr`` for failure signal.
    """

    namespace: str
    name: str
    container: str | None
    command: list[str]
    stdout: str
    stderr: str
    returncode: int | None
    elapsed_ms: float | None = None


@dataclass(slots=True)
class PodInfo:
    """Compact pod descriptor returned by :meth:`KubernetesAdapter.list_pods`.

    Adapters set fields they cannot resolve to ``""`` / ``None`` —
    routes pass the dict through to the frontend without inventing
    missing values.
    """

    namespace: str
    name: str
    phase: str = ""
    node: str = ""
    pod_ip: str = ""
    started_at: str = ""
    containers: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PodLogEvent:
    """Single frame emitted by :meth:`KubernetesAdapter.stream_pod_logs`.

    Frames are produced by the adapter; the WebSocket route adapts
    them to the canonical ``{task_id, stage, message, timestamp,
    **extras}`` payload shape required by AGENTS rule 4.
    """

    namespace: str
    name: str
    container: str | None
    line: str
    timestamp: str = ""
    source: str = "stdout"  # "stdout" | "stderr"


__all__ = ["PodExecResult", "PodInfo", "PodLogEvent"]
