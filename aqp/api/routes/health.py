"""Liveness / readiness probes for the infra stack."""
from __future__ import annotations

from fastapi import APIRouter

from aqp.api.schemas import HealthResponse

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
        pass
    try:
        from aqp.persistence.db import engine

        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        postgres_ok = True
    except Exception:
        pass
    try:
        from aqp.data.chroma_store import ChromaStore

        ChromaStore()
        chroma_ok = True
    except Exception:
        pass
    return HealthResponse(
        status="ok" if (redis_ok and postgres_ok) else "degraded",
        ollama=ollama_ok,
        redis=redis_ok,
        postgres=postgres_ok,
        chromadb=chroma_ok,
        models=list_local_models() if ollama_ok else [],
    )
