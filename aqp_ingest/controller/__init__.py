"""Airbyte workspace + connection controller.

Speaks only Terraform + Airbyte HTTP API (per the AGENTS contract);
never imports `aqp.*` ORM models directly. The per-team
`Organization.airbyte_workspace_id` column (Alembic 0070) is the
only Postgres handshake.
"""
from __future__ import annotations

from aqp_ingest.controller.workspaces import (
    AirbyteWorkspaceController,
    WorkspaceDescriptor,
)

__all__ = ["AirbyteWorkspaceController", "WorkspaceDescriptor"]
