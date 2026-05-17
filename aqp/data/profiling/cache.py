"""Profile cache (Redis + Postgres).

Two-layer cache for dataset profiles:

- Hot path lives in Redis (``aqp:profile:<ns>:<name>:<version>``);
  TTL from :class:`aqp.config.Settings.profile_cache_ttl_seconds`.
- Durable mirror lives in :class:`aqp.persistence.DatasetProfile` so
  the UI keeps showing summaries even after Redis evictions.

Best-effort: Redis or Postgres unavailability logs at DEBUG and
falls through to whichever layer is reachable.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _redis_key(namespace: str, name: str, version: int | None) -> str:
    from aqp.config import settings

    prefix = settings.profile_cache_prefix or "aqp:profile"
    suffix = f":{int(version)}" if version is not None else ""
    return f"{prefix}:{namespace}:{name}{suffix}"


def _redis_client():  # type: ignore[no-untyped-def]
    try:
        from redis import Redis

        from aqp.config import settings

        return Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("redis unavailable for profile cache: %s", exc)
        return None


def write_profile(
    *,
    namespace: str,
    name: str,
    version: int | None,
    profile: dict[str, Any],
) -> None:
    """Persist ``profile`` to Redis (hot) and Postgres (durable)."""
    from aqp.config import settings

    payload = json.dumps(profile, default=str)
    ttl = max(60, int(settings.profile_cache_ttl_seconds or 3600))
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)

    client = _redis_client()
    if client is not None:
        try:
            client.set(_redis_key(namespace, name, version), payload, ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.debug("redis set failed: %s", exc)

    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_pipelines import DatasetProfile

        with get_session() as session:
            existing = session.execute(
                select(DatasetProfile)
                .where(DatasetProfile.namespace == namespace)
                .where(DatasetProfile.name == name)
                .where(
                    (DatasetProfile.version == version)
                    if version is not None
                    else DatasetProfile.version.is_(None)
                )
                .limit(1)
            ).scalar_one_or_none()
            row_kwargs = dict(
                namespace=namespace,
                name=name,
                version=version,
                rows=int(profile.get("rows") or 0),
                bytes=int(profile.get("bytes") or 0),
                columns=list(profile.get("columns") or []),
                summary={
                    "engine": profile.get("engine"),
                    "computed_at": profile.get("computed_at"),
                    "requested_engine": profile.get("requested_engine"),
                },
                engine=str(profile.get("engine") or "local"),
                computed_at=datetime.utcnow(),
                expires_at=expires_at,
            )
            if existing is None:
                row = DatasetProfile(**row_kwargs)
                session.add(row)
            else:
                for key, value in row_kwargs.items():
                    setattr(existing, key, value)
                session.add(existing)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.debug("postgres profile write skipped: %s", exc)


def read_profile(
    *, namespace: str, name: str, version: int | None = None
) -> dict[str, Any] | None:
    """Read the cached profile, preferring Redis."""
    client = _redis_client()
    if client is not None:
        try:
            payload = client.get(_redis_key(namespace, name, version))
            if payload:
                return json.loads(payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("redis get failed: %s", exc)

    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_pipelines import DatasetProfile

        with get_session() as session:
            row = session.execute(
                select(DatasetProfile)
                .where(DatasetProfile.namespace == namespace)
                .where(DatasetProfile.name == name)
                .where(
                    (DatasetProfile.version == version)
                    if version is not None
                    else DatasetProfile.version.is_(None)
                )
                .order_by(DatasetProfile.computed_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "rows": int(row.rows),
                "bytes": int(row.bytes),
                "columns": list(row.columns or []),
                "engine": row.engine,
                "computed_at": (row.computed_at or datetime.utcnow()).isoformat(),
                "namespace": row.namespace,
                "name": row.name,
                "version": row.version,
                **(row.summary or {}),
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("postgres profile read skipped: %s", exc)
    return None


def delete_profile(
    *, namespace: str, name: str, version: int | None = None
) -> None:
    client = _redis_client()
    if client is not None:
        try:
            client.delete(_redis_key(namespace, name, version))
        except Exception as exc:  # noqa: BLE001
            logger.debug("redis del failed: %s", exc)
    try:
        from sqlalchemy import delete

        from aqp.persistence.db import get_session
        from aqp.persistence.models_pipelines import DatasetProfile

        with get_session() as session:
            stmt = delete(DatasetProfile).where(
                DatasetProfile.namespace == namespace,
                DatasetProfile.name == name,
            )
            if version is not None:
                stmt = stmt.where(DatasetProfile.version == version)
            session.execute(stmt)
    except Exception as exc:  # noqa: BLE001
        logger.debug("postgres profile delete skipped: %s", exc)


def refresh_table_profile(
    namespace: str,
    name: str,
    *,
    version: int | None = None,
    engine: str = "auto",
    head_rows: int | None = None,
) -> dict[str, Any] | None:
    """Profile an Iceberg table head and persist the result."""
    from aqp.config import settings
    from aqp.data.profiling.profiler import profile_iceberg_table

    head_rows = head_rows or settings.profile_distinct_sample_rows or 200_000
    try:
        profile = profile_iceberg_table(
            namespace,
            name,
            head_rows=head_rows,
            engine=engine,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("refresh_table_profile %s.%s failed: %s", namespace, name, exc)
        return None
    write_profile(
        namespace=namespace,
        name=name,
        version=version,
        profile=profile,
    )
    return profile


__all__ = [
    "delete_profile",
    "read_profile",
    "refresh_table_profile",
    "write_profile",
]
