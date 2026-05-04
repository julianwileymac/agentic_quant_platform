"""Tests for ``RequestContext`` — the Lean-style ``AlgorithmNodePacket``."""
from __future__ import annotations

from aqp.auth.context import RequestContext, default_context, scope_id_for
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


def test_default_context_uses_canonical_seed_ids() -> None:
    ctx = default_context()
    assert ctx.user_id == DEFAULT_USER_ID
    assert ctx.org_id == DEFAULT_ORG_ID
    assert ctx.team_id == DEFAULT_TEAM_ID
    assert ctx.workspace_id == DEFAULT_WORKSPACE_ID
    assert ctx.project_id == DEFAULT_PROJECT_ID
    assert ctx.lab_id == DEFAULT_LAB_ID
    assert ctx.role == "owner"
    assert ctx.live_control is True


def test_with_run_id_returns_new_context_with_run() -> None:
    ctx = default_context()
    new_ctx = ctx.with_run_id("abc-123")
    assert new_ctx.run_id == "abc-123"
    assert new_ctx.user_id == ctx.user_id
    # Original is not mutated.
    assert ctx.run_id is None


def test_with_run_id_generates_uuid_when_missing() -> None:
    ctx = default_context()
    new_ctx = ctx.with_run_id()
    assert new_ctx.run_id is not None
    assert len(new_ctx.run_id) >= 32  # UUID-ish


def test_with_overrides_replaces_named_fields() -> None:
    ctx = default_context()
    new_ctx = ctx.with_overrides(workspace_id="new-ws", project_id=None)
    assert new_ctx.workspace_id == "new-ws"
    assert new_ctx.project_id is None
    # Other fields are preserved.
    assert new_ctx.user_id == ctx.user_id


def test_fingerprint_format_matches_lean_shape() -> None:
    ctx = RequestContext(
        user_id="u",
        workspace_id="w",
        project_id="p",
        run_id="r",
    )
    assert ctx.fingerprint() == "u-w-p-r"


def test_fingerprint_falls_back_to_lab_when_no_project() -> None:
    ctx = RequestContext(
        user_id="u",
        workspace_id="w",
        lab_id="lab-1",
        run_id="r",
    )
    assert ctx.fingerprint() == "u-w-lab-1-r"


def test_to_finops_extras_only_includes_set_fields() -> None:
    ctx = RequestContext(user_id="u", workspace_id="w")
    extras = ctx.to_finops_extras()
    assert extras == {"user_id": "u", "workspace_id": "w"}
    assert "project_id" not in extras


def test_scope_id_for_returns_correct_field() -> None:
    ctx = default_context()
    assert scope_id_for(ctx, SCOPE_ORG) == DEFAULT_ORG_ID
    assert scope_id_for(ctx, SCOPE_TEAM) == DEFAULT_TEAM_ID
    assert scope_id_for(ctx, SCOPE_USER) == DEFAULT_USER_ID
    assert scope_id_for(ctx, SCOPE_WORKSPACE) == DEFAULT_WORKSPACE_ID
    assert scope_id_for(ctx, SCOPE_PROJECT) == DEFAULT_PROJECT_ID
    assert scope_id_for(ctx, SCOPE_LAB) == DEFAULT_LAB_ID


def test_scope_id_for_unknown_kind_returns_none() -> None:
    ctx = default_context()
    assert scope_id_for(ctx, "unknown") is None
