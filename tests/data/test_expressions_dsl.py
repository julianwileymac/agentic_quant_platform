"""Hermetic tests for the symbolic alpha DSL AST sandbox."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aqp.data.expressions_dsl import (
    FactorNode,
    SymbolicAlphaError,
    compile_to_factor_node,
)


def _bars(n=30, seed=7):
    rng = np.random.default_rng(seed)
    close = 100.0
    rows = []
    for d in range(n):
        ret = rng.normal(0.001, 0.012)
        close *= (1 + ret)
        rows.append({
            "open": close * (1 + rng.normal(0, 0.001)),
            "high": close * (1 + abs(rng.normal(0, 0.003))),
            "low": close * (1 - abs(rng.normal(0, 0.003))),
            "close": close,
            "volume": float(rng.integers(1_000_000, 5_000_000)),
        })
    return pd.DataFrame(rows)


def test_compile_simple_formula():
    factor = compile_to_factor_node("EMA($close, 12) - EMA($close, 26)")
    assert isinstance(factor, FactorNode)
    series = factor.compute(_bars())
    assert isinstance(series, pd.Series)
    assert len(series) == 30
    assert "EMA" in factor.used_operators
    assert "close" in factor.used_fields


def test_compile_with_arithmetic_and_unary():
    factor = compile_to_factor_node("-Sign(Mean($returns, 5)) * Rank(Std($close, 20))")
    series = factor.compute(_bars())
    assert len(series) == 30


def test_sandbox_rejects_import():
    with pytest.raises(SymbolicAlphaError, match="Disallowed call"):
        compile_to_factor_node("__import__('os').system('echo pwn')")


def test_sandbox_rejects_attribute_access():
    with pytest.raises(SymbolicAlphaError, match="Forbidden AST"):
        compile_to_factor_node("$close.attr_access")


def test_sandbox_rejects_subscript():
    with pytest.raises(SymbolicAlphaError, match="Forbidden AST"):
        compile_to_factor_node("$close[0]")


def test_sandbox_rejects_lambda():
    with pytest.raises(SymbolicAlphaError, match="Forbidden AST"):
        compile_to_factor_node("lambda x: x")


def test_sandbox_rejects_list_literal():
    with pytest.raises(SymbolicAlphaError, match="Forbidden AST"):
        compile_to_factor_node("[1, 2, 3]")


def test_sandbox_rejects_dict_literal():
    with pytest.raises(SymbolicAlphaError, match="Forbidden AST"):
        compile_to_factor_node("{'a': 1}")


def test_sandbox_rejects_unknown_operator():
    with pytest.raises(SymbolicAlphaError, match="Unknown operator"):
        compile_to_factor_node("UnknownOp($close)")


def test_sandbox_rejects_unknown_field():
    with pytest.raises(SymbolicAlphaError, match="Unknown symbol field"):
        compile_to_factor_node("$nonexistent_field")


def test_sandbox_rejects_keyword_args():
    with pytest.raises(SymbolicAlphaError, match="Keyword"):
        compile_to_factor_node("EMA($close, period=12)")


def test_sandbox_rejects_comprehension():
    with pytest.raises(SymbolicAlphaError, match="Forbidden AST"):
        compile_to_factor_node("Sum([$close, $high])")


def test_panel_compute_multi_symbol():
    factor = compile_to_factor_node("EMA($close, 5)")
    rng = np.random.default_rng(3)
    rows = []
    for tic in ("A", "B", "C"):
        close = 100.0
        for d in range(20):
            close *= (1 + rng.normal(0, 0.01))
            rows.append({
                "date": pd.Timestamp("2024-01-02") + pd.Timedelta(days=d),
                "tic": tic,
                "open": close, "high": close * 1.01, "low": close * 0.99,
                "close": close, "volume": 1_000_000.0,
            })
    panel = pd.DataFrame(rows)
    wide = factor.compute_panel(panel)
    assert set(wide.columns) == {"A", "B", "C"}
    assert len(wide) == 20


def test_empty_formula_rejected():
    with pytest.raises(SymbolicAlphaError, match="Empty"):
        compile_to_factor_node("")


def test_division_by_zero_caught():
    factor = compile_to_factor_node("Mean($close, 5) / 0")
    with pytest.raises(SymbolicAlphaError, match="Division by zero"):
        factor.compute(_bars())
