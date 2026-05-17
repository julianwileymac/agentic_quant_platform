"""In-cluster / kubeconfig adapter using the official Kubernetes Python SDK.

Loaded when AQP runs inside a cluster (pod-internal `ServiceAccount`)
or has a local `KUBECONFIG`. The `kubernetes` Python dependency is
optional — when missing, :meth:`is_available` returns ``False`` so
routes degrade gracefully.

This adapter implements the operations AQP needs today
(``scale_deployment``, ``pod_logs``, ``apply_manifest``) plus the
Phase 1 pod-level surface (``exec_in_pod``, ``stream_pod_logs``,
``get_pod_archive``, ``put_pod_archive``, ``list_pods``). Adding
more in-cluster ops here is straightforward — call the relevant
``CoreV1Api`` / ``CustomObjectsApi`` method.

Critical implementation notes (the documented client bugs):

- ``read_namespaced_pod_log(follow=True)`` hangs on sparse log
  emission unless ``_preload_content=False`` AND the stream is
  consumed via :class:`kubernetes.watch.Watch().stream(...)`.
  :meth:`stream_pod_logs` enforces both.
- ``connect_get_namespaced_pod_exec`` requires
  :func:`kubernetes.stream.stream` to multiplex stdin/stdout/stderr
  over the WebSocket connection. Plain calls return a single mixed
  string with no exit code.
"""
from __future__ import annotations

import io
import logging
import tarfile
import time
from typing import Any, Iterator

from aqp.kubernetes.protocol import (
    KubernetesAdapter,
    KubernetesAdapterError,
    KubernetesAdapterUnavailable,
    PodExecResult,
    PodInfo,
    PodLogEvent,
)

logger = logging.getLogger(__name__)


