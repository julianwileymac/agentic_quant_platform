"""Qlib-inspired symbolic feature DSL.

A tiny expression evaluator that lets a strategy or the LLM author features
declaratively, e.g.::

    "Rank( Ref($close, 1) / $close - 1 )"
    "Mean($volume, 20)"
    "Greater($close, Ref($close, 1))"
    "If(Gt($close, $open), 1.0, -1.0)"
    "Slope($close, 20) * Std($close, 20)"

An :class:`Expression` is evaluated against a tidy bars frame grouped by
``vt_symbol``. Only a curated operator set is enabled to keep eval safe.

Reference for the operator list:
``inspiration/qlib-main/qlib/data/ops.py`` — the ``OpsList`` registry.
"""
from __future__ import annotations

import ast
import operator
from collections.abc import Callable

import numpy as np
import pandas as pd


class ExpressionError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Primitive operators — organised in families to mirror qlib's ``OpsList``.
# ---------------------------------------------------------------------------


# --- unary / element-wise ---------------------------------------------------

def _ref(series: pd.Series, n: int) -> pd.Series:
    return series.shift(int(n))


def _delta(series: pd.Series, n: int) -> pd.Series:
    return series - series.shift(int(n))


def _abs(series: pd.Series) -> pd.Series:
    return series.abs()


def _sign(series: pd.Series) -> pd.Series:
    return np.sign(series)


def _log(series: pd.Series) -> pd.Series:
    return np.log(series.clip(lower=1e-12))


def _power(series: pd.Series, n: float) -> pd.Series:
    return np.power(series, float(n))


def _rank(series: pd.Series) -> pd.Series:
    return series.rank(pct=True)


# --- rolling aggregations ---------------------------------------------------


def _mean(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).mean()


def _std(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).std(ddof=0)


def _var(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).var(ddof=0)


def _skew(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).skew()


def _kurt(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).kurt()


def _sum(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).sum()


def _min(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).min()


def _max(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).max()


def _med(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).median()


def _mad(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))) if len(x) else np.nan,
        raw=True,
    )


def _quantile(series: pd.Series, n: int, q: float = 0.5) -> pd.Series:
    return series.rolling(int(n)).quantile(float(q))


def _count(series: pd.Series, n: int) -> pd.Series:
    """Rolling count of non-zero / True values (qlib semantics)."""
    return series.rolling(int(n)).apply(lambda x: int(np.sum(np.asarray(x, dtype=bool))), raw=True)


def _idxmax(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).apply(lambda x: float(np.argmax(x)), raw=True)


def _idxmin(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).apply(lambda x: float(np.argmin(x)), raw=True)


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=int(n), adjust=False).mean()


def _wma(series: pd.Series, n: int) -> pd.Series:
    n = int(n)
    weights = np.arange(1, n + 1)
    return series.rolling(n).apply(lambda x: float(np.dot(x, weights) / weights.sum()), raw=True)


def _slope(series: pd.Series, n: int) -> pd.Series:
    """Rolling OLS slope of ``series`` on a time index of ``0..n-1``."""
    n = int(n)

    def _f(window: np.ndarray) -> float:
        x = np.arange(len(window), dtype=float)
        y = np.asarray(window, dtype=float)
        xm = x.mean()
        ym = y.mean()
        denom = ((x - xm) ** 2).sum()
        return float(((x - xm) * (y - ym)).sum() / denom) if denom else float("nan")

    return series.rolling(n).apply(_f, raw=True)


def _rsquare(series: pd.Series, n: int) -> pd.Series:
    n = int(n)

    def _f(window: np.ndarray) -> float:
        x = np.arange(len(window), dtype=float)
        y = np.asarray(window, dtype=float)
        xm = x.mean()
        ym = y.mean()
        num = ((x - xm) * (y - ym)).sum() ** 2
        denom = ((x - xm) ** 2).sum() * ((y - ym) ** 2).sum()
        return float(num / denom) if denom else float("nan")

    return series.rolling(n).apply(_f, raw=True)


