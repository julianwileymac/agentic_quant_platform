"""Pull external datasets from DataHub into the AQP-side cache."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.config import settings
from aqp.data.datahub.client import get_client

logger = logging.getLogger(__name__)


def pull_platform(platform: str, *, count: int = 100) -> dict[str, Any]:
    """Search for every dataset under ``platform`` and cache the URN list."""
    client = get_client()
    if not client.is_configured():
        return {"platform": platform, "datasets": [], "error": "datahub not configured"}
    payload = client.search(query=f"platform:{platform}", count=count)
    results = []
    for entry in (payload.get("value") or {}).get("entities", []) or []:
        urn = entry.get("entity") or entry.get("urn")
        if urn:
            results.append({"urn": urn})

    _record_pull(platform=platform, urns=[r["urn"] for r in results])
    return {"platform": platform, "datasets": results, "count": len(results)}


def pull_external() -> dict[str, Any]:
    """Pull every platform listed in ``datahub_external_platforms``."""
    summary: dict[str, Any] = {}
    for platform in settings.datahub_external_platform_list:
        summary[platform] = pull_platform(platform)
    return summary


def _record_pull(*, platform: str, urns: list[str]) -> None:
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_pipelines import DatahubSyncLog

        with get_session() as session:
            row = DatahubSyncLog(
                direction="pull",
                target=platform[:240],
                urn=None,
                platform=platform,
                platform_instance=settings.datahub_platform_instance,
                status="ok",
                payload={"urns": urns[:200], "count": len(urns)},
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
            )
            session.add(row)
    except Exception as exc:  # noqa: BLE001
        logger.debug("datahub pull log skipped: %s", exc)


__all__ = ["pull_external", "pull_platform"]
