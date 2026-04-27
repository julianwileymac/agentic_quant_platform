"""Liveness / readiness probes for the infra stack."""
from __future__ import annotations

import logging

from fastapi import APIRouter

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