def _resi(series: pd.Series, n: int) -> pd.Series:
    """Residual of the last value vs the rolling OLS fit over ``n`` bars."""
    n = int(n)

    def _f(window: np.ndarray) -> float:
        x = np.arange(len(window), dtype=float)
        y = np.asarray(window, dtype=float)
        xm = x.mean()
        ym = y.mean()
        denom = ((x - xm) ** 2).sum()
        if not denom:
            return float("nan")
        slope = ((x - xm) * (y - ym)).sum() / denom
        intercept = ym - slope * xm
        pred_last = slope * (len(window) - 1) + intercept
        return float(y[-1] - pred_last)

    return series.rolling(n).apply(_f, raw=True)


# --- pairwise operators -----------------------------------------------------


def _corr(a: pd.Series, b: pd.Series, n: int) -> pd.Series:
    return a.rolling(int(n)).corr(b)


def _cov(a: pd.Series, b: pd.Series, n: int) -> pd.Series:
    return a.rolling(int(n)).cov(b)


# --- comparison operators ---------------------------------------------------


def _greater(a: pd.Series, b: pd.Series | float) -> pd.Series:
    return (a > b).astype(float)


def _less(a: pd.Series, b: pd.Series | float) -> pd.Series:
    return (a < b).astype(float)


def _gt(a, b):
    return _greater(a, b)


def _ge(a, b):
    return (a >= b).astype(float)


def _lt(a, b):
    return _less(a, b)


def _le(a, b):
    return (a <= b).astype(float)


def _eq(a, b):
    return (a == b).astype(float)


def _ne(a, b):
    return (a != b).astype(float)


# --- logical operators ------------------------------------------------------


def _and(a, b):
    return (pd.Series(a).astype(bool) & pd.Series(b).astype(bool)).astype(float)


def _or(a, b):
    return (pd.Series(a).astype(bool) | pd.Series(b).astype(bool)).astype(float)


def _not(a):
    return (~pd.Series(a).astype(bool)).astype(float)


# --- conditional operators --------------------------------------------------


def _mask(series, condition, value):
    """Return ``value`` where ``condition`` is truthy, else the original series."""
    out = pd.Series(series, copy=True)
    mask = pd.Series(condition).astype(bool)
    out = out.where(~mask, other=value)
    return out


def _if(cond, a, b):
    """Element-wise ternary: ``cond ? a : b``."""
    cond_s = pd.Series(cond).astype(bool)
    a_s = a if isinstance(a, pd.Series) else pd.Series([a] * len(cond_s), index=cond_s.index)
    b_s = b if isinstance(b, pd.Series) else pd.Series([b] * len(cond_s), index=cond_s.index)
    return pd.Series(np.where(cond_s, a_s, b_s), index=cond_s.index)


# --- add / sub / mul / div as explicit ops ----------------------------------


def _add(a, b):
    return a + b


def _sub(a, b):
    return a - b


def _mul(a, b):
    return a * b


def _div(a, b):
    return a / b


OPERATORS: dict[str, Callable] = {
    # Unary element-wise.
    "Ref": _ref,
    "Delta": _delta,
    "Abs": _abs,
    "Sign": _sign,
    "Log": _log,
    "Power": _power,
    "Rank": _rank,
    # Rolling aggregations.
    "Mean": _mean,
    "Std": _std,
    "Var": _var,
    "Skew": _skew,
    "Kurt": _kurt,
    "Sum": _sum,
    "Min": _min,
    "Max": _max,
    "Med": _med,
    "Mad": _mad,
    "Quantile": _quantile,
    "Count": _count,
    "IdxMax": _idxmax,
    "IdxMin": _idxmin,
    "EMA": _ema,
    "WMA": _wma,
    "Slope": _slope,
    "Rsquare": _rsquare,
    "Resi": _resi,
    # Pairwise rolling.
    "Corr": _corr,
    "Cov": _cov,
    # Comparison.
    "Greater": _greater,
    "Less": _less,
    "Gt": _gt,
    "Ge": _ge,
    "Lt": _lt,
    "Le": _le,
    "Eq": _eq,
    "Ne": _ne,
    # Logical.
    "And": _and,
    "Or": _or,
    "Not": _not,
    # Conditional.
    "Mask": _mask,
    "If": _if,
    # Explicit arithmetic (allows chaining in parentheses-heavy YAMLs).
    "Add": _add,
    "Sub": _sub,
    "Mul": _mul,
    "Div": _div,
}


