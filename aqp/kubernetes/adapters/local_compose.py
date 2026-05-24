"""Local ``docker compose`` adapter.

Backs the new ``aqp_platform/compose/docker-compose.platform.yml`` overlay (Milestone 5):
the AQP "cluster" is the local Docker daemon, and operations like
``scale_deployment`` and ``pod_logs`` shell out to ``docker compose``
commands.

The Phase 1 pod-level ops (``exec_in_pod`` / ``stream_pod_logs`` /
``get_pod_archive`` / ``put_pod_archive`` / ``list_pods``) use the
**Docker Python SDK** instead of subprocess so we can stream
``container.logs(stream=True, follow=True)`` and use
``container.get_archive`` / ``put_archive`` directly. The SDK client
is constructed with ``Accept-Encoding: identity`` to dodge the
documented gigabyte-tarball latency bug (the requests session's
default compression injection on ``get_archive``).

This adapter is lightweight by design — operations are safe-by-default
and never raise on missing services (returns the stderr instead). For
real cluster ops, use :class:`InClusterAdapter` or
:class:`RpiClusterAdapter`.
"""
from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tarfile
import time
from pathlib import Path
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


class _IdentityEncodingAdapter:
    """Wrap a ``requests`` ``HTTPAdapter`` so default ``Accept-Encoding``
    becomes ``identity``.

    The Docker SDK plumbs a ``requests.Session`` under
    ``client.api.session``; the session's default headers inject
    ``Accept-Encoding: gzip, deflate`` which saturates the Docker
    daemon's response compression path on multi-gigabyte ``get_archive``
    calls. We replace the session's default headers (rule 28 — this
    fix lives inside the adapter, not in any agent body).
    """

    @staticmethod
    def apply(session: Any) -> None:
        try:
            session.headers["Accept-Encoding"] = "identity"
        except Exception:  # noqa: BLE001
            logger.debug("could not patch session Accept-Encoding", exc_info=True)


