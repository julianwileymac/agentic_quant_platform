"""Deterministic critic checks for the EvolutionaryDebateAdapter.

These checks layer **on top of** the LLM-driven Critic agent so the
adapter never trusts an LLM verdict alone. They are pure-Python, AST-
driven, and never call ``router_complete`` (rule 2). They mirror the
hardening pattern the existing :mod:`aqp.strategies.lean.translator`
applies to LEAN strategy templates.

Five families of checks:

1. **Vectorisation** — reject per-symbol / per-day Python loops over
   the universe (``for sym in universe`` etc.). Quant strategies must
   stay vectorised.
2. **AST sandbox** — reject ``exec`` / ``eval`` / ``compile`` /
   ``__import__`` calls; reject attribute access on the
   ``os`` / ``subprocess`` / ``socket`` modules.
3. **Symbolic factor sandbox** — when ``formula`` is provided, route
   it through :func:`aqp.data.expressions_dsl.compile_to_factor_node`
   so the same NodeVisitor that rejects unsafe operators in the
   alpha DSL also runs against LLM proposals.
4. **DataMCP boundary** — heuristic: reject imports of
   ``aqp.persistence.*`` / ``pyiceberg.*`` / ``redis.*`` / ``sqlalchemy.*``
   from generated code, plus calls to
   ``router_complete`` / ``litellm.completion`` inside developer body.
5. **Risk constraints** — at least one of ``max_position`` /
   ``max_drawdown`` / ``cost_bps`` must appear (textual heuristic so
   the check works on natural-language constraints + numeric).
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


_FORBIDDEN_CALLS = frozenset({"exec", "eval", "compile", "__import__"})
_FORBIDDEN_ATTR_ROOTS = frozenset(
    {"os", "subprocess", "socket", "shutil", "ctypes", "pickle", "marshal"}
)
_FORBIDDEN_IMPORT_PREFIXES = (
    "aqp.persistence",
    "pyiceberg",
    "redis",
    "sqlalchemy",
    "litellm",
    "openai",
    "anthropic",
    "ollama",
)
_FORBIDDEN_FUNCTION_CALLS = frozenset(
    {
        "router_complete",
        "completion",
        "create",
        "generate",
        "deep_llm",
        "quick_llm",
    }
)
_PER_SYMBOL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfor\s+\w+\s+in\s+(?:universe|symbols|tickers|equities|stocks)\b"),
    re.compile(r"\bfor\s+\w+\s+in\s+(?:dates|trading_days|sessions)\b"),
    re.compile(r"\.apply\(\s*lambda\s+row\s*:"),
    re.compile(r"\.iterrows\(\s*\)"),
    re.compile(r"\.itertuples\(\s*\)"),
)
_RISK_HINTS = (
    "max_position",
    "max_drawdown",
    "drawdown",
    "cost_bps",
    "transaction_cost",
    "stop_loss",
    "position_limit",
    "leverage",
    "var_limit",
)


@dataclass
class CriticVerdict:
    """Aggregate outcome of every deterministic critic check.

    ``passed`` is the AND of all checks. ``violations`` carries
    structured diagnostics so the adapter can stamp them into the
    breadcrumb trail and the frontend timeline can render every
    failure individually rather than a single opaque rejection.
    """

    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    used_operators: list[str] = field(default_factory=list)
    used_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "used_operators": list(self.used_operators),
            "used_fields": list(self.used_fields),
        }


def run_deterministic_critic(
    proposal: dict[str, Any],
    *,
    formula_field: str = "formula",
    code_field: str = "code",
    rationale_field: str = "rationale",
    require_risk_constraints: bool = True,
) -> CriticVerdict:
    """Apply every deterministic critic check to ``proposal``.

    ``proposal`` is the JSON dict the Proposer / Developer agent
    emitted. The adapter combines this verdict with the LLM Critic
    response and only accepts a round when BOTH approve — there is no
    LLM-only path.
    """
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    used_operators: list[str] = []
    used_fields: list[str] = []

    formula = str(proposal.get(formula_field) or "").strip()
    code = str(proposal.get(code_field) or "").strip()

    if formula:
        verdict = _check_formula(formula)
        violations.extend(verdict["violations"])
        warnings.extend(verdict["warnings"])
        used_operators = verdict["operators"]
        used_fields = verdict["fields"]

    if code:
        violations.extend(_check_python_code(code))
        violations.extend(_check_per_symbol_loops(code))
        violations.extend(_check_forbidden_imports(code))

    if require_risk_constraints:
        constraint_violation = _check_risk_constraints(proposal, rationale_field)
        if constraint_violation is not None:
            violations.append(constraint_violation)

    return CriticVerdict(
        passed=not violations,
        violations=violations,
        warnings=warnings,
        used_operators=used_operators,
        used_fields=used_fields,
    )


# ----------------------------------------------------------------------------
# Per-check implementations
# ----------------------------------------------------------------------------


def _check_formula(formula: str) -> dict[str, Any]:
    """Drive the formula through the existing Symbolic-DSL sandbox."""
    out: dict[str, Any] = {
        "violations": [],
        "warnings": [],
        "operators": [],
        "fields": [],
    }
    try:
        from aqp.data.expressions_dsl import (  # type: ignore[attr-defined]
            SymbolicAlphaError,
            compile_to_factor_node,
        )
    except Exception as exc:  # noqa: BLE001 - DSL is in-tree but stay defensive
        out["warnings"].append(
            {
                "kind": "dsl_unavailable",
                "message": f"expressions_dsl unavailable: {exc}",
            }
        )
        return out
    try:
        node = compile_to_factor_node(formula)
    except SymbolicAlphaError as exc:
        out["violations"].append(
            {
                "kind": "ast_sandbox",
                "rule": "symbolic_factor_validator",
                "message": str(exc),
                "field": "formula",
            }
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out["violations"].append(
            {
                "kind": "ast_sandbox",
                "rule": "symbolic_factor_validator",
                "message": f"compile failed: {exc}",
                "field": "formula",
            }
        )
        return out
    out["operators"] = sorted(getattr(node, "operators", set()) or set())
    out["fields"] = sorted(getattr(node, "fields", set()) or set())
    return out


def _check_python_code(code: str) -> list[dict[str, Any]]:
    """Reject ``exec`` / ``eval`` / ``__import__`` and dangerous attr access."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return [
            {
                "kind": "syntax",
                "rule": "python_parse",
                "message": f"developer code did not parse: {exc}",
            }
        ]
    violations: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                violations.append(
                    {
                        "kind": "ast_sandbox",
                        "rule": "no_dynamic_code_exec",
                        "message": f"forbidden call to {func.id!r}",
                    }
                )
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_FUNCTION_CALLS:
                violations.append(
                    {
                        "kind": "datamcp_boundary",
                        "rule": "no_direct_llm_call",
                        "message": (
                            f"developer code calls {func.id!r} directly; "
                            "every LLM call must route through router_complete "
                            "via AgentRuntime"
                        ),
                    }
                )
        if isinstance(node, ast.Attribute):
            root = _attr_root(node)
            if root in _FORBIDDEN_ATTR_ROOTS:
                violations.append(
                    {
                        "kind": "ast_sandbox",
                        "rule": "no_unsafe_module_attr",
                        "message": f"forbidden attribute access on {root!r}",
                    }
                )
    return violations


