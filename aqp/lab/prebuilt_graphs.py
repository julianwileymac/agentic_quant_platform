"""Prebuilt :class:`GraphSpec` factories.

Phase 5 ships two flagship prebuilt graphs:

- :func:`build_train_labeler_graph` — wires the data → feature →
  triple_barrier → gbm → tearsheet flow the ``POST
  /lab/labelers/train`` route hands back.
- :func:`build_tearsheet_to_agent_graph` — the plan's flagship
  agent.crewai example: a tearsheet + 2 RAG hits feed into a CrewAI
  agent that writes a one-page analysis attached to ``lab_notes``.

Both helpers return a frozen :class:`GraphSpec` that the Phase 0+
compliance checker validates before submit.
"""
from __future__ import annotations

from aqp.lab.schema import EdgeSpec, GraphSpec, NodeSpec, Port, PortDType


def build_train_labeler_graph(
    *,
    vt_symbol: str,
    iceberg_namespace: str = "aqp_silver_equities_bars",
    iceberg_table: str = "bars_1m",
    label_kind_seed: str = "swing",
) -> GraphSpec:
    """data → tech → triple_barrier → sklearn → tearsheet."""
    bars = NodeSpec(
        id="bars",
        type="data.iceberg_scan",
        category="DataSource",
        outputs=[Port(name="out", dtype=PortDType.FRAME)],
        params={"namespace": iceberg_namespace, "table": iceberg_table},
    )
    tech = NodeSpec(
        id="tech",
        type="feature.technical",
        category="Feature",
        inputs=[Port(name="in", dtype=PortDType.BAR_SERIES)],
        outputs=[Port(name="out", dtype=PortDType.PANEL)],
        params={"indicator": "rsi", "window": 14},
    )
    labels = NodeSpec(
        id="labels",
        type="label.triple_barrier",
        category="Labeler",
        inputs=[Port(name="bars", dtype=PortDType.BAR_SERIES)],
        outputs=[Port(name="out", dtype=PortDType.ANNOTATION_SET)],
        params={
            "pt_sl": [1.0, 1.0],
            "vertical_barrier_days": 5,
            "label_kind_seed": label_kind_seed,
            "vt_symbol": vt_symbol,
        },
    )
    model = NodeSpec(
        id="model",
        type="model.sklearn",
        category="Model",
        inputs=[
            Port(name="X", dtype=PortDType.PANEL),
            Port(name="y", dtype=PortDType.SIGNAL),
        ],
        outputs=[Port(name="out", dtype=PortDType.MODEL_ARTIFACT)],
        params={"estimator": "rf_classifier", "target_column": "tb_bin"},
    )
    sheet = NodeSpec(
        id="sheet",
        type="out.tearsheet",
        category="Output",
        inputs=[Port(name="portfolio", dtype=PortDType.PORTFOLIO)],
        params={"title": f"{vt_symbol} meta-labeler"},
    )
    return GraphSpec(
        name=f"train-labeler:{vt_symbol}",
        description=f"Train a meta-labeler over {vt_symbol} using the operator's manual labels.",
        mode="testing",
        nodes=[bars, tech, labels, model, sheet],
        edges=[
            # Explicit edge ids keep the snapshot hash stable across
            # builds (EdgeSpec.id defaults to a uuid4 otherwise).
            EdgeSpec(id="e-bars-tech", source="bars", target="tech"),
            EdgeSpec(id="e-bars-labels", source="bars", target="labels"),
            EdgeSpec(id="e-tech-model", source="tech", target="model"),
            EdgeSpec(id="e-labels-model", source="labels", target="model"),
            EdgeSpec(id="e-model-sheet", source="model", target="sheet"),
        ],
    )


def build_tearsheet_to_agent_graph(
    *,
    agent_spec: str,
    iceberg_namespace: str = "aqp_silver_equities_bars",
    iceberg_table: str = "bars_1m",
    prompt: str = "",
) -> GraphSpec:
    """data → vbt_portfolio → tearsheet → agent.crewai (one-page analysis).

    The plan's Phase 5 flagship example: the agent receives the
    tearsheet artifact + lets the operator pin RAG hits via the
    PaperRagDrawer cite-to-notes flow.
    """
    bars = NodeSpec(
        id="bars",
        type="data.iceberg_scan",
        category="DataSource",
        outputs=[Port(name="out", dtype=PortDType.FRAME)],
        params={"namespace": iceberg_namespace, "table": iceberg_table},
    )
    strategy = NodeSpec(
        id="portfolio",
        type="strategy.vbt_portfolio",
        category="Strategy",
        inputs=[Port(name="signal", dtype=PortDType.SIGNAL)],
        outputs=[Port(name="out", dtype=PortDType.PORTFOLIO)],
        params={"mode": "holding", "init_cash": 1_000_000.0, "fees": 0.001},
    )
    sheet = NodeSpec(
        id="sheet",
        type="out.tearsheet",
        category="Output",
        inputs=[Port(name="portfolio", dtype=PortDType.PORTFOLIO)],
        outputs=[Port(name="out", dtype=PortDType.JSON)],
        params={"title": "lab analysis"},
    )
    agent = NodeSpec(
        id="agent",
        type="agent.crewai",
        category="Agent",
        inputs=[Port(name="context", dtype=PortDType.JSON, optional=True)],
        outputs=[Port(name="out", dtype=PortDType.AGENT_HANDLE)],
        params={
            "agent_spec": agent_spec,
            "prompt": (
                prompt
                or "Summarise the portfolio's behaviour, cite any matching "
                "research papers, and flag risks."
            ),
            "persist_as_note": True,
        },
    )
    return GraphSpec(
        name=f"tearsheet-to-agent:{agent_spec}",
        description=f"Run a tearsheet + dispatch {agent_spec} for a one-page analysis.",
        mode="testing",
        nodes=[bars, strategy, sheet, agent],
        edges=[
            EdgeSpec(id="e-bars-portfolio", source="bars", target="portfolio"),
            EdgeSpec(id="e-portfolio-sheet", source="portfolio", target="sheet"),
            EdgeSpec(id="e-sheet-agent", source="sheet", target="agent"),
        ],
    )


__all__ = ["build_tearsheet_to_agent_graph", "build_train_labeler_graph"]
