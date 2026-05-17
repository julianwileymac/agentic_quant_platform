"""DataHub bidirectional sync orchestrator."""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings
from aqp.data.datahub.emitter import push_all
from aqp.data.datahub.puller import pull_external

logger = logging.getLogger(__name__)


def sync_all() -> dict[str, Any]:
    """Run push + pull according to ``datahub_sync_direction``.

    Also kicks off a best-effort
    :func:`aqp.tasks.streaming_link_tasks.refresh_links` refresh after
    a pull so the streaming graph mirrors any new lineage that
    arrived from DataHub. Failures are swallowed -- DataHub sync
    should never block on the link refresher.
    """
    direction = (settings.datahub_sync_direction or "push").lower()
    summary: dict[str, Any] = {"direction": direction}
    if direction in {"push", "bidirectional"}:
        summary["push"] = push_all()
    if direction in {"pull", "bidirectional"}:
        summary["pull"] = pull_external()
        summary["streaming_links_refresh"] = _refresh_streaming_links()
    return summary


def _refresh_streaming_links() -> dict[str, Any]:
    try:
        from aqp.tasks.streaming_link_tasks import refresh_links
    except Exception as exc:  # pragma: no cover
        return {"queued": False, "error": f"task unavailable: {exc}"}
    try:
        result = refresh_links.delay()
        return {"queued": True, "task_id": str(getattr(result, "id", "local"))}
    except Exception as exc:  # noqa: BLE001
        logger.debug("streaming_links_refresh dispatch failed", exc_info=True)
        return {"queued": False, "error": str(exc)}


__all__ = ["sync_all"]