def _attr_root(node: ast.Attribute) -> str:
    cursor: ast.AST = node
    while isinstance(cursor, ast.Attribute):
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        return cursor.id
    return ""


def _check_per_symbol_loops(code: str) -> list[dict[str, Any]]:
    """Reject Python code that loops per-symbol or per-day instead of vectorising."""
    violations: list[dict[str, Any]] = []
    for pattern in _PER_SYMBOL_PATTERNS:
        match = pattern.search(code)
        if match:
            violations.append(
                {
                    "kind": "vectorisation",
                    "rule": "no_per_symbol_loop",
                    "message": (
                        f"per-symbol / per-day loop detected: {match.group(0)!r}; "
                        "use vectorised pandas / numpy / pyarrow ops instead"
                    ),
                }
            )
    return violations


def _check_forbidden_imports(code: str) -> list[dict[str, Any]]:
    """Reject imports that would bypass DataMCP / sanctioned APIs."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return []
    bad: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
        for name in names:
            for prefix in _FORBIDDEN_IMPORT_PREFIXES:
                if name == prefix or name.startswith(prefix + "."):
                    bad.append(
                        {
                            "kind": "datamcp_boundary",
                            "rule": "no_bypass_import",
                            "message": (
                                f"forbidden import {name!r}; reach for the "
                                "matching DataMCP tool / sanctioned wrapper"
                            ),
                        }
                    )
                    break
    return bad


def _check_risk_constraints(
    proposal: dict[str, Any], rationale_field: str
) -> dict[str, Any] | None:
    """Surface a violation when no risk hint shows up anywhere on the proposal."""
    haystack_parts: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            haystack_parts.append(value.lower())
        elif isinstance(value, dict):
            for k, v in value.items():
                haystack_parts.append(str(k).lower())
                _walk(v)
        elif isinstance(value, (list, tuple, set)):
            for v in value:
                _walk(v)

    _walk(proposal)
    haystack = " ".join(haystack_parts)
    if any(hint in haystack for hint in _RISK_HINTS):
        return None
    return {
        "kind": "risk_constraints",
        "rule": "missing_risk_hint",
        "message": (
            "proposal mentions no risk constraint (max_position / max_drawdown "
            "/ cost_bps / leverage / stop_loss). Add at least one before the "
            "evaluator round."
        ),
        "field": rationale_field,
    }


__all__ = [
    "CriticVerdict",
    "run_deterministic_critic",
]
