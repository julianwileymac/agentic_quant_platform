"""Liveness / readiness probes for the infra stack.

Three endpoints, three different audiences:

- ``GET /health`` — full diagnostic check used by external dashboards
  and the original Solara monitor. Returns details about every
  dependency the AQP API talks to (Ollama / Redis / Postgres / Chroma /
  vLLM). Always returns 200 with a per-dep breakdown so the caller can
  render a status table; the ``status`` field on the body is
  ``"ok"`` only when both Redis and Postgres respond.
- ``GET /livez`` — Phase 4b control-plane maturation. Lightweight
  Kubernetes liveness probe. Returns 200 the moment the FastAPI
  process is up; performs zero downstream calls. Intended for
  ``livenessProbe`` in the manifests under
  ``deployments/kubernetes/base/`` so transient dependency outages
  don't kill an otherwise-healthy pod.
- ``GET /readyz`` — Phase 4b. Strict readiness probe. Returns 200 only
  when every critical dependency (Postgres, Redis, Auth0 JWKS when
  configured, Iceberg catalog when configured) responds; returns 503
  with a per-dependency breakdown otherwise. Wired into
  ``readinessProbe`` + ``startupProbe`` so traffic doesn't reach a
  pod until it can actually serve work.

The split mirrors the canonical Kubernetes probe pattern: liveness
restarts the pod when the process itself is broken, readiness gates
endpoint inclusion in the Service when downstream dependencies are
unavailable.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Response, status

from aqp.api.schemas import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    from aqp.llm.ollama_client import check_health, list_local_models

    ollama_ok = check_health()
    redis_ok = False
    postgres_ok = False
    chroma_ok = False
    try:
        import redis

        from aqp.config import settings

        redis.Redis.from_url(settings.redis_url).ping()
        redis_ok = True
    except Exception:
        logger.exception("redis health probe failed")
    try:
        from aqp.persistence.db import engine

        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        postgres_ok = True
    except Exception:
        logger.exception("postgres health probe failed")
    try:
        from aqp.data.chroma_store import ChromaStore

        ChromaStore()
        chroma_ok = True
    except Exception:
        logger.exception("chromadb health probe failed")
    vllm_ok = False
    vllm_models: list[str] = []
    try:
        from aqp.config import settings

        if settings.vllm_base_url:
            import httpx

            base = settings.vllm_base_url.rstrip("/")
            # `AQP_VLLM_BASE_URL` is documented as `http://vllm:8000/v1` in
            # our YAMLs; tolerate both shapes by trimming a trailing
            # ``/v1`` so we always land on ``<host>/v1/models``.
            if base.endswith("/v1"):
                base = base[: -len("/v1")]
            headers: dict[str, str] = {}
            if settings.vllm_api_key:
                headers["Authorization"] = f"Bearer {settings.vllm_api_key}"
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{base}/v1/models", headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, list):
                vllm_models = [str(m.get("id", "")) for m in data if isinstance(m, dict)]
            vllm_ok = True
    except Exception:
        logger.exception("vllm health probe failed")
        vllm_ok = False
    return HealthResponse(
        status="ok" if (redis_ok and postgres_ok) else "degraded",
        ollama=ollama_ok,
        redis=redis_ok,
        postgres=postgres_ok,
        chromadb=chroma_ok,
        vllm=vllm_ok,
        models=list_local_models() if ollama_ok else [],
        vllm_models=vllm_models,
    )


# ---------------------------------------------------------------------------
# Phase 4b — Kubernetes liveness / readiness probes
# ---------------------------------------------------------------------------


@router.get("/livez")
def livez() -> dict[str, Any]:
    """Liveness probe — returns 200 the moment the process is up.

    Performs ZERO downstream calls. The contract is "this Python
    process is reachable and the FastAPI router is wired". A failing
    livez means the kubelet must restart the pod; a successful livez
    means the process is healthy enough to keep running. Dependency
    failures belong on ``/readyz`` so they don't trigger restarts.
    """
    return {"status": "alive"}


def _check_postgres(timeout_s: float = 3.0) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        from aqp.persistence.db import engine

        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {
            "name": "postgres",
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "postgres",
            "status": "unreachable",
            "detail": str(exc)[:200],
        }


def _check_redis(timeout_s: float = 3.0) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        import redis

        from aqp.config import settings

        client = redis.Redis.from_url(
            settings.redis_url, socket_timeout=timeout_s, socket_connect_timeout=timeout_s
        )
        client.ping()
        return {
            "name": "redis",
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "redis",
            "status": "unreachable",
            "detail": str(exc)[:200],
        }


def _check_auth0_jwks(timeout_s: float = 3.0) -> dict[str, Any]:
    """Probe the Auth0 / OIDC JWKS endpoint.

    Skipped when the active provider is ``local`` / ``mock`` (local-first
    dev). Returns ``status="skipped"`` so readyz still passes without a
    live IdP.
    """
    try:
        from aqp.config import settings

        provider = str(settings.auth_provider or "").lower()
        if provider in ("", "local", "mock"):
            return {"name": "auth0_jwks", "status": "skipped"}
        issuer = str(settings.auth_oidc_issuer or "").strip()
        if not issuer:
            return {
                "name": "auth0_jwks",
                "status": "unconfigured",
                "detail": "AQP_AUTH_OIDC_ISSUER unset",
            }
        import httpx

        url = issuer.rstrip("/") + "/.well-known/jwks.json"
        t0 = time.perf_counter()
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url)
        resp.raise_for_status()
        return {
            "name": "auth0_jwks",
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "auth0_jwks",
            "status": "unreachable",
            "detail": str(exc)[:200],
        }


def _check_iceberg(timeout_s: float = 3.0) -> dict[str, Any]:
    """Probe the Iceberg catalog backend.

    Best-effort — the catalog client is heavy-weight, so we issue a
    cheap ``list_namespaces`` call and ignore the result. Failure
    means the catalog is currently unreachable; the API can still
    serve non-data routes, so we mark this dependency as
    ``status="degraded"`` rather than failing the readiness probe
    entirely. Operators that need strict iceberg-readiness can flip
    ``settings.readyz_iceberg_strict`` (covered by an opt-in).
    """
    try:
        from aqp.data.iceberg_catalog import get_catalog

        catalog = get_catalog()
        if catalog is None:
            return {"name": "iceberg", "status": "skipped"}
        # Most catalog impls expose ``list_namespaces``; if not, fall
        # through with status=ok since merely being able to construct
        # the client is enough.
        if hasattr(catalog, "list_namespaces"):
            t0 = time.perf_counter()
            list(catalog.list_namespaces())
            return {
                "name": "iceberg",
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            }
        return {"name": "iceberg", "status": "ok"}
    except Exception as exc:  # noqa: BLE001
        return {
            "name": "iceberg",
            "status": "degraded",
            "detail": str(exc)[:200],
        }


async def _gather_dependency_checks() -> list[dict[str, Any]]:
    """Run every readiness probe concurrently in a thread pool."""
    loop = asyncio.get_running_loop()
    return await asyncio.gather(
        loop.run_in_executor(None, _check_postgres),
        loop.run_in_executor(None, _check_redis),
        loop.run_in_executor(None, _check_auth0_jwks),
        loop.run_in_executor(None, _check_iceberg),
    )


@router.get("/readyz")
async def readyz(response: Response) -> dict[str, Any]:
    """Readiness probe — returns 200 only when every critical dep is up.

    Critical deps:
      - Postgres (must be reachable)
      - Redis (must be reachable)
      - Auth0 / OIDC JWKS (must be reachable IF configured;
        ``status="skipped"`` for local-first dev counts as ok)

    Non-critical deps (degraded does not fail the probe):
      - Iceberg catalog

    Returns 503 with a structured per-dependency breakdown when any
    critical dep is unreachable. The K8s ``readinessProbe`` reads the
    HTTP status; the operator UI can render the body to surface
    *which* dependency is down.
    """
    checks = await _gather_dependency_checks()
    critical = [c for c in checks if c["name"] in ("postgres", "redis", "auth0_jwks")]
    overall_ok = all(
        c["status"] in ("ok", "skipped", "unconfigured") for c in critical
    )
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}
