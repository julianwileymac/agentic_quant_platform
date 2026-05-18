"""``AssistantSpec`` snapshot hash + validation tests."""
from __future__ import annotations

import pytest

from aqp.assistants.spec import AssistantSpec, AssistantToolPolicy


def _agent_spec(**overrides):
    base = dict(
        name="t.platform_assistant",
        description="t",
        mode="agent",
        agent_spec_name="codebase_assistant",
        system_instructions="hello",
        annotations=["assistant"],
    )
    base.update(overrides)
    return AssistantSpec(**base)


def test_snapshot_hash_is_stable():
    a = _agent_spec()
    b = _agent_spec()
    assert a.snapshot_hash() == b.snapshot_hash()


def test_snapshot_hash_changes_when_target_ref_changes():
    a = _agent_spec(agent_spec_name="codebase_assistant")
    b = _agent_spec(agent_spec_name="research.equity")
    assert a.snapshot_hash() != b.snapshot_hash()


def test_snapshot_hash_changes_when_tool_policy_changes():
    a = _agent_spec()
    b = _agent_spec()
    a_hash = a.snapshot_hash()
    b.tool_policy = AssistantToolPolicy(
        read_only=False, allowed_tools=["rag_query"], explicit_scopes=["data:write"]
    )
    assert a_hash != b.snapshot_hash()


def test_explicit_scopes_normalised():
    """Duplicates collapsed and empty strings dropped."""
    spec = AssistantSpec(
        name="t.assistant",
        mode="agent",
        agent_spec_name="x",
        tool_policy=AssistantToolPolicy(
            explicit_scopes=["data:write", "data:write", "", "data:read"]
        ),
    )
    assert spec.tool_policy.explicit_scopes == ["data:read", "data:write"]


def test_workflow_mode_requires_workflow_spec_name():
    with pytest.raises(ValueError):
        AssistantSpec(name="t", mode="workflow")  # type: ignore[call-arg]


def test_agent_mode_requires_agent_spec_name():
    with pytest.raises(ValueError):
        AssistantSpec(name="t", mode="agent")  # type: ignore[call-arg]


def test_target_kind_and_target_ref_helpers():
    a = _agent_spec(agent_spec_name="alpha.proposer")
    assert a.target_kind == "agent"
    assert a.target_ref == "alpha.proposer"

    w = AssistantSpec(
        name="t.workflow",
        mode="workflow",
        workflow_spec_name="assistant.financial_analyst_team_evolutionary",
    )
    assert w.target_kind == "workflow"
    assert w.target_ref == "assistant.financial_analyst_team_evolutionary"


def test_round_trip_yaml():
    spec = _agent_spec()
    out = spec.to_yaml()
    again = AssistantSpec.from_yaml_str(out)
    assert again.snapshot_hash() == spec.snapshot_hash()
