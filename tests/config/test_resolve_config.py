"""End-to-end resolve_config tests using the in-memory DB fixture."""
from __future__ import annotations


def test_resolve_config_falls_back_to_global_settings_layer() -> None:
    """Without any overlays the Settings baseline shows through."""
    from aqp.auth.context import default_context
    from aqp.config import resolve_config

    cfg = resolve_config("llm", context=default_context())
    # The Settings baseline projects every field whose name starts with
    # ``llm_`` into the ``llm`` namespace (with the prefix stripped).
    # E.g. ``settings.llm_provider`` becomes ``cfg["provider"]``.
    assert "provider" in cfg or "model" in cfg


def test_resolve_config_writes_and_resolves_workspace_overlay(in_memory_db) -> None:
    from aqp.auth.context import RequestContext
    from aqp.config import resolve_config, set_overlay
    from aqp.config.defaults import (
        DEFAULT_ORG_ID,
        DEFAULT_TEAM_ID,
        DEFAULT_USER_ID,
        SCOPE_WORKSPACE,
    )

    set_overlay(SCOPE_WORKSPACE, "ws-test", "llm", {"deep_model": "gpt-5.5"})

    ctx = RequestContext(
        user_id=DEFAULT_USER_ID,
        org_id=DEFAULT_ORG_ID,
        team_id=DEFAULT_TEAM_ID,
        workspace_id="ws-test",
    )
    cfg = resolve_config("llm", context=ctx)
    assert cfg.get("deep_model") == "gpt-5.5"


def test_resolve_config_project_layer_wins_over_workspace(in_memory_db) -> None:
    from aqp.auth.context import RequestContext
    from aqp.config import resolve_config, set_overlay
    from aqp.config.defaults import SCOPE_PROJECT, SCOPE_WORKSPACE

    set_overlay(SCOPE_WORKSPACE, "ws-1", "llm", {"deep_model": "ws-model"})
    set_overlay(SCOPE_PROJECT, "proj-1", "llm", {"deep_model": "proj-model"})

    ctx = RequestContext(
        user_id="u",
        workspace_id="ws-1",
        project_id="proj-1",
    )
    cfg = resolve_config("llm", context=ctx)
    assert cfg.get("deep_model") == "proj-model"
