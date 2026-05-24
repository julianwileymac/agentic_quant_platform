"""HTTP relay from ``lineage_openlineage_outbox`` -> Marquez (Workstream B).

The drain function below is called from the Celery beat task in
:mod:`aqp.tasks.openlineage_relay_tasks`. It pulls up to ``batch``
pending rows, POSTs each payload to the configured Marquez endpoint,
and marks the row ``sent_at`` on 2xx. Failed rows record their last
error and increment ``attempts``; the next pass picks them up again
(no exponential backoff at the DB layer — the Celery beat schedule
already provides cadence-level backoff).

Marquez URL resolution honours the topology service per AQP rule 47:
``settings.lineage_openlineage_marquez_url`` is the explicit knob;
when unset, the :mod:`aqp.config.topology_fallback` table provides
the cluster-local default once the ``marquez`` service is declared
in ``aqp_platform/configs/deployment/topology.yaml``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def get_marquez_url() -> str:
    """Return the configured Marquez OL HTTP endpoint, or empty string."""
    try:
        from aqp.config import settings

        return str(
            getattr(settings, "lineage_openlineage_marquez_url", "") or ""
        ).rstrip("/")
    except Exception:  # noqa: BLE001
        return ""


def _post_endpoint(base_url: str) -> str:
    """The OpenLineage HTTP transport POSTs to ``<base>/api/v1/lineage``."""
    if not base_url:
        return ""
    if base_url.endswith("/api/v1/lineage"):
        return base_url
    return f"{base_url}/api/v1/lineage"


def post_openlineage_event(payload: dict[str, Any]) -> tuple[bool, str]:
    """POST a single OpenLineage RunEvent to Marquez.

    Returns ``(success, error_or_status)``. Never raises so the drain
    loop can keep moving on transient failures.
    """
    url = _post_endpoint(get_marquez_url())
    if not url:
        return (False, "marquez_url_not_configured")
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx is a base dep
        return (False, "httpx_unavailable")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        if 200 <= resp.status_code < 300:
            return (True, str(resp.status_code))
        return (False, f"status={resp.status_code} body={resp.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        return (False, f"http_error: {exc}")


def drain_outbox_once(
    *,
    batch: int | None = None,
) -> dict[str, Any]:
    """Drain up to ``batch`` pending rows from the outbox.

    Returns a summary dict with ``sent`` / ``failed`` counts. Used by
    :mod:`aqp.tasks.openlineage_relay_tasks.drain_openlineage_outbox`
    and by tests that exercise the relay in-process.
    """
    from aqp.config import settings
    from aqp.persistence.db import get_session
    from aqp.persistence.models_openlineage import OpenLineageOutbox

    limit = int(batch if batch is not None else getattr(settings, "lineage_openlineage_relay_batch", 200))
    limit = max(1, min(limit, 5000))

    sent = 0
    failed = 0
    failed_ids: list[str] = []

    with get_session() as session:
        rows = (
            session.query(OpenLineageOutbox)
            .filter(OpenLineageOutbox.sent_at.is_(None))
            .order_by(OpenLineageOutbox.created_at.asc())
            .limit(limit)
            .all()
        )
        for row in rows:
            ok, info = post_openlineage_event(row.payload)
            if ok:
                row.sent_at = datetime.utcnow()
                row.last_error = None
                sent += 1
            else:
                row.attempts = (row.attempts or 0) + 1
                row.last_error = info[:500]
                failed += 1
                failed_ids.append(str(row.id))
        session.commit()

    return {
        "sent": sent,
        "failed": failed,
        "failed_ids": failed_ids[:10],
        "limit": limit,
    }


__all__ = [
    "drain_outbox_once",
    "get_marquez_url",
    "post_openlineage_event",
]