class InClusterAdapter(KubernetesAdapter):
    """Direct K8s API access via the kubernetes-client SDK."""

    adapter_kind = "in_cluster"
    adapter_alias = "InClusterAdapter"

    def __init__(self) -> None:
        self._loaded = False
        self._k8s_module = None
        try:
            self._load_config()
        except Exception as exc:  # noqa: BLE001
            logger.debug("InClusterAdapter unavailable: %s", exc)

    def _load_config(self) -> None:
        try:
            import kubernetes as k8s  # type: ignore
        except ImportError:
            self._loaded = False
            return
        try:
            k8s.config.load_incluster_config()
            self._loaded = True
            self._k8s_module = k8s
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            k8s.config.load_kube_config()
            self._loaded = True
            self._k8s_module = k8s
        except Exception as exc:  # noqa: BLE001
            logger.debug("kubeconfig load failed: %s", exc)
            self._loaded = False

    def is_available(self) -> bool:
        return bool(self._loaded)

    # ------------------------------------------------------------------
    # Generic ops (the ones AQP needs today)
    # ------------------------------------------------------------------

    def scale_deployment(
        self, *, namespace: str, name: str, replicas: int
    ) -> dict[str, Any]:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            apps_v1 = self._k8s_module.client.AppsV1Api()  # type: ignore[union-attr]
            scale = apps_v1.read_namespaced_deployment_scale(name=name, namespace=namespace)
            scale.spec.replicas = int(replicas)
            updated = apps_v1.replace_namespaced_deployment_scale(
                name=name, namespace=namespace, body=scale
            )
            return {
                "name": name,
                "namespace": namespace,
                "replicas": int(getattr(updated.spec, "replicas", replicas)),
            }
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"scale_deployment failed: {exc}") from exc

    def pod_logs(
        self, *, namespace: str, name: str, tail_lines: int = 200
    ) -> str:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            core_v1 = self._k8s_module.client.CoreV1Api()  # type: ignore[union-attr]
            return str(
                core_v1.read_namespaced_pod_log(
                    name=name,
                    namespace=namespace,
                    tail_lines=int(tail_lines),
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"pod_logs failed: {exc}") from exc

    def apply_manifest(
        self, *, manifest: dict[str, Any], namespace: str | None = None
    ) -> dict[str, Any]:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            from kubernetes.utils import create_from_dict  # type: ignore

            api_client = self._k8s_module.client.ApiClient()  # type: ignore[union-attr]
            results = create_from_dict(api_client, manifest, namespace=namespace)
            return {
                "applied": True,
                "kinds": [str(r.__class__.__name__) for r in results],
            }
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"apply_manifest failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Phase 1 — pod-level ops
    # ------------------------------------------------------------------

    def list_pods(
        self,
        *,
        namespace: str,
        label_selector: str | None = None,
    ) -> list[PodInfo]:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            core_v1 = self._k8s_module.client.CoreV1Api()  # type: ignore[union-attr]
            kwargs: dict[str, Any] = {"namespace": namespace}
            if label_selector:
                kwargs["label_selector"] = label_selector
            resp = core_v1.list_namespaced_pod(**kwargs)
            pods: list[PodInfo] = []
            for item in getattr(resp, "items", []) or []:
                meta = getattr(item, "metadata", None)
                status = getattr(item, "status", None)
                spec = getattr(item, "spec", None)
                started_at = ""
                try:
                    raw_start = getattr(status, "start_time", None) if status else None
                    if raw_start is not None:
                        started_at = raw_start.isoformat()
                except Exception:  # noqa: BLE001
                    pass
                containers: list[str] = []
                try:
                    for c in getattr(spec, "containers", []) or []:
                        if getattr(c, "name", None):
                            containers.append(str(c.name))
                except Exception:  # noqa: BLE001
                    pass
                labels: dict[str, str] = {}
                try:
                    raw_labels = getattr(meta, "labels", None) or {}
                    labels = {str(k): str(v) for k, v in raw_labels.items()}
                except Exception:  # noqa: BLE001
                    pass
                pods.append(
                    PodInfo(
                        namespace=str(getattr(meta, "namespace", namespace) or namespace),
                        name=str(getattr(meta, "name", "")),
                        phase=str(getattr(status, "phase", "") or ""),
                        node=str(getattr(spec, "node_name", "") or ""),
                        pod_ip=str(getattr(status, "pod_ip", "") or ""),
                        started_at=started_at,
                        containers=containers,
                        labels=labels,
                    )
                )
            return pods
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"list_pods failed: {exc}") from exc

    def exec_in_pod(
        self,
        *,
        namespace: str,
        name: str,
        command: list[str],
        container: str | None = None,
        timeout_seconds: int = 60,
        stdin: bytes | None = None,
    ) -> PodExecResult:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            from kubernetes.stream import stream as _stream  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"kubernetes.stream unavailable: {exc}") from exc

        started = time.time()
        core_v1 = self._k8s_module.client.CoreV1Api()  # type: ignore[union-attr]
        kwargs: dict[str, Any] = {
            "command": list(command),
            "stderr": True,
            "stdin": stdin is not None,
            "stdout": True,
            "tty": False,
            "_preload_content": False,
        }
        if container:
            kwargs["container"] = container
        try:
            resp = _stream(
                core_v1.connect_get_namespaced_pod_exec,
                name,
                namespace,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"exec_in_pod failed to start: {exc}") from exc

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        deadline = started + max(1, int(timeout_seconds))
        try:
            if stdin is not None:
                try:
                    resp.write_stdin(stdin.decode("utf-8", errors="replace"))
                except Exception:  # noqa: BLE001
                    logger.debug("exec_in_pod write_stdin failed", exc_info=True)
            while resp.is_open():
                if time.time() > deadline:
                    logger.warning(
                        "exec_in_pod timeout after %ss for %s/%s",
                        timeout_seconds,
                        namespace,
                        name,
                    )
                    break
                resp.update(timeout=1)
                if resp.peek_stdout():
                    stdout_chunks.append(resp.read_stdout())
                if resp.peek_stderr():
                    stderr_chunks.append(resp.read_stderr())
            # Drain remaining buffers after the channel closes.
            if resp.peek_stdout():
                stdout_chunks.append(resp.read_stdout())
            if resp.peek_stderr():
                stderr_chunks.append(resp.read_stderr())
            returncode = getattr(resp, "returncode", None)
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass

        elapsed_ms = (time.time() - started) * 1000.0
        return PodExecResult(
            namespace=namespace,
            name=name,
            container=container,
            command=list(command),
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            returncode=int(returncode) if isinstance(returncode, int) else None,
            elapsed_ms=float(round(elapsed_ms, 3)),
        )

    def stream_pod_logs(
        self,
        *,
        namespace: str,
        name: str,
        container: str | None = None,
        since_seconds: int | None = None,
        tail_lines: int | None = None,
        follow: bool = True,
        max_lines: int | None = None,
    ) -> Iterator[PodLogEvent]:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            core_v1 = self._k8s_module.client.CoreV1Api()  # type: ignore[union-attr]
            watch_mod = self._k8s_module.watch  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"watch unavailable: {exc}") from exc

        watcher = watch_mod.Watch()
        kwargs: dict[str, Any] = {
            "name": name,
            "namespace": namespace,
            "follow": bool(follow),
            "_preload_content": False,
            "timestamps": True,
        }
        if container:
            kwargs["container"] = container
        if since_seconds is not None:
            kwargs["since_seconds"] = int(since_seconds)
        if tail_lines is not None:
            kwargs["tail_lines"] = int(tail_lines)

        emitted = 0
        try:
            for raw_line in watcher.stream(core_v1.read_namespaced_pod_log, **kwargs):
                # The watch helper yields decoded strings even with
                # ``_preload_content=False`` because we asked for
                # ``timestamps=True`` (text mode). Be defensive in case
                # a future client returns bytes.
                line = raw_line.decode("utf-8", errors="replace") if isinstance(raw_line, (bytes, bytearray)) else str(raw_line)
                ts = ""
                body = line
                # Kubernetes prepends an RFC3339 timestamp + space when
                # ``timestamps=True``. Split once so consumers can
                # render them separately without losing whitespace.
                if line and line[0].isdigit() and " " in line:
                    head, _, rest = line.partition(" ")
                    if "T" in head and (head.endswith("Z") or "+" in head[10:] or "-" in head[10:]):
                        ts = head
                        body = rest
                yield PodLogEvent(
                    namespace=namespace,
                    name=name,
                    container=container,
                    line=body,
                    timestamp=ts,
                )
                emitted += 1
                if max_lines is not None and emitted >= int(max_lines):
                    break
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"stream_pod_logs failed: {exc}") from exc
        finally:
            try:
                watcher.stop()
            except Exception:  # noqa: BLE001
                pass

    def get_pod_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        container: str | None = None,
    ) -> bytes:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            from kubernetes.stream import stream as _stream  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"kubernetes.stream unavailable: {exc}") from exc

        core_v1 = self._k8s_module.client.CoreV1Api()  # type: ignore[union-attr]
        kwargs: dict[str, Any] = {
            "command": ["tar", "cf", "-", path],
            "stderr": True,
            "stdin": False,
            "stdout": True,
            "tty": False,
            "_preload_content": False,
        }
        if container:
            kwargs["container"] = container
        try:
            resp = _stream(
                core_v1.connect_get_namespaced_pod_exec,
                name,
                namespace,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"get_pod_archive failed to start: {exc}") from exc

        chunks: list[bytes] = []
        try:
            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    payload = resp.read_stdout()
                    if isinstance(payload, str):
                        chunks.append(payload.encode("latin-1", errors="replace"))
                    else:
                        chunks.append(bytes(payload))
                if resp.peek_stderr():
                    err = resp.read_stderr()
                    logger.debug("get_pod_archive stderr: %s", err)
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
        return b"".join(chunks)

    def put_pod_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        data: bytes,
        container: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_available():
            raise KubernetesAdapterUnavailable("in-cluster client unavailable")
        try:
            from kubernetes.stream import stream as _stream  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"kubernetes.stream unavailable: {exc}") from exc

        core_v1 = self._k8s_module.client.CoreV1Api()  # type: ignore[union-attr]
        kwargs: dict[str, Any] = {
            "command": ["tar", "xmf", "-", "-C", path],
            "stderr": True,
            "stdin": True,
            "stdout": True,
            "tty": False,
            "_preload_content": False,
        }
        if container:
            kwargs["container"] = container
        try:
            resp = _stream(
                core_v1.connect_get_namespaced_pod_exec,
                name,
                namespace,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"put_pod_archive failed to start: {exc}") from exc

        bytes_written = 0
        stderr_chunks: list[str] = []
        try:
            # Verify we got a valid tar stream before shoving raw bytes
            # into the pod (defensive — broken tarballs corrupt the pod
            # filesystem silently otherwise).
            try:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r|"):
                    pass
            except Exception as exc:  # noqa: BLE001
                raise KubernetesAdapterError(
                    f"put_pod_archive received invalid tar bytes: {exc}"
                ) from exc
            try:
                resp.write_stdin(data.decode("latin-1", errors="replace"))
                bytes_written = len(data)
            except Exception as exc:  # noqa: BLE001
                raise KubernetesAdapterError(f"put_pod_archive write failed: {exc}") from exc
            # Give the remote ``tar xmf`` a moment to drain.
            for _ in range(60):
                if not resp.is_open():
                    break
                resp.update(timeout=1)
                if resp.peek_stderr():
                    stderr_chunks.append(resp.read_stderr())
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass

        return {
            "namespace": namespace,
            "name": name,
            "path": path,
            "container": container,
            "bytes_written": bytes_written,
            "stderr": "".join(stderr_chunks),
        }


__all__ = ["InClusterAdapter"]
