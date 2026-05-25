"""Inference-time OOD safety rules + circuit breaker.

The skill runtime calls :meth:`RuleRegistry.load_pack` before each step
to fetch the active list of rules; the rules return a structured
:class:`RuleVerdict` indicating whether the step should be allowed and
why. Rejected verdicts surface as ``HandlerPolicyError``-style errors
to the agent for self-correction.

Built-in packs:

- ``ood_default`` — z-score threshold + range guard + tensor-shape guard.
- ``strict`` — same as ``ood_default`` with tighter thresholds.
- ``permissive`` — no rules; useful for local debugging.

Rule subclasses self-register via :class:`MLRuleMeta` so adding a
custom rule is one class definition with ``rule_name`` set.
"""
from __future__ import annotations

from aqp_models.rules.base import (
    MLRule,
    MLRuleMeta,
    RuleRegistry,
    RuleVerdict,
)
from aqp_models.rules.circuit_breaker import CircuitBreaker
from aqp_models.rules.ood_guard import (
    OODGuard,
    RangeGuard,
    TensorShapeGuard,
)

__all__ = [
    "CircuitBreaker",
    "MLRule",
    "MLRuleMeta",
    "OODGuard",
    "RangeGuard",
    "RuleRegistry",
    "RuleVerdict",
    "TensorShapeGuard",
]
