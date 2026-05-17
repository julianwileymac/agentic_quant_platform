"""Symbolic alpha factor DSL — LLM-emitted formulas → engine-agnostic ``FactorNode``.

The Alpha-Researcher agent emits factor candidates as short Python-
like expressions over a vocabulary of safe primitives (``Mean``,
``Std``, ``EMA``, ``WMA``, ``RSI``, ``MACD``, ``Corr``, ``Slope``,
``Sign``, ``Abs``, ``Log``, ``Rank``, plus the symbol fields
``$close`` / ``$high`` / ``$low`` / ``$open`` / ``$volume``). This
module compiles them through a strictly whitelisted AST sandbox
(mirroring :mod:`aqp.strategies.lean.translator` per AGENTS.md
rule 35) and emits a :class:`FactorNode` that any registered
:class:`BaseBacktestEngine` can consume.

Security contract
-----------------

The AST validator is strictly opt-in:

- Only the operators in :data:`SYMBOLIC_OPERATORS` are callable.
- Only :data:`SYMBOLIC_FIELDS` are readable as ``Name`` nodes
  (prefixed ``$`` is rewritten to ``FIELD_`` before parsing).
- No attribute access, subscript, lambda, if-expr, list / dict /
  set / comprehension, walrus, or import.
- Numeric / string / bool / None constants only.
- Free function names that aren't in the whitelist raise
  :class:`SymbolicAlphaError` immediately at compile time.

Anything else is a hard reject — no `exec` / `eval` of raw LLM
output ever crosses the boundary.

Reward bridge
-------------

The Alpha-Researcher agent's reward comes from running the compiled
:class:`FactorNode` through a quick :class:`EventDrivenBacktester`
pass on a deterministic medallion-replay slice and reading the
Sharpe / IR / max-drawdown out of the resulting :class:`BacktestResult`
summary. The agent's update step (Phase 5 of the FinRL-X loop)
mutates the symbolic formula and tries again.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar

import numpy as np
import pandas as pd

from aqp.data.expressions import OPERATORS as _BASE_OPERATORS

logger = logging.getLogger(__name__)


class SymbolicAlphaError(ValueError):
    """Raised on any AST validation failure inside the symbolic DSL."""


# ---------------------------------------------------------------------------
# Operator + field vocabulary
# ---------------------------------------------------------------------------

# The DSL inherits every operator from :mod:`aqp.data.expressions`
# (Ref, Delay, Mean, EMA, MACD, RSI, etc.) plus a thin layer of
# convenience helpers for LLM-emitted formulas.

def _abs(x: Any) -> Any:
    if isinstance(x, pd.Series):
        return x.abs()
    return np.abs(x)


def _sign(x: Any) -> Any:
    if isinstance(x, pd.Series):
        return np.sign(x)
    return float(np.sign(x))


def _log(x: Any) -> Any:
    if isinstance(x, pd.Series):
        return np.log(x.clip(lower=1e-12))
    return float(np.log(max(float(x), 1e-12)))


def _rank(x: pd.Series) -> pd.Series:
    if not isinstance(x, pd.Series):
        raise SymbolicAlphaError("Rank() requires a Series argument")
    return x.rank(pct=True)


def _clip(x: pd.Series, low: float, high: float) -> pd.Series:
    if not isinstance(x, pd.Series):
        return float(np.clip(float(x), float(low), float(high)))
    return x.clip(lower=float(low), upper=float(high))


# Curated allow-list. The base OPERATORS map comes from
# aqp.data.expressions and includes Ref/Delay/Mean/EMA/MACD/RSI/...;
# we extend with a few LLM-friendly helpers above.
SYMBOLIC_OPERATORS: dict[str, Callable[..., Any]] = {
    **_BASE_OPERATORS,
    "Abs": _abs,
    "Sign": _sign,
    "Log": _log,
    "Rank": _rank,
    "Clip": _clip,
}

SYMBOLIC_FIELDS: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "returns",
)


_ALLOWED_BINOPS: tuple[type, ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)


_ALLOWED_UNARYOPS: tuple[type, ...] = (ast.USub, ast.UAdd)


# ---------------------------------------------------------------------------
# AST sandbox validator
# ---------------------------------------------------------------------------


class _SymbolicFactorValidator(ast.NodeVisitor):
    """Walk the AST and raise on any non-whitelisted construct."""

    _FORBIDDEN = (
        ast.Attribute,
        ast.Subscript,
        ast.Lambda,
        ast.IfExp,
        ast.List,
        ast.Dict,
        ast.Set,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.Starred,
        ast.NamedExpr,
        ast.Import,
        ast.ImportFrom,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.AsyncFunctionDef,
        ast.FunctionDef,
        ast.ClassDef,
    )

    def __init__(self) -> None:
        super().__init__()
        self.used_operators: set[str] = set()
        self.used_fields: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            raise SymbolicAlphaError(
                f"Disallowed call: expression must call top-level operators by name, got "
                f"{ast.dump(node.func)}"
            )
        name = node.func.id
        if name not in SYMBOLIC_OPERATORS:
            raise SymbolicAlphaError(f"Unknown operator {name!r}")
        self.used_operators.add(name)
        for arg in node.args:
            self.visit(arg)
        if node.keywords:
            raise SymbolicAlphaError("Keyword arguments are not allowed in symbolic alphas")

    def visit_Name(self, node: ast.Name) -> None:
        # ``$<field>`` was rewritten to ``FIELD_<field>`` before parsing.
        if node.id.startswith("FIELD_"):
            field_name = node.id[len("FIELD_") :]
            if field_name not in SYMBOLIC_FIELDS:
                raise SymbolicAlphaError(
                    f"Unknown symbol field ${field_name}. Allowed: {SYMBOLIC_FIELDS}"
                )
            self.used_fields.add(field_name)
            return
        if node.id not in SYMBOLIC_OPERATORS:
            raise SymbolicAlphaError(
                f"Bare identifier {node.id!r} not allowed (use ${node.id} for a field or a registered operator)"
            )

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if type(node.op) not in _ALLOWED_BINOPS:
            raise SymbolicAlphaError(f"Disallowed binop {type(node.op).__name__}")
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if type(node.op) not in _ALLOWED_UNARYOPS:
            raise SymbolicAlphaError(f"Disallowed unary op {type(node.op).__name__}")
        self.visit(node.operand)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, (int, float, bool, str)) and node.value is not None:
            raise SymbolicAlphaError(f"Disallowed constant: {type(node.value).__name__}")

    def visit_Expression(self, node: ast.Expression) -> None:
        self.visit(node.body)

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, self._FORBIDDEN):
            raise SymbolicAlphaError(
                f"Forbidden AST construct: {type(node).__name__} (the symbolic DSL is "
                "intentionally narrow; complex factor logic belongs in a Python class "
                "inheriting from FactorNode)"
            )
        super().generic_visit(node)


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


@dataclass
class FactorNode:
    """Engine-agnostic compiled factor.

    A :class:`FactorNode` carries the validated AST + the alias map
    so any engine that wants per-bar evaluation can call
    :meth:`compute` and any engine that wants a pre-materialised
    panel can call :meth:`compute_panel`.

    Round-trip
    ----------

    - Source formula preserved on :attr:`formula`.
    - Operator + field usage cached for telemetry / audit.
    - Reusable across engines: vbt-pro consumes the panel,
      event-driven consumes the per-symbol Series, hftbacktest /
      Backtrader (Phase 9) consume the dynamic indicator class
      built from :meth:`as_backtrader_indicator`.
    """

    formula: str
    tree: ast.AST = field(repr=False)
    used_operators: set[str] = field(default_factory=set)
    used_fields: set[str] = field(default_factory=set)
    name: str = "alpha"

    def compute(self, bars: pd.DataFrame) -> pd.Series:
        """Evaluate the factor against a single-symbol bars DataFrame."""
        env = self._build_env(bars)
        return _eval_node(self.tree.body, env)  # type: ignore[attr-defined]

    def compute_panel(self, bars_panel: pd.DataFrame) -> pd.DataFrame:
        """Evaluate per-symbol over a long-format ``date / tic / OHLCV`` frame."""
        if "tic" not in bars_panel.columns:
            return self.compute(bars_panel).to_frame(self.name)
        out: dict[str, pd.Series] = {}
        for tic, group in bars_panel.groupby("tic"):
            out[str(tic)] = self.compute(group.sort_values("date").reset_index(drop=True))
        wide = pd.DataFrame(out)
        wide.columns.name = "tic"
        return wide

    def as_callable(self) -> Callable[[pd.DataFrame], pd.Series]:
        """Return a thin closure suitable for engines that accept a callable."""
        return lambda bars: self.compute(bars)

    def as_backtrader_indicator(self) -> type:
        """Return a dynamic ``bt.Indicator`` subclass that wraps :meth:`compute`.

        Backtrader is an optional Phase 9 engine — if the package is
        not installed this raises :class:`ImportError`. The returned
        class has a single line attribute named ``alpha`` whose value
        on each bar is the compiled factor evaluated against the
        most-recent ``lookback`` bars.
        """
        try:
            import backtrader as bt
        except Exception as exc:
            raise ImportError(
                "as_backtrader_indicator requires backtrader (Phase 9 optional dep)"
            ) from exc
        compiled = self
        cls_name = f"_AlphaIndicator_{abs(hash(self.formula)) % 10_000_000}"

        def __init__(self, *a: Any, **kw: Any) -> None:
            bt.Indicator.__init__(self, *a, **kw)

        def next(self) -> None:
            n = max(len(self.data.close), 1)
            window = pd.DataFrame(
                {
                    "open": list(self.data.open.get(ago=0, size=n)),
                    "high": list(self.data.high.get(ago=0, size=n)),
                    "low": list(self.data.low.get(ago=0, size=n)),
                    "close": list(self.data.close.get(ago=0, size=n)),
                    "volume": list(self.data.volume.get(ago=0, size=n)),
                }
            )
            series = compiled.compute(window)
            self.lines.alpha[0] = float(series.iloc[-1]) if len(series) else float("nan")

        cls = type(
            cls_name,
            (bt.Indicator,),
            {
                "lines": ("alpha",),
                "__init__": __init__,
                "next": next,
                "__doc__": f"Dynamic Backtrader indicator compiled from {self.formula!r}",
            },
        )
        return cls

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": "FactorNode",
            "formula": self.formula,
            "used_operators": sorted(self.used_operators),
            "used_fields": sorted(self.used_fields),
            "name": self.name,
        }

    @staticmethod
    def _build_env(bars: pd.DataFrame) -> dict[str, Any]:
        env: dict[str, Any] = {}
        for col in ("open", "high", "low", "close", "volume"):
            if col in bars.columns:
                env[f"FIELD_{col}"] = bars[col]
        if "vwap" not in bars.columns and all(c in bars.columns for c in ("close", "high", "low")):
            env["FIELD_vwap"] = (bars["close"] + bars["high"] + bars["low"]) / 3.0
        elif "vwap" in bars.columns:
            env["FIELD_vwap"] = bars["vwap"]
        if "returns" not in bars.columns and "close" in bars.columns:
            env["FIELD_returns"] = bars["close"].pct_change().fillna(0.0)
        elif "returns" in bars.columns:
            env["FIELD_returns"] = bars["returns"]
        return env


def compile_to_factor_node(
    formula: str,
    *,
    name: str | None = None,
) -> FactorNode:
    """Compile a symbolic-alpha string into a :class:`FactorNode`.

    Parameters
    ----------
    formula:
        Human-readable expression in the symbolic DSL
        (e.g. ``"Sign(EMA($close, 12) - EMA($close, 26))"``).
    name:
        Optional human-readable name for the factor. Defaults to a
        truncated form of the formula.

    Raises
    ------
    SymbolicAlphaError:
        On any AST validation failure. Wraps the underlying
        :class:`SyntaxError` so the Alpha-Researcher agent can decode
        the failure cause and self-correct on the next iteration.
    """
    clean = formula.strip().replace("$", "FIELD_")
    if not clean:
        raise SymbolicAlphaError("Empty formula")
    try:
        tree = ast.parse(clean, mode="eval")
    except SyntaxError as exc:
        raise SymbolicAlphaError(f"Invalid expression {formula!r}: {exc}") from exc
    validator = _SymbolicFactorValidator()
    validator.visit(tree)
    return FactorNode(
        formula=formula,
        tree=tree,
        used_operators=validator.used_operators,
        used_fields=validator.used_fields,
        name=name or (formula if len(formula) <= 60 else formula[:57] + "..."),
    )


# ---------------------------------------------------------------------------
# Internal evaluator (mirrors aqp.data.expressions._eval_node)
# ---------------------------------------------------------------------------


def _eval_node(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Call):
        func_name = getattr(node.func, "id", None)
        if func_name not in SYMBOLIC_OPERATORS:
            raise SymbolicAlphaError(f"Disallowed operator: {func_name}")
        args = [_eval_node(a, env) for a in node.args]
        return SYMBOLIC_OPERATORS[func_name](*args)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, env)
        right = _eval_node(node.right, env)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if isinstance(right, (int, float)) and right == 0:
                raise SymbolicAlphaError("Division by zero")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right
        raise SymbolicAlphaError(f"Disallowed binop: {type(node.op).__name__}")
    if isinstance(node, ast.UnaryOp):
        value = _eval_node(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return +value
        raise SymbolicAlphaError(f"Disallowed unary op: {type(node.op).__name__}")
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise SymbolicAlphaError(f"Unknown field: {node.id}")
        return env[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    raise SymbolicAlphaError(f"Unsupported AST node: {type(node).__name__}")


__all__ = [
    "FactorNode",
    "SymbolicAlphaError",
    "SYMBOLIC_FIELDS",
    "SYMBOLIC_OPERATORS",
    "compile_to_factor_node",
]


# ---------------------------------------------------------------------------
# Class attribute on FactorNode that lets _eval_node bind back into it
# ---------------------------------------------------------------------------

FactorNode._eval_node: ClassVar[Callable[[ast.AST, dict[str, Any]], Any]] = staticmethod(_eval_node)  # type: ignore[attr-defined]
