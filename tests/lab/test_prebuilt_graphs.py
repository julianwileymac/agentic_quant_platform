"""End-to-end exit test for the Phase 5 prebuilt graphs.

Verifies the train-labeler wizard graph + tearsheet-to-agent graph
both pass the pre-flight compliance check, have the expected node
sequence, and hash deterministically (so the route layer can dedupe
graphs across operators with identical configs).
"""
from __future__ import annotations

from aqp.lab.compliance import check_graph_compliance
from aqp.lab.prebuilt_graphs import (
    build_tearsheet_to_agent_graph,
    build_train_labeler_graph,
)


def test_train_labeler_graph_passes_compliance() -> None:
    graph = build_train_labeler_graph(vt_symbol="AAPL")
    violations = check_graph_compliance(graph)
    blocking = [v for v in violations if v.severity == "error"]
    assert blocking == []
    # Five nodes in the canonical sequence.
    assert [n.id for n in graph.nodes] == ["bars", "tech", "labels", "model", "sheet"]
    # Topological sort honours dependencies.
    order = [n.id for n in graph.topological_order()]
    assert order[0] == "bars"
    assert order[-1] == "sheet"


def test_train_labeler_graph_is_deterministic() -> None:
    a = build_train_labeler_graph(vt_symbol="AAPL")
    b = build_train_labeler_graph(vt_symbol="AAPL")
    # Schema node IDs are fixed strings so the snapshot hash is
    # deterministic across builds — the route layer relies on this
    # to dedupe identical wizard requests.
    assert a.snapshot_hash() == b.snapshot_hash()


def test_tearsheet_to_agent_graph_terminates_in_agent() -> None:
    graph = build_tearsheet_to_agent_graph(agent_spec="codebase_assistant")
    violations = check_graph_compliance(graph)
    blocking = [v for v in violations if v.severity == "error"]
    assert blocking == []
    order = [n.id for n in graph.topological_order()]
    assert order[-1] == "agent"
    agent_node = next(n for n in graph.nodes if n.id == "agent")
    assert agent_node.type == "agent.crewai"
    assert agent_node.params.get("persist_as_note") is True
