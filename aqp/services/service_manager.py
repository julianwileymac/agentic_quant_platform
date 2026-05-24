"""Unified local service management for AQP-managed data services."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Literal

import httpx

from aqp.config import settings
from aqp.data import iceberg_catalog
from aqp.data.entities.graph_store import get_graph_store
from aqp.services.airbyte_client import AirbyteClient, AirbyteClientError
from aqp.services.iceberg_bootstrap import IcebergBootstrapManager, credentials_file
from aqp.services.polaris_client import PolarisClientError
from aqp.services.superset_client import SupersetClient
from aqp.services.trino_client import TrinoClient, TrinoClientError
from aqp.services.trino_probe import probe_trino_coordinator

logger = logging.getLogger(__name__)

ServiceName = Literal[
    "trino",
    "polaris",
    "iceberg",
    "superset",
    "airbyte",
    "dagster",
    "neo4j",
    "dask",
    "ray",
    "minio",
]
ActionName = Literal["start", "stop", "restart"]

SERVICE_NAMES: tuple[str, ...] = (
    "trino",
    "polaris",
    "iceberg",
    "superset",
    "airbyte",
    "dagster",
    "neo4j",
    "dask",
    "ray",
    "minio",
)

COMPOSE_SERVICE_MAP = {
    "trino": "trino",
    "polaris": "polaris",
    "superset": "superset",
    "airbyte": "airbyte-server",
    "dagster": "dagster-webserver",
    "neo4j": "neo4j",
    "dask": "dask-scheduler",
    "ray": "ray-head",
    "minio": "minio",
}


def config_snapshot() -> dict[str, Any]:
    return {
        "service_control_enabled": settings.service_control_enabled,
        "graph_store": settings.graph_store,
        "neo4j_uri": settings.neo4j_uri,
        "trino_uri": settings.trino_uri,
        "trino_http_url": settings.trino_http_url or None,
        "polaris_base_url": settings.polaris_base_url,
        "iceberg_rest_uri": settings.iceberg_rest_uri or None,
        "superset_base_url": settings.superset_base_url,
        "superset_public_url": settings.superset_public_url,
        "airbyte_enabled": settings.airbyte_enabled,
        "airbyte_base_url": settings.airbyte_base_url,
        "dagster_graphql_url": settings.dagster_graphql_url or None,
        "dagster_webserver_url": settings.dagster_webserver_url or None,
        "dask_scheduler_address": settings.dask_scheduler_address or None,
        "dask_n_workers": settings.dask_n_workers,
        "dask_threads_per_worker": settings.dask_threads_per_worker,
        "ray_address": settings.ray_address or None,
        "ray_init_kwargs": settings.ray_init_kwargs,
        "s3_endpoint_url": settings.s3_endpoint_url or None,
        "minio_endpoint_url": settings.minio_endpoint_url or None,
        "minio_artifacts_bucket": settings.minio_artifacts_bucket,
        "minio_datasets_bucket": settings.minio_datasets_bucket,
    }


def health() -> dict[str, Any]:
    services = {name: service_health(name) for name in SERVICE_NAMES}
    return {
        "ok": all(payload.get("ok") for payload in services.values()),
        "services": services,
        "config": config_snapshot(),
    }


def service_health(name: str) -> dict[str, Any]:
    if name == "trino":
        return _trino_health()
    if name == "polaris":
        return _polaris_health()
    if name == "iceberg":
        return _iceberg_health()
    if name == "superset":
        return _superset_health()
    if name == "airbyte":
        return _airbyte_health()
    if name == "dagster":
        return _dagster_health()
    if name == "neo4j":
        return _neo4j_health()
    if name == "dask":
        return _dask_health()
    if name == "ray":
        return _ray_health()
    if name == "minio":
        return _minio_health()
    return {"ok": False, "service": name, "error": "unknown service"}


def service_logs(name: str, *, lines: int | None = None) -> dict[str, Any]:
    compose = COMPOSE_SERVICE_MAP.get(name)
    if not compose:
        return {"ok": False, "service": name, "error": "unknown service"}
    if not settings.service_control_enabled:
        return {
            "ok": False,
            "service": name,
            "enabled": False,
            "error": "AQP_SERVICE_CONTROL_ENABLED is false",
        }
    line_count = max(1, min(int(lines or settings.service_log_tail_lines or 200), 2000))
    result = _compose(["logs", "--tail", str(line_count), compose])
    if not result.get("returncode") == 0 and _compose_unavailable(result):
        container_names = _container_names_for_service(name)
        payloads = [_docker_logs(container, line_count) for container in container_names]
        ok = all(payload.get("ok") for payload in payloads)
        return {
            "ok": ok,
            "service": name,
            "containers": payloads,
            "stdout": "\n".join(str(p.get("stdout") or "") for p in payloads),
            "stderr": "\n".join(str(p.get("stderr") or "") for p in payloads),
        }
    return {"ok": result["returncode"] == 0, "service": name, **result}


def service_action(name: str, action: ActionName) -> dict[str, Any]:
    compose = COMPOSE_SERVICE_MAP.get(name)
    if not compose:
        return {"ok": False, "service": name, "error": "unknown service"}
    if not settings.service_control_enabled:
        return {
            "ok": False,
            "service": name,
            "action": action,
            "enabled": False,
            "error": "AQP_SERVICE_CONTROL_ENABLED is false",
        }
    if name == "dask":
        args = {
            "start": ["up", "-d", "dask-scheduler", "dask-worker"],
            "stop": ["stop", "dask-worker", "dask-scheduler"],
            "restart": ["restart", "dask-scheduler", "dask-worker"],
        }[action]
    else:
        args = {
            "start": ["up", "-d", compose],
            "stop": ["stop", compose],
            "restart": ["restart", compose],
        }[action]
    result = _compose(args)
    if not result.get("returncode") == 0 and _compose_unavailable(result):
        container_names = _container_names_for_service(name)
        payloads = [_docker_action(container, action) for container in container_names]
        ok = all(payload.get("ok") for payload in payloads)
        return {
            "ok": ok,
            "service": name,
            "action": action,
            "containers": payloads,
            "stdout": "",
            "stderr": "\n".join(str(p.get("error") or "") for p in payloads if p.get("error")),
        }
    return {"ok": result["returncode"] == 0, "service": name, "action": action, **result}


def _trino_health() -> dict[str, Any]:
    info = probe_trino_coordinator(timeout_seconds=5.0)
    payload: dict[str, Any] = {"service": "trino", **info}
    payload.setdefault("query_ok", False)
    payload.setdefault("iceberg_catalog_ok", False)
    payload.setdefault("catalogs", [])
    payload.setdefault("query_error", None)
    if not info.get("ok"):
        return payload
    try:
        with TrinoClient() as client:
            verification = client.verify(iceberg_catalog=settings.trino_catalog or "iceberg")
        payload.update(
            {
                "query_ok": verification.query_ok,
                "iceberg_catalog_ok": verification.iceberg_catalog_ok,
                "catalogs": verification.catalogs,
                "iceberg_schemas": verification.iceberg_schemas,
                "query_error": verification.error,
                "node_id": verification.node_id or info.get("node_id"),
                "node_version": verification.node_version or info.get("node_version"),
            }
        )
        if not verification.query_ok:
            payload["ok"] = False
            payload["error"] = verification.error or info.get("error")
    except TrinoClientError as exc:
        payload["ok"] = False
        payload["error"] = str(exc)
        payload["query_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("trino verification failed: %s", exc)
        payload["ok"] = False
        payload["error"] = str(exc)
        payload["query_error"] = str(exc)
    return payload


def _polaris_health() -> dict[str, Any]:
    url = (settings.polaris_base_url or "").rstrip("/")
    if not url:
        return {"ok": False, "service": "polaris", "error": "AQP_POLARIS_BASE_URL is empty"}
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
        return {
            "ok": response.status_code < 500,
            "service": "polaris",
            "url": url,
            "status_code": response.status_code,
            "error": None if response.status_code < 500 else response.text[:300],
        }
    except httpx.HTTPError as exc:
        return {"ok": False, "service": "polaris", "url": url, "error": str(exc)}


def _iceberg_health() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "service": "iceberg",
        "ok": False,
        "catalog_present": False,
        "principal_present": False,
        "principal_role_present": False,
        "catalog_role_present": False,
        "credentials_persisted": credentials_file().exists(),
        "credentials_file": str(credentials_file()),
        "bootstrap_required": True,
        "table_count": 0,
        "sample_tables": [],
        "polaris_reachable": False,
        "error": None,
    }
    try:
        with IcebergBootstrapManager() as manager:
            status = manager.status()
    except PolarisClientError as exc:
        payload["error"] = str(exc)
        return payload
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
        return payload
    payload.update(
        {
            "catalog": status["catalog"],
            "principal": status["principal"],
            "principal_role": status["principal_role"],
            "catalog_role": status["catalog_role"],
            "polaris_reachable": status.get("polaris_reachable", False),
            "catalog_present": status.get("catalog_present", False),
            "principal_present": status.get("principal_present", False),
            "principal_role_present": status.get("principal_role_present", False),
            "catalog_role_present": status.get("catalog_role_present", False),
        }
    )
    if status.get("error"):
        payload["error"] = status["error"]
    bootstrap_required = not all(
        [
            payload["catalog_present"],
            payload["principal_present"],
            payload["principal_role_present"],
            payload["catalog_role_present"],
        ]
    )
    payload["bootstrap_required"] = bootstrap_required
    if bootstrap_required:
        payload["detail"] = (
            "Polaris bootstrap incomplete; call POST /service-manager/iceberg/bootstrap"
        )
        return payload
    try:
        tables = iceberg_catalog.list_tables()
        payload["ok"] = True
        payload["table_count"] = len(tables)
        payload["sample_tables"] = tables[:10]
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
    return payload


def iceberg_status() -> dict[str, Any]:
    with IcebergBootstrapManager() as manager:
        return manager.status()


def iceberg_bootstrap() -> dict[str, Any]:
    with IcebergBootstrapManager() as manager:
        report = manager.bootstrap()
    return report.to_dict()


def trino_verify() -> dict[str, Any]:
    with TrinoClient() as client:
        verification = client.verify(iceberg_catalog=settings.trino_catalog or "iceberg")
    return verification.to_dict()


def trino_queries(*, limit: int = 50) -> dict[str, Any]:
    with TrinoClient() as client:
        rows = client.query_history(limit=limit)
    return {"queries": [row.to_dict() for row in rows], "count": len(rows)}


def trino_query(statement: str, *, catalog: str | None = None, schema: str | None = None) -> dict[str, Any]:
    with TrinoClient() as client:
        result = client.query(statement, catalog=catalog, schema=schema)
    return result.to_dict()


def _superset_health() -> dict[str, Any]:
    try:
        with SupersetClient() as client:
            payload = client.health()
        return {"ok": True, "service": "superset", "payload": payload}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "service": "superset", "error": str(exc)}


def _airbyte_health() -> dict[str, Any]:
    if not settings.airbyte_enabled:
        return {
            "ok": False,
            "service": "airbyte",
            "enabled": False,
            "error": "AQP_AIRBYTE_ENABLED is false",
        }
    try:
        payload = AirbyteClient().health()
        ok = payload.get("available") if isinstance(payload.get("available"), bool) else not payload.get("error")
        return {"ok": bool(ok), "service": "airbyte", "payload": payload}
    except AirbyteClientError as exc:
        return {"ok": False, "service": "airbyte", "error": str(exc)}


def _dagster_graphql_url() -> str | None:
    url = settings.dagster_graphql_url or settings.dagster_webserver_url
    if not url:
        return None
    return url if url.endswith("/graphql") else url.rstrip("/") + "/graphql"


def _dagster_health() -> dict[str, Any]:
    url = _dagster_graphql_url()
    if not url:
        return {
            "ok": False,
            "service": "dagster",
            "error": "AQP_DAGSTER_GRAPHQL_URL/AQP_DAGSTER_WEBSERVER_URL is empty",
            "code_location": settings.dagster_code_location,
        }
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(url, json={"query": "query { version }"})
            response.raise_for_status()
        return {"ok": True, "service": "dagster", "graphql_url": url, "payload": response.json()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "service": "dagster", "graphql_url": url, "error": str(exc)}


def _neo4j_health() -> dict[str, Any]:
    store = get_graph_store()
    if store is None:
        return {"ok": False, "service": "neo4j", "error": "AQP_GRAPH_STORE is not neo4j"}
    payload = store.health()
    return {"service": "neo4j", **payload}


def _dask_health() -> dict[str, Any]:
    address = settings.dask_scheduler_address or "tcp://dask-scheduler:8786"
    payload: dict[str, Any] = {
        "ok": False,
        "service": "dask",
        "scheduler_address": address,
        "n_workers": 0,
        "threads_per_worker": settings.dask_threads_per_worker,
        "dashboard_url": _dask_dashboard_url(address),
        "error": None,
    }
    try:
        from distributed import Client

        client = Client(address, timeout="5s", set_as_default=False)
        try:
            info = client.scheduler_info()
            workers = info.get("workers", {}) if isinstance(info, dict) else {}
            payload.update(
                {
                    "ok": True,
                    "n_workers": len(workers),
                    "worker_addresses": list(workers.keys())[:10],
                    "scheduler": info.get("address") if isinstance(info, dict) else None,
                }
            )
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
    return payload


def _ray_health() -> dict[str, Any]:
    address = settings.ray_address or "ray://ray-head:10001"
    dashboard_url = _ray_dashboard_url(address)
    payload: dict[str, Any] = {
        "ok": False,
        "service": "ray",
        "address": address,
        "dashboard_url": dashboard_url,
        "error": None,
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{dashboard_url.rstrip('/')}/api/version")
            response.raise_for_status()
        payload.update({"ok": True, "version": response.json()})
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
    return payload


def _minio_health() -> dict[str, Any]:
    endpoint = (
        settings.s3_endpoint_url
        or settings.minio_endpoint_url
        or "http://minio:9000"
    ).rstrip("/")
    payload: dict[str, Any] = {
        "ok": False,
        "service": "minio",
        "endpoint_url": endpoint,
        "console_url": endpoint.replace(":9000", ":9090"),
        "live": False,
        "ready": False,
        "artifacts_bucket": settings.minio_artifacts_bucket,
        "datasets_bucket": settings.minio_datasets_bucket,
        "error": None,
    }
    try:
        with httpx.Client(timeout=5.0) as client:
            live = client.get(f"{endpoint}/minio/health/live")
            ready = client.get(f"{endpoint}/minio/health/ready")
        payload["live"] = live.status_code < 500
        payload["ready"] = ready.status_code < 500
        payload["ok"] = bool(payload["live"] and payload["ready"])
        payload["live_status_code"] = live.status_code
        payload["ready_status_code"] = ready.status_code
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
    return payload


def _dask_dashboard_url(address: str) -> str:
    host = "dask-scheduler"
    if "://" in address:
        rest = address.split("://", 1)[1]
        host = rest.split(":", 1)[0] or host
    return f"http://{host}:8787"


def _ray_dashboard_url(address: str) -> str:
    host = "ray-head"
    if "://" in address:
        rest = address.split("://", 1)[1]
        host = rest.split(":", 1)[0] or host
    return f"http://{host}:8265"


def _compose(args: list[str]) -> dict[str, Any]:
    compose_args = [
        "-f",
        "aqp_platform/compose/docker-compose.yml",
        "-f",
        "aqp_platform/compose/docker-compose.viz.yml",
        "--profile",
        "visualization",
        *args,
    ]
    commands = [
        ["docker", "compose", *compose_args],
        ["docker-compose", *compose_args],
    ]
    last: dict[str, Any] | None = None
    for command in commands:
        result = _run_compose_command(command)
        last = result
        if result["returncode"] == 0:
            return result
        stderr = str(result.get("stderr") or "")
        if "No such file or directory" in stderr or "is not a docker command" in stderr:
            continue
        return result
    return last or {"returncode": 1, "stdout": "", "stderr": "compose command unavailable"}


def _compose_unavailable(result: dict[str, Any]) -> bool:
    stderr = str(result.get("stderr") or "")
    return (
        "No such file or directory" in stderr
        or "compose command unavailable" in stderr
        or "is not a docker command" in stderr
        or "executable file not found" in stderr
    )


def _run_compose_command(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        return {"returncode": 1, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-8000:],
    }


def _container_names_for_service(name: str) -> list[str]:
    if name == "dask":
        return ["aqp-dask-scheduler", "aqp-dask-worker"]
    compose = COMPOSE_SERVICE_MAP.get(name, name)
    return [f"aqp-{compose}"]


def _docker_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.HTTPTransport(uds="/var/run/docker.sock"),
        base_url="http://docker",
        timeout=30.0,
    )


def _docker_logs(container: str, tail: int) -> dict[str, Any]:
    try:
        with _docker_client() as client:
            response = client.get(
                f"/containers/{container}/logs",
                params={
                    "stdout": "true",
                    "stderr": "true",
                    "tail": str(tail),
                    "timestamps": "false",
                },
            )
        if response.status_code >= 400:
            return {
                "ok": False,
                "container": container,
                "stdout": "",
                "stderr": response.text[-8000:],
                "status_code": response.status_code,
            }
        text = _decode_docker_log_stream(response.content)
        return {
            "ok": True,
            "container": container,
            "stdout": text[-8000:],
            "stderr": "",
            "status_code": response.status_code,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "container": container, "stdout": "", "stderr": str(exc)}


def _docker_action(container: str, action: ActionName) -> dict[str, Any]:
    try:
        with _docker_client() as client:
            response = client.post(f"/containers/{container}/{action}")
        ok_codes = {
            "start": {204, 304},
            "stop": {204, 304},
            "restart": {204},
        }[action]
        return {
            "ok": response.status_code in ok_codes,
            "container": container,
            "status_code": response.status_code,
            "error": None if response.status_code in ok_codes else response.text[-8000:],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "container": container, "error": str(exc)}


def _decode_docker_log_stream(payload: bytes) -> str:
    """Decode Docker Engine's multiplexed log stream.

    Containers with TTY disabled return frames shaped:
    [stream:1][000][length:4][payload:length].
    If the payload doesn't match that framing we fall back to utf-8 text.
    """

    if not payload:
        return ""
    chunks: list[bytes] = []
    i = 0
    try:
        while i + 8 <= len(payload):
            stream_type = payload[i]
            if stream_type not in (0, 1, 2):
                raise ValueError("not a docker multiplexed log stream")
            size = int.from_bytes(payload[i + 4 : i + 8], "big")
            i += 8
            if size < 0 or i + size > len(payload):
                raise ValueError("invalid docker log frame size")
            chunks.append(payload[i : i + size])
            i += size
        if i != len(payload):
            chunks.append(payload[i:])
        return b"".join(chunks).decode("utf-8", errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


__all__ = [
    "SERVICE_NAMES",
    "config_snapshot",
    "health",
    "iceberg_bootstrap",
    "iceberg_status",
    "service_action",
    "service_health",
    "service_logs",
    "trino_queries",
    "trino_query",
    "trino_verify",
]
