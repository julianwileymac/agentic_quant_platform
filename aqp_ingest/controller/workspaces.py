"""Per-team Airbyte workspace provisioning.

Pairs with Alembic migration 0070 which adds
``organizations.airbyte_workspace_id``. The controller's two
public methods are:

- :meth:`ensure_workspace_for_org` — idempotently provision an
  Airbyte workspace for an :class:`Organization` and write the
  resulting external workspace id back to Postgres.
- :meth:`tear_down_workspace_for_org` — opposite, used by
  the AQP off-boarding flow.

The controller never imports ORM models directly; it speaks
Airbyte HTTP API via the existing
:class:`aqp.services.airbyte_client.AirbyteClient` and the
matching :data:`organizations.airbyte_workspace_id` column via a
narrow SQL session passed in by the caller.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkspaceDescriptor:
    org_id: str
    name: str
    airbyte_workspace_id: str | None = None
    created: bool = False


class AirbyteWorkspaceController:
    """Provisions one Airbyte workspace per AQP organization."""

    def __init__(self, *, airbyte_client: Any) -> None:
        self._client = airbyte_client

    def ensure_workspace_for_org(
        self,
        *,
        org_id: str,
        org_name: str,
        session_executor: Any | None = None,
    ) -> WorkspaceDescriptor:
        """Idempotently provision a workspace for *org_id*.

        ``session_executor`` is an optional callback the caller
        provides for the back-write to ``organizations.airbyte_workspace_id``;
        we don't import the ORM here so the controller stays
        boundary-safe.
        """
        existing = self._existing_workspace_for(org_id)
        if existing:
            return WorkspaceDescriptor(
                org_id=org_id,
                name=org_name,
                airbyte_workspace_id=existing,
                created=False,
            )
        new_id = self._create_workspace(org_id=org_id, org_name=org_name)
        if session_executor and new_id:
            try:
                session_executor(
                    "UPDATE organizations SET airbyte_workspace_id = :wsid WHERE id = :oid",
                    {"wsid": new_id, "oid": org_id},
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "could not back-write airbyte_workspace_id for org %s",
                    org_id,
                    exc_info=True,
                )
        return WorkspaceDescriptor(
            org_id=org_id,
            name=org_name,
            airbyte_workspace_id=new_id,
            created=bool(new_id),
        )

    def tear_down_workspace_for_org(self, *, org_id: str) -> bool:
        existing = self._existing_workspace_for(org_id)
        if not existing:
            return False
        try:
            # Airbyte v1 API: DELETE /v1/workspaces/{id}
            if hasattr(self._client, "delete_workspace"):
                self._client.delete_workspace(existing)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tear_down_workspace_for_org failed for %s: %s",
                org_id,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _existing_workspace_for(self, org_id: str) -> str | None:
        try:
            workspaces = self._client.list_workspaces() if hasattr(
                self._client, "list_workspaces"
            ) else []
        except Exception:  # noqa: BLE001
            workspaces = []
        for ws in workspaces or []:
            if str(ws.get("name", "")).startswith(f"aqp-org-{org_id}"):
                return str(ws.get("workspaceId") or ws.get("id"))
        return None

    def _create_workspace(self, *, org_id: str, org_name: str) -> str | None:
        try:
            if hasattr(self._client, "create_workspace"):
                ws = self._client.create_workspace(
                    name=f"aqp-org-{org_id}-{org_name}",
                    email=f"ops+{org_id}@aqp.local",
                )
                return str(ws.get("workspaceId") or ws.get("id"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("create_workspace failed for %s: %s", org_id, exc)
        return None


__all__ = ["AirbyteWorkspaceController", "WorkspaceDescriptor"]
