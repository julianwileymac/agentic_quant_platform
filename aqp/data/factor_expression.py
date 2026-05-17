"""Tiny factor expression DSL inspired by Alpha101 / akquant FactorEngine.

Source: ``inspiration/akquant-main/examples/19_factor_expression.py``.

Supports the following primitives:

- ``Ts_Mean(x, n)`` — rolling mean of ``x`` over ``n`` bars.
- ``Ts_Std(x, n)`` — rolling std of ``x`` over ``n`` bars.
- ``Ts_Corr(x, y, n)`` — rolling Pearson corr.
- ``Ts_Sum(x, n)`` — rolling sum.
- ``Rank(x)`` — cross-sectional rank (per timestamp across ``vt_symbol``).
- ``Decay_Linear(x, n)`` — linearly weighted average over last ``n`` bars.
- ``Delta(x, n)`` — value minus value ``n`` bars ago.
- ``Log(x)``, ``Abs(x)``, ``Sign(x)``.
- Arithmetic ``+ - * /``, comparison ``> < ==``.

Inputs are columns of a long-format DataFrame keyed on
``(vt_symbol, timestamp)``. Outputs are pandas Series keyed by the same
MultiIndex.
"""
from __future__ import annotations

import ast
import logging
import operator
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_CMPOPS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


def _ts_op(series: pd.Series, n: int, fn) -> pd.Series:
    return series.groupby(level="vt_symbol", group_keys=False).apply(
        lambda s: fn(s, n)
    )


def _ts_mean(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _ts_std(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).std()


def _ts_sum(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).sum()


def _decay_linear(s: pd.Series, n: int) -> pd.Series:
    weights = np.arange(1, n + 1, dtype=float)
    weights /= weights.sum()
    return s.rolling(n).apply(lambda w: float(np.dot(w, weights)), raw=True)


def _delta(s: pd.Series, n: int) -> pd.Series:
    return s - s.shift(n)


def _ts_corr(x: pd.Series, y: pd.Series, n: int) -> pd.Series:
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1)
    return df.groupby(level="vt_symbol", group_keys=False).apply(
        lambda d: d["x"].rolling(n).corr(d["y"])
    )


def _rank(s: pd.Series) -> pd.Series:
    return s.groupby(level="timestamp").rank(pct=True)


_FUNCS: dict[str, Any] = {
    "Ts_Mean": lambda x, n: _ts_op(x, int(n), _ts_mean),
    "Ts_Std": lambda x, n: _ts_op(x, int(n), _ts_std),
    "Ts_Sum": lambda x, n: _ts_op(x, int(n), _ts_sum),
    "Decay_Linear": lambda x, n: _ts_op(x, int(n), _decay_linear),
    "Delta": lambda x, n: _ts_op(x, int(n), _delta),
    "Ts_Corr": lambda x, y, n: _ts_corr(x, y, int(n)),
    "Rank": _rank,
    "Log": lambda x: np.log(x.replace(0, np.nan)),
    "Abs": lambda x: x.abs(),
    "Sign": lambda x: np.sign(x),
}


class FactorEngine:
    """Evaluate factor expressions over a long-format panel.

    Panel must have a 2-level index ``(vt_symbol, timestamp)`` and the
    columns referenced by the expression (e.g. ``open``, ``high``,
    ``low``, ``close``, ``volume``, etc.).
    """

    def __init__(self, panel: pd.DataFrame) -> None:
        if not isinstance(panel.index, pd.MultiIndex) or panel.index.names != ["vt_symbol", "timestamp"]:
            raise ValueError(
                "FactorEngine expects a panel indexed by ('vt_symbol', 'timestamp')"
            )
        self.panel = panel.sort_index()

    def evaluate(self, expression: str) -> pd.Series:
        """Evaluate ``expression`` and return a pd.Series aligned to ``panel.index``."""
        tree = ast.parse(expression, mode="eval")
        return self._eval(tree.body)

    def evaluate_many(self, expressions: dict[str, str]) -> pd.DataFrame:
        """Evaluate multiple named factors at once.

        ``expressions`` maps factor name → DSL string. Returns a DataFrame
        with one column per factor.
        """
        out = {}
        for name, expr in expressions.items():
            out[name] = self.evaluate(expr)
        return pd.DataFrame(out)

    def _eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.panel.columns:
                return self.panel[node.id]
            raise KeyError(f"Unknown column: {node.id}; have {list(self.panel.columns)}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._eval(node.operand)
        if isinstance(node, ast.BinOp):
            op = _BINOPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
            return op(self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            result = None
            for op, right_node in zip(node.ops, node.comparators, strict=False):
                right = self._eval(right_node)
                cmp = _CMPOPS.get(type(op))
                if cmp is None:
                    raise ValueError(f"Unsupported compare op: {type(op).__name__}")
                cur = cmp(left, right)
                result = cur if result is None else (result & cur)
                left = right
            return result
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Factor functions must be referenced by name")
            fn = _FUNCS.get(node.func.id)
            if fn is None:
                raise KeyError(f"Unknown factor function: {node.func.id}; known={list(_FUNCS)}")
            args = [self._eval(a) for a in node.args]
            return fn(*args)
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def panel_from_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Convert tidy bars (``vt_symbol, timestamp, ohlcv``) to a panel."""
    df = bars.copy()
    df = df.set_index(["vt_symbol", "timestamp"]).sort_index()
    return df


__all__ = ["FactorEngine", "panel_from_bars"]
