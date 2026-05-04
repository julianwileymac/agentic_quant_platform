"""``RequestContext`` — the Lean-style ``AlgorithmNodePacket`` for AQP.

Every code path that runs on a user's behalf (HTTP request, Celery task,
Dagster asset, CLI invocation) carries one of these so the chokepoints in
:mod:`aqp.persistence.ledger`, :mod:`aqp.agents.runtime`,
:mod:`aqp.rag.hierarchy`, and :mod:`aqp.data.iceberg_catalog` can stamp
ownership without re-resolving the identity chain.

Compare to ``inspiration/Lean-master/Common/Packets/AlgorithmNodePacket.cs``
which carries ``UserId``, ``OrganizationId``, ``ProjectId`` on every job
and exposes ``GetAlgorithmName() => "{UserId}-{ProjectId}-{AlgorithmId}"``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from aqp.config.defaults import (
    DEFAULT_LAB_ID,
    DEFAULT_ORG_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_TEAM_ID,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
    SCOPE_LAB,
    SCOPE_ORG,
    SCOPE_PROJECT,
    SCOPE_TEAM,
    SCOPE_USER,
    SCOPE_WORKSPACE,
)


@dataclass
class RequestContext:
    """Identity + scope context for one request, task, or run.

    All fields are optional except ``user_id``: the auth dependency always
    populates the user; the workspace/project/lab are pulled from the
    ``X-AQP-Workspace`` / ``X-AQP-Project`` / ``X-AQP-Lab`` headers (or
    Celery task headers) and validated against the user's accessible scopes.

    The :meth:`fingerprint` method mirrors Lean's
    ``AlgorithmNodePacket.GetAlgorithmName()`` for log / metric correlation.
    """

    user_id: str
    org_id: str | None = None
    team_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    lab_id: str | None = None
    run_id: str | None = None
    role: str | None = None
    live_control: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "RequestContext":
        """Synthesise the local-first default context (no DB round-trip)."""
        return cls(
            user_id=DEFAULT_USER_ID,
            org_id=DEFAULT_ORG_ID,
            team_id=DEFAULT_TEAM_ID,
            workspace_id=DEFAULT_WORKSPACE_ID,
            project_id=DEFAULT_PROJECT_ID,
            lab_id=DEFAULT_LAB_ID,
            role="owner",
            live_control=True,
        )

    def with_run_id(self, run_id: str | None = None) -> "RequestContext":
        """Return a copy stamped with a run id (for Lean-style fingerprints)."""
        rid = run_id or str(uuid.uuid4())
        return RequestContext(
            user_id=self.user_id,
            org_id=self.org_id,
            team_id=self.team_id,
            workspace_id=self.workspace_id,
            project_id=self.project_id,
            lab_id=self.lab_id,
            run_id=rid,
            role=self.role,
            live_control=self.live_control,
            extras=dict(self.extras),
        )

    def with_overrides(self, **overrides: Any) -> "RequestContext":
        """Return a copy with selected fields replaced."""
        data = self.to_dict()
        data.update(overrides)
        extras = data.pop("extras", {}) or {}
        return RequestContext(extras=dict(extras), **data)

    def fingerprint(self) -> str:
        """``{user}-{workspace}-{project|lab}-{run}`` style identifier.

        Borrowed from Lean's
        ``AlgorithmNodePacket.GetAlgorithmName()``. Useful for log
        correlation, metric dimensions, and Iceberg path prefixes.
        """
        parts = [
            self.user_id or "anon",
            self.workspace_id or "no-ws",
            self.project_id or self.lab_id or "no-proj",
            self.run_id or "no-run",
        ]
        return "-".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "org_id": self.org_id,
            "team_id": self.team_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "lab_id": self.lab_id,
            "run_id": self.run_id,
            "role": self.role,
            "live_control": self.live_control,
            "extras": dict(self.extras),
        }

    def to_finops_extras(self) -> dict[str, str]:
        """Project the context into the FinOps tag map for telemetry."""
        out: dict[str, str] = {}
        for key, value in (
            ("user_id", self.user_id),
            ("org_id", self.org_id),
            ("team_id", self.team_id),
            ("workspace_id", self.workspace_id),
            ("project_id", self.project_id),
            ("lab_id", self.lab_id),
            ("run_id", self.run_id),
        ):
            if value:
                out[key] = str(value)
        return out


def default_context() -> RequestContext:
    """Module-level convenience for callers that want the local-first default."""
    return RequestContext.default()


def scope_id_for(context: RequestContext, scope_kind: str) -> str | None:
    """Return the ``scope_id`` field on *context* matching the given kind."""
    mapping = {
        SCOPE_ORG: context.org_id,
        SCOPE_TEAM: context.team_id,
        SCOPE_USER: context.user_id,
        SCOPE_WORKSPACE: context.workspace_id,
        SCOPE_PROJECT: context.project_id,
        SCOPE_LAB: context.lab_id,
    }
    return mapping.get(scope_kind)


__all__ = ["RequestContext", "default_context", "scope_id_for"]
