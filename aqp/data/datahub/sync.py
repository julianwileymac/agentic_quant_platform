"""DataHub bidirectional sync orchestrator."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_, select

from aqp.auth.contextvars import get_context_or_default
from aqp.config import settings
from aqp.data.datahub.aspect_emitter import push_all_aspects, push_aspect
from aqp.data.datahub.aspect_mapping import aqp_urn_to_datahub_entity_urn
from aqp.data.datahub.aspect_puller import pull_all_aspects
from aqp.data.datahub.emitter import push_all
from aqp.data.datahub.puller import pull_external
from aqp.metadata.urn import to_datahub_urn
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect

logger = logging.getLogger(__name__)


def sync_all(*, include_aspects: bool = False) -> dict[str, Any]:
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
    if include_aspects:
        ctx = get_context_or_default()
        if direction in {"push", "bidirectional"}:
            summary["aspect_push"] = push_all_aspects()
        if direction in {"pull", "bidirectional"}:
            tracked_urns = _list_owned_aspect_urns(
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
            )
            pulled_count = 0
            errors: list[str] = []
            for aqp_urn in tracked_urns:
                result = pull_all_aspects(
                    datahub_urn=aqp_urn_to_datahub_entity_urn(aqp_urn)
                )
                pulled_count += int(result.get("pulled_count") or 0)
                if result.get("error"):
                    errors.append(str(result["error"]))
                errors.extend(str(err) for err in (result.get("errors") or []))
            summary["aspect_pull"] = {
                "tracked_urns": len(tracked_urns),
                "pulled_count": pulled_count,
                "errors": errors,
            }
    return summary


def sync_aspects(
    *,
    push: bool = True,
    pull: bool = True,
    urn_filter: tuple[str, ...] | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Sync aspect-oriented metadata rows with DataHub.

    ``workspace_id`` / ``project_id`` scope the candidate urn list on the push
    path so a multi-tenant caller never accidentally emits another tenant's
    aspects to a shared DataHub instance (rule 33). When both are ``None`` the
    sync is limited to NULL-tenant rows (legacy / shared reference data).
    """
    push_enabled = bool(
        getattr(settings, "datahub_aspect_push_enabled", True)
    )
    pull_enabled = bool(
        getattr(settings, "datahub_aspect_pull_enabled", True)
    )
    if not push_enabled and not pull_enabled:
        return {
            "pushed": 0,
            "pulled": 0,
            "errors": [],
            "disabled": {
                "push_enabled": False,
                "pull_enabled": False,
                "reason": (
                    "AQP_DATAHUB_ASPECT_PUSH_ENABLED and "
                    "AQP_DATAHUB_ASPECT_PULL_ENABLED are both false"
                ),
            },
        }

    pushed = 0
    pulled = 0
    errors: list[str] = []
    urns = tuple(urn_filter or ())

    if push:
        if not push_enabled:
            errors.append(
                "aspect push disabled via AQP_DATAHUB_ASPECT_PUSH_ENABLED"
            )
        else:
            candidate_urns = urns or _list_owned_aspect_urns(
                workspace_id=workspace_id, project_id=project_id
            )
            for urn in candidate_urns:
                result = push_aspect(urn=urn)
                pushed += int(result.get("n_aspects") or 0)
                if result.get("error"):
                    errors.append(f"push {urn}: {result['error']}")
                for err in result.get("errors") or []:
                    if err:
                        errors.append(f"push {urn}: {err}")

    if pull:
        if not pull_enabled:
            errors.append(
                "aspect pull disabled via AQP_DATAHUB_ASPECT_PULL_ENABLED"
            )
        elif urns:
            for urn in urns:
                try:
                    is_datahub_urn = urn.startswith("urn:li:")
                    datahub_urn = (
                        urn if is_datahub_urn else to_datahub_urn(urn)
                    )
                    result = pull_all_aspects(datahub_urn=datahub_urn)
                    pulled += int(result.get("pulled_count") or 0)
                    if result.get("error"):
                        errors.append(f"pull {datahub_urn}: {result['error']}")
                    for err in result.get("errors") or []:
                        if err:
                            errors.append(f"pull {datahub_urn}: {err}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"pull {urn}: {exc}")
        else:
            tracked_urns = _list_owned_aspect_urns(
                workspace_id=workspace_id, project_id=project_id
            )
            for aqp_urn in tracked_urns:
                try:
                    result = pull_all_aspects(
                        datahub_urn=aqp_urn_to_datahub_entity_urn(aqp_urn)
                    )
                    pulled += int(result.get("pulled_count") or 0)
                    if result.get("error"):
                        errors.append(f"pull {aqp_urn}: {result['error']}")
                    for err in result.get("errors") or []:
                        if err:
                            errors.append(f"pull {aqp_urn}: {err}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"pull {aqp_urn}: {exc}")

    return {"pushed": pushed, "pulled": pulled, "errors": errors}


def _list_owned_aspect_urns(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> tuple[str, ...]:
    """Distinct URNs scoped to a tenancy bucket (rule 33).

    With no scope, returns only NULL-tenant rows so a shared-DataHub push
    never leaks another tenant's aspects. Scoped callers see their own
    rows plus the NULL-tenant baseline.
    """
    with get_session() as session:
        stmt = select(EntityAspect.urn).distinct()
        if workspace_id:
            stmt = stmt.where(
                or_(
                    EntityAspect.workspace_id == workspace_id,
                    EntityAspect.workspace_id.is_(None),
                )
            )
        else:
            stmt = stmt.where(EntityAspect.workspace_id.is_(None))
        if project_id:
            stmt = stmt.where(
                or_(
                    EntityAspect.project_id == project_id,
                    EntityAspect.project_id.is_(None),
                )
            )
        rows = session.execute(stmt).scalars().all()
    return tuple(str(urn) for urn in rows if urn)


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


__all__ = ["sync_all", "sync_aspects"]
