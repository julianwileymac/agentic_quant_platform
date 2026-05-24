"""Pre-flight AGENTS.md rule compliance checks on every GraphSpec.

The :class:`LabRuntime` calls :func:`check_graph_compliance` BEFORE
dispatch. Any violation raises :class:`ComplianceError` with a
structured ``violations`` list — the route layer surfaces this so
the operator sees exactly which rule a graph breaks (per AGENTS.md
hard rules numbered 1-47).

Phase 0 ships the cheap structural checks:

- Every NodeSpec.type is a registered alias.
- Every edge's source / target port exists on the underlying
  NodeType definition.
- Edge dtype (when set) matches the upstream output port dtype.
- For mode='evaluation', the SweepConfig has at least one
  param_path / range / value entry.

Phase 2-5 layer on the harder semantic checks (e.g. medallion-layer
validation on any explicit Iceberg write, ``codebase.*`` import bans
inside agent body executors, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass

from aqp.lab.registry import get_node_type, known_aliases
from aqp.lab.schema import GraphSpec, NodeSpec


@dataclass(frozen=True)
class Violation:
    rule: str
    severity: str
    message: str
    node_id: str | None = None
    edge_id: str | None = None


class ComplianceError(ValueError):
    """Raised when :func:`check_graph_compliance` finds blocking violations."""

    def __init__(self, violations: list[Violation]) -> None:
        super().__init__(
            "GraphSpec failed pre-flight compliance: "
            + "; ".join(f"{v.rule}@{v.node_id or v.edge_id}: {v.message}" for v in violations)
        )
        self.violations = tuple(violations)


def check_graph_compliance(spec: GraphSpec) -> list[Violation]:
    """Return all violations found in ``spec``; empty list = green.

    The runtime treats any ``severity='error'`` row as blocking.
    """
    violations: list[Violation] = []
    alias_set = set(known_aliases())

    # 1. Unknown node type aliases (structural)
    for node in spec.nodes:
        if node.type not in alias_set:
            violations.append(
                Violation(
                    rule="lab.node_type_registered",
                    severity="error",
                    message=f"node type {node.type!r} is not registered",
                    node_id=node.id,
                )
            )

    # 2. Edge structural validity (ports + dtypes)
    nodes_by_id: dict[str, NodeSpec] = {n.id: n for n in spec.nodes}
    for edge in spec.edges:
        src = nodes_by_id.get(edge.source)
        tgt = nodes_by_id.get(edge.target)
        if src is None or tgt is None:
            # Already caught by GraphSpec model validator; we keep this
            # as a defensive belt-and-braces here.
            continue
        src_alias = src.type
        tgt_alias = tgt.type
        if src_alias not in alias_set or tgt_alias not in alias_set:
            continue
        try:
            src_nt = get_node_type(src_alias)
            tgt_nt = get_node_type(tgt_alias)
        except KeyError:
            continue
        src_port = next(
            (p for p in src_nt.outputs if p.name == edge.source_port), None
        )
        tgt_port = next(
            (p for p in tgt_nt.inputs if p.name == edge.target_port), None
        )
        # Fall back to "out" / "in" defaults when port names aren't
        # explicitly registered — single-port nodes are common.
        if src_port is None and src_nt.outputs:
            src_port = src_nt.outputs[0]
        if tgt_port is None and tgt_nt.inputs:
            tgt_port = tgt_nt.inputs[0]
        if src_port is None:
            violations.append(
                Violation(
                    rule="lab.edge_source_port",
                    severity="error",
                    message=(
                        f"node {src.id!r} ({src_alias}) has no output port "
                        f"{edge.source_port!r}"
                    ),
                    edge_id=edge.id,
                )
            )
            continue
        if tgt_port is None:
            violations.append(
                Violation(
                    rule="lab.edge_target_port",
                    severity="error",
                    message=(
                        f"node {tgt.id!r} ({tgt_alias}) has no input port "
                        f"{edge.target_port!r}"
                    ),
                    edge_id=edge.id,
                )
            )
            continue
        if (
            edge.dtype is not None
            and src_port.dtype != tgt_port.dtype
            and src_port.dtype != edge.dtype
        ):
            violations.append(
                Violation(
                    rule="lab.edge_dtype_match",
                    severity="error",
                    message=(
                        f"edge dtype {edge.dtype.value!r} does not match "
                        f"upstream output dtype {src_port.dtype.value!r}"
                    ),
                    edge_id=edge.id,
                )
            )

    # 3. Mode-specific sanity
    if spec.mode == "evaluation":
        sweep = (
            spec.mode_config.evaluation.sweep
            if spec.mode_config.evaluation
            else None
        )
        if sweep is None or not (
            sweep.param_paths or sweep.values or sweep.ranges
        ):
            violations.append(
                Violation(
                    rule="lab.evaluation_sweep_nonempty",
                    severity="error",
                    message=(
                        "mode='evaluation' requires at least one "
                        "param_path / value / range entry"
                    ),
                )
            )

    if spec.mode == "simulation":
        sim = spec.mode_config.simulation
        if sim is None:
            violations.append(
                Violation(
                    rule="lab.simulation_config_required",
                    severity="warning",
                    message="mode='simulation' without a SimulationConfig — defaults will apply",
                )
            )

    return violations


__all__ = ["ComplianceError", "Violation", "check_graph_compliance"]
