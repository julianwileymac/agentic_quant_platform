"""Smoke tests for aqp.data (feature engineer + expressions + ingestion writer)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aqp.data.expressions import Expression, compute
from aqp.data.feature_engineer import FeatureEngineer
from aqp.data.ingestion import dataset_hash, write_parquet


def test_feature_engineer_adds_indicators(synthetic_bars: pd.DataFrame) -> None:
    fe = FeatureEngineer(indicators=["sma_20", "rsi_14", "macd"])
    out = fe.transform(synthetic_bars)
    assert "sma_20" in out.columns
    assert "rsi_14" in out.columns
    assert "macd" in out.columns
    assert len(out) == len(synthetic_bars)


def test_expression_ref_mean(synthetic_bars: pd.DataFrame) -> None:
    sub = synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].reset_index(drop=True)
    expr = Expression("Mean($close, 10)")
    values = expr(sub)
    assert isinstance(values, pd.Series)
    assert len(values) == len(sub)


def test_expression_rank(synthetic_bars: pd.DataFrame) -> None:
    out = compute("Rank($close)", synthetic_bars.head(100))
    assert not out.empty
    assert "Rank($close)" in out.columns


def test_write_parquet_and_hash(tmp_path: Path, synthetic_bars: pd.DataFrame) -> None:
    out = write_parquet(synthetic_bars.head(200), parquet_dir=tmp_path, overwrite=True)
    assert out.exists()
    files = list(out.glob("*.parquet"))
    assert len(files) > 0
    h = dataset_hash(synthetic_bars.head(200))
    assert isinstance(h, str) and len(h) == 64


def test_expression_rejects_unknown_operator() -> None:
    with pytest.raises(Exception):
        Expression("Eval($close)")