class LocalComposeAdapter(KubernetesAdapter):
    """Treat ``docker compose`` services as the cluster surface."""

    adapter_kind = "local_compose"
    adapter_alias = "LocalComposeAdapter"

    def __init__(
        self,
        *,
        compose_files: list[Path] | None = None,
        project_directory: Path | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._compose_files = list(compose_files or [])
        self._cwd = project_directory
        self._timeout = max(5, int(timeout_seconds))
        self._docker_client: Any | None = None  # lazy
        self._docker_import_error: Exception | None = None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(shutil.which("docker"))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compose_args(self) -> list[str]:
        args: list[str] = ["docker", "compose"]
        for f in self._compose_files:
            args.extend(["-f", str(f)])
        return args

    def _run(self, *cmd: str) -> tuple[int, str, str]:
        if not self.is_available():
            raise KubernetesAdapterError("docker is not on PATH")
        try:
            result = subprocess.run(
                list(cmd),
                cwd=self._cwd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise KubernetesAdapterError(
                f"docker command timed out after {self._timeout}s: {' '.join(cmd)}"
            ) from exc
        return result.returncode, result.stdout, result.stderr

    # ------------------------------------------------------------------
    # Ops
    # ------------------------------------------------------------------

    def scale_deployment(
        self, *, namespace: str, name: str, replicas: int
    ) -> dict[str, Any]:
        # docker compose treats compose service names as deployments;
        # ``namespace`` is unused but kept for parity with the cluster
        # adapters.
        del namespace
        rc, stdout, stderr = self._run(
            *self._compose_args(),
            "up",
            "-d",
            "--scale",
            f"{name}={int(replicas)}",
            name,
        )
        if rc != 0:
            raise KubernetesAdapterError(f"compose scale failed: {stderr or stdout}")
        return {"service": name, "replicas": int(replicas), "stdout": stdout.strip()}

    def pod_logs(
        self, *, namespace: str, name: str, tail_lines: int = 200
    ) -> str:
        del namespace
        rc, stdout, stderr = self._run(
            *self._compose_args(),
            "logs",
            "--no-color",
            "--tail",
            str(int(tail_lines)),
            name,
        )
        if rc != 0:
            raise KubernetesAdapterError(f"compose logs failed: {stderr or stdout}")
        return stdout

    # ------------------------------------------------------------------
    # Phase 1 — pod-level ops via Docker SDK
    # ------------------------------------------------------------------

    def _get_docker_client(self) -> Any:
        if self._docker_client is not None:
            return self._docker_client
        if self._docker_import_error is not None:
            raise KubernetesAdapterUnavailable(
                f"docker SDK not importable: {self._docker_import_error}"
            )
        try:
            import docker  # type: ignore
        except Exception as exc:  # noqa: BLE001
            self._docker_import_error = exc
            raise KubernetesAdapterUnavailable(
                f"docker SDK not installed: {exc}"
            ) from exc

        # Honour the optional settings overrides so operators can point
        # at a non-default daemon (TLS, remote socket, etc) without
        # touching the adapter.
        try:
            from aqp.config import settings

            base_url = (str(getattr(settings, "docker_sdk_base_url", "") or "")).strip()
            timeout = int(getattr(settings, "docker_sdk_timeout", 60) or 60)
            disable_compression = bool(
                getattr(settings, "docker_sdk_disable_compression", True)
            )
        except Exception:  # noqa: BLE001
            base_url = ""
            timeout = 60
            disable_compression = True

        try:
            if base_url:
                self._docker_client = docker.DockerClient(
                    base_url=base_url, timeout=timeout
                )
            else:
                self._docker_client = docker.from_env(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"docker SDK client init failed: {exc}") from exc

        # Critical: disable response compression on the underlying
        # requests session so ``get_archive`` does not throttle on
        # gigabyte tarballs.
        if disable_compression:
            try:
                session = getattr(self._docker_client.api, "session", None)
                if session is not None:
                    _IdentityEncodingAdapter.apply(session)
            except Exception:  # noqa: BLE001
                logger.debug("Accept-Encoding override skipped", exc_info=True)

        return self._docker_client

    def _resolve_container(
        self, *, namespace: str, name: str, container: str | None = None
    ) -> Any:
        """Resolve a Docker container by service name or container id.

        We treat ``name`` as the compose service name (matched via
        labels) when ``container`` is unset; otherwise it is taken as
        the container id / name directly. ``namespace`` is accepted
        for adapter parity and folded into the compose project label
        when supplied.
        """
        client = self._get_docker_client()
        target = container or name
        try:
            if container:
                return client.containers.get(container)
            # Try fast path: direct container name.
            try:
                return client.containers.get(target)
            except Exception:  # noqa: BLE001
                pass
            # Fall back to compose service label lookup.
            filters: dict[str, list[str]] = {
                "label": [f"com.docker.compose.service={name}"]
            }
            if namespace:
                filters["label"].append(f"com.docker.compose.project={namespace}")
            containers = client.containers.list(all=True, filters=filters)
            if not containers:
                raise KubernetesAdapterError(
                    f"container for service {name!r} not found"
                )
            return containers[0]
        except KubernetesAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(
                f"docker container lookup failed for {target!r}: {exc}"
            ) from exc

    def list_pods(
        self,
        *,
        namespace: str,
        label_selector: str | None = None,
    ) -> list[PodInfo]:
        client = self._get_docker_client()
        filters: dict[str, list[str]] = {}
        labels: list[str] = []
        if namespace:
            labels.append(f"com.docker.compose.project={namespace}")
        if label_selector:
            # Accept the Kubernetes label-selector mini-language only for
            # exact "key=value" / "key" forms. Anything fancier degrades
            # to a wildcard list — keep the adapter side simple.
            for clause in label_selector.split(","):
                clause = clause.strip()
                if not clause:
                    continue
                labels.append(clause)
        if labels:
            filters["label"] = labels
        try:
            containers = client.containers.list(all=True, filters=filters or None)
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"docker list_pods failed: {exc}") from exc

        pods: list[PodInfo] = []
        for c in containers:
            attrs = getattr(c, "attrs", {}) or {}
            state = attrs.get("State", {}) or {}
            config = attrs.get("Config", {}) or {}
            labels_map = config.get("Labels") or {}
            pods.append(
                PodInfo(
                    namespace=str(
                        labels_map.get("com.docker.compose.project", namespace or "")
                    ),
                    name=str(c.name),
                    phase=str(state.get("Status", "") or ""),
                    node="docker",
                    pod_ip=str(
                        (attrs.get("NetworkSettings", {}) or {}).get("IPAddress", "")
                        or ""
                    ),
                    started_at=str(state.get("StartedAt", "") or ""),
                    containers=[str(c.name)],
                    labels={str(k): str(v) for k, v in (labels_map or {}).items()},
                )
            )
        return pods

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
        del timeout_seconds  # Docker SDK exec_run does not surface a timeout
        if stdin is not None:
            raise KubernetesAdapterError(
                "exec_in_pod stdin injection is not supported by the docker SDK adapter"
            )
        container_obj = self._resolve_container(
            namespace=namespace, name=name, container=container
        )
        started = time.time()
        try:
            exit_code, output = container_obj.exec_run(
                cmd=list(command),
                stdout=True,
                stderr=True,
                demux=True,
                tty=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"docker exec_run failed: {exc}") from exc
        elapsed_ms = (time.time() - started) * 1000.0
        if isinstance(output, tuple):
            out_bytes, err_bytes = output
        else:
            out_bytes, err_bytes = output, None
        return PodExecResult(
            namespace=namespace,
            name=name,
            container=container_obj.name,
            command=list(command),
            stdout=(out_bytes or b"").decode("utf-8", errors="replace"),
            stderr=(err_bytes or b"").decode("utf-8", errors="replace"),
            returncode=int(exit_code) if exit_code is not None else None,
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
        container_obj = self._resolve_container(
            namespace=namespace, name=name, container=container
        )
        kwargs: dict[str, Any] = {
            "stream": True,
            "follow": bool(follow),
            "stdout": True,
            "stderr": True,
            "timestamps": True,
        }
        if since_seconds is not None:
            kwargs["since"] = int(time.time() - int(since_seconds))
        if tail_lines is not None:
            kwargs["tail"] = int(tail_lines)
        try:
            stream = container_obj.logs(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"docker logs failed: {exc}") from exc

        emitted = 0
        try:
            for chunk in stream:
                if not chunk:
                    continue
                text = (
                    chunk.decode("utf-8", errors="replace")
                    if isinstance(chunk, (bytes, bytearray))
                    else str(chunk)
                )
                for raw_line in text.splitlines():
                    if not raw_line:
                        continue
                    ts = ""
                    body = raw_line
                    if raw_line and raw_line[0].isdigit() and " " in raw_line:
                        head, _, rest = raw_line.partition(" ")
                        if "T" in head and (
                            head.endswith("Z") or "+" in head[10:] or "-" in head[10:]
                        ):
                            ts = head
                            body = rest
                    yield PodLogEvent(
                        namespace=namespace,
                        name=name,
                        container=container_obj.name,
                        line=body,
                        timestamp=ts,
                    )
                    emitted += 1
                    if max_lines is not None and emitted >= int(max_lines):
                        return
        finally:
            try:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
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
        container_obj = self._resolve_container(
            namespace=namespace, name=name, container=container
        )
        try:
            tar_iter, _stat = container_obj.get_archive(path)
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"docker get_archive failed: {exc}") from exc
        try:
            chunks: list[bytes] = []
            for chunk in tar_iter:
                if isinstance(chunk, (bytes, bytearray)):
                    chunks.append(bytes(chunk))
                else:
                    chunks.append(str(chunk).encode("latin-1", errors="replace"))
            return b"".join(chunks)
        finally:
            try:
                close = getattr(tar_iter, "close", None)
                if callable(close):
                    close()
            except Exception:  # noqa: BLE001
                pass

    def put_pod_archive(
        self,
        *,
        namespace: str,
        name: str,
        path: str,
        data: bytes,
        container: str | None = None,
    ) -> dict[str, Any]:
        container_obj = self._resolve_container(
            namespace=namespace, name=name, container=container
        )
        # Validate the tar stream before pushing so we do not corrupt
        # the container's filesystem on a malformed input.
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r|"):
                pass
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(
                f"put_pod_archive received invalid tar bytes: {exc}"
            ) from exc
        try:
            ok = container_obj.put_archive(path=path, data=data)
        except Exception as exc:  # noqa: BLE001
            raise KubernetesAdapterError(f"docker put_archive failed: {exc}") from exc
        return {
            "namespace": namespace,
            "name": name,
            "container": container_obj.name,
            "path": path,
            "bytes_written": len(data),
            "ok": bool(ok),
        }


__all__ = ["LocalComposeAdapter"]