# --- Expression object -----------------------------------------------------


class Expression:
    """Compile + evaluate a formula string against one symbol's bars frame."""

    def __init__(self, formula: str) -> None:
        self.formula = formula.strip()
        self._tree = self._parse(self.formula)
        self._validate(self._tree.body)

    @staticmethod
    def _parse(formula: str) -> ast.AST:
        clean = formula.replace("$", "FIELD_")
        try:
            return ast.parse(clean, mode="eval")
        except SyntaxError as e:  # pragma: no cover
            raise ExpressionError(f"Invalid expression {formula!r}: {e}") from e

    @staticmethod
    def _validate(node: ast.AST) -> None:
        """Walk the AST up-front and reject unknown operator names/types."""
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                name = getattr(sub.func, "id", None)
                if name not in OPERATORS:
                    raise ExpressionError(f"Disallowed operator: {name}")
            elif isinstance(sub, ast.BinOp) and type(sub.op) not in _BINOPS:
                raise ExpressionError(f"Disallowed binop: {type(sub.op).__name__}")
            elif isinstance(sub, ast.UnaryOp) and not isinstance(sub.op, (ast.USub, ast.UAdd)):
                raise ExpressionError(f"Disallowed unary op: {type(sub.op).__name__}")
            elif isinstance(sub, (ast.Attribute, ast.Subscript, ast.Lambda, ast.IfExp)):
                raise ExpressionError(f"Unsupported AST node: {type(sub).__name__}")

    def evaluate(self, bars: pd.DataFrame) -> pd.Series:
        """Evaluate on a single-symbol dataframe (must be sorted by timestamp)."""
        env = {
            f"FIELD_{c}": bars[c] for c in ("open", "high", "low", "close", "volume") if c in bars
        }
        # Also expose common aliases like ``$vwap`` using (close+high+low)/3.
        if "close" in bars and "high" in bars and "low" in bars:
            env["FIELD_vwap"] = (bars["close"] + bars["high"] + bars["low"]) / 3.0
        return self._eval_node(self._tree.body, env)

    def _eval_node(self, node: ast.AST, env: dict) -> pd.Series | float:
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, "id", None)
            if func_name not in OPERATORS:
                raise ExpressionError(f"Disallowed operator: {func_name}")
            args = [self._eval_node(a, env) for a in node.args]
            return OPERATORS[func_name](*args)
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, env)
            right = self._eval_node(node.right, env)
            op = _BINOPS.get(type(node.op))
            if op is None:
                raise ExpressionError(f"Disallowed binop: {type(node.op).__name__}")
            return op(left, right)
        if isinstance(node, ast.UnaryOp):
            value = self._eval_node(node.operand, env)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return +value
            raise ExpressionError(f"Disallowed unary op: {type(node.op).__name__}")
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ExpressionError(f"Unknown field: {node.id}")
            return env[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        raise ExpressionError(f"Unsupported AST node: {type(node).__name__}")

    def __call__(self, bars: pd.DataFrame) -> pd.Series:
        return self.evaluate(bars)

    def __repr__(self) -> str:
        return f"Expression({self.formula!r})"


_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}


def compute(formula: str, bars: pd.DataFrame) -> pd.DataFrame:
    """Evaluate a formula across all symbols in a long-format bars frame."""
    expr = Expression(formula)
    out = []
    for vt_symbol, sub in bars.sort_values("timestamp").groupby("vt_symbol", sort=False):
        values = expr(sub)
        if isinstance(values, (int, float)):
            values = pd.Series([values] * len(sub), index=sub.index)
        out.append(
            pd.DataFrame(
                {"timestamp": sub["timestamp"].values, "vt_symbol": vt_symbol, formula: values.values}
            )
        )
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def registered_operators() -> list[str]:
    """Introspection helper used by the UI + docs."""
    return sorted(OPERATORS)
