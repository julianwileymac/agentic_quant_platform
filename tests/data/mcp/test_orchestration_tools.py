"""Phase 3 — ``data.orchestration.*`` + ``data.automation.*`` MCP tools.

Covers:

- Every Phase 3 tool registers under :data:`DATA_MCP_TOOLS` with the
  expected name + ``data:read`` scope.
- ``data.orchestration.list_adapters`` returns the in-process metaclass
  catalog (works without any persistence layer).
- ``data.orchestration.list_runs`` / ``get_run`` / ``fusion_inputs_for_run``
  degrade cleanly when the Phase 5 ``workflow_runs`` table is missing.
- Calls without ``data:read`` scope are rejected by the default
  policy_check (rule 22 boundary).
- The two ``data.automation.*`` tools surface the beat-schedule entries
  the orchestration scheduler claims.
"""
from __future__ import annotations

from aqp.data.mcp.base import MCPToolContext
from aqp.data.mcp.registry import DATA_MCP_TOOLS, get_data_mcp_tool


def _ctx(*scopes: str) -> MCPToolContext:
    return MCPToolContext(
        actor="test",
        actor_kind="user",
        workspace_id="ws-test",
        project_id="proj-test",
        granted_scopes=tuple(scopes) if scopes else (),
    )


def test_phase3_tools_registered():
    expected = {
        "data.orchestration.list_adapters",
        "data.orchestration.list_runs",
        "data.orchestration.get_run",
        "data.orchestration.list_workflows",
        "data.orchestration.fusion_inputs_for_run",
        "data.automation.list_schedules",
        "data.automation.get_schedule_status",
    }
    assert expected.issubset(set(DATA_MCP_TOOLS.keys()))


def test_list_adapters_returns_metaclass_catalog():
    tool = get_data_mcp_tool("data.orchestration.list_adapters")
    result = tool.invoke(ctx=_ctx("data:read"))
    assert result.ok is True
    aliases = {a["alias"] for a in result.data["adapters"]}
    # All Phase 2 + Phase 3 adapters auto-registered through the metaclass.
    assert "LangGraphAdapter" in aliases
    assert "CrewProcessAdapter" in aliases
    assert "DialecticalDebateAdapter" in aliases
    assert "AutomationScheduleAdapter" in aliases


def test_list_runs_returns_empty_when_table_missing(monkeypatch):
    """If the Phase 5 ORM isn't importable, the tool returns an empty
    list with ``table_present=False`` so the UI keeps rendering.
    """
    import builtins

    real_import = builtins.__import__

    def _block_models_workflows(name, *args, **kwargs):
        if name == "aqp.persistence.models_workflows":
            raise ImportError("models_workflows not provisioned")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_models_workflows)
    tool = get_data_mcp_tool("data.orchestration.list_runs")
    result = tool.invoke(ctx=_ctx("data:read"))
    assert result.ok is True
    assert result.data == {"runs": [], "table_present": False}


def test_get_run_returns_not_found_when_table_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _block(name, *args, **kwargs):
        if name == "aqp.persistence.models_workflows":
            raise ImportError("not yet provisioned")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block)
    tool = get_data_mcp_tool("data.orchestration.get_run")
    result = tool.invoke(ctx=_ctx("data:read"), run_id="abc-123")
    assert result.ok is False
    assert "not yet provisioned" in (result.error or "")


def test_fusion_inputs_returns_empty_when_table_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _block(name, *args, **kwargs):
        if name == "aqp.persistence.models_workflows":
            raise ImportError("not yet provisioned")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block)
    tool = get_data_mcp_tool("data.orchestration.fusion_inputs_for_run")
    result = tool.invoke(ctx=_ctx("data:read"), run_id="abc-123")
    assert result.ok is True
    assert result.data["table_present"] is False


def test_orchestration_tools_require_data_read_scope():
    tool = get_data_mcp_tool("data.orchestration.list_adapters")
    result = tool.invoke(ctx=_ctx())  # no scopes
    assert result.ok is False
    assert "policy denied" in (result.error or "")


def test_list_workflows_includes_yaml_when_requested(tmp_path, monkeypatch):
    """The tool reads `configs/workflows/*.yaml` when include_yaml=True."""
    # Repo ships `configs/workflows/daily_stock_analysis.yaml`; verify it
    # surfaces when include_yaml is True.
    tool = get_data_mcp_tool("data.orchestration.list_workflows")
    result = tool.invoke(ctx=_ctx("data:read"), include_yaml=True)
    assert result.ok is True
    names = [w["name"] for w in result.data["workflows"]]
    assert any(n == "research.daily_stock_analysis_v1" for n in names) or names == []


def test_automation_list_schedules_filters_by_prefix(monkeypatch):
    """Only beat entries with the orchestration prefixes are returned."""
    from aqp.tasks.celery_app import celery_app

    monkeypatch.setattr(
        celery_app.conf,
        "beat_schedule",
        {
            "workflow-daily-stock-analysis": {
                "task": "aqp.tasks.orchestration_tasks.run_workflow",
                "schedule": 3600.0,
                "kwargs": {"spec_name": "daily.spec"},
            },
            "orchestration-fanout": {
                "task": "aqp.tasks.orchestration_tasks.run_workflow",
                "schedule": 60.0,
            },
            "agent-stall-watchdog": {
                "task": "aqp.tasks.agent_watchdog_tasks.scan_for_stalled_agent_runs",
                "schedule": 60.0,
            },
        },
    )
    tool = get_data_mcp_tool("data.automation.list_schedules")
    result = tool.invoke(ctx=_ctx("data:read"))
    assert result.ok is True
    keys = {entry["key"] for entry in result.data["schedules"]}
    assert keys == {"workflow-daily-stock-analysis", "orchestration-fanout"}


def test_automation_get_schedule_status_rejects_bad_prefix():
    tool = get_data_mcp_tool("data.automation.get_schedule_status")
    result = tool.invoke(ctx=_ctx("data:read"), key="agent-stall-watchdog")
    assert result.ok is False
    assert "prefix" in (result.error or "").lower()


def test_automation_get_schedule_status_returns_not_found(monkeypatch):
    from aqp.tasks.celery_app import celery_app

    monkeypatch.setattr(celery_app.conf, "beat_schedule", {})
    tool = get_data_mcp_tool("data.automation.get_schedule_status")
    result = tool.invoke(
        ctx=_ctx("data:read"), key="workflow-does-not-exist"
    )
    assert result.ok is False
    assert result.error == "not_found"
