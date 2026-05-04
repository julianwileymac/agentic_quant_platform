"""Tests for ML preprocessing as data-pipeline nodes."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def small_arrow_batches():
    pa = pytest.importorskip("pyarrow")
    df = pd.DataFrame(
        {
            "vt_symbol": ["AAA"] * 100,
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="D"),
            "close": np.linspace(100.0, 200.0, 100),
            "volume": np.linspace(1000.0, 2000.0, 100),
        }
    )
    table = pa.Table.from_pandas(df, preserve_index=False)
    return list(table.to_batches(max_chunksize=25))


def _ctx() -> object:
    from aqp.data.engine.nodes import NodeContext

    return NodeContext(
        pipeline_id="p", run_id="r", node_name="n", node_index=0
    )


def test_ml_preprocessing_inline_processors(small_arrow_batches) -> None:
    pa = pytest.importorskip("pyarrow")
    from aqp.data.fetchers.transforms.ml_preprocessing import MlPreprocessingTransform

    node = MlPreprocessingTransform(
        processors=[
            {
                "class": "Fillna",
                "module_path": "aqp.ml.processors",
                "kwargs": {"value": 0.0},
            }
        ],
        fit=True,
    )
    out_batches = list(node.transform(small_arrow_batches, _ctx()))
    assert all(isinstance(b, pa.RecordBatch) for b in out_batches)
    out = pa.Table.from_batches(out_batches).to_pandas()
    assert len(out) == 100
    assert "close" in out.columns


def test_ml_preprocessing_no_processors_passthrough(small_arrow_batches) -> None:
    pa = pytest.importorskip("pyarrow")
    from aqp.data.fetchers.transforms.ml_preprocessing import MlPreprocessingTransform

    node = MlPreprocessingTransform(processors=[])
    out = list(node.transform(small_arrow_batches, _ctx()))
    # No-op: same number of rows
    out_table = pa.Table.from_batches(out)
    assert out_table.num_rows == 100


def test_ml_preprocessing_specialised_node_register() -> None:
    from aqp.data.engine.registry import get_node_class

    cls = get_node_class("transform.ml_scale")
    assert cls is not None
    cls = get_node_class("transform.ml_pyod_outliers")
    assert cls is not None


def test_pipeline_recipe_materialise_node_spec(in_memory_db) -> None:
    """Saved PipelineRecipe -> manifest NodeSpec fragment."""
    from aqp.ml.pipeline_recipes import materialise_node_spec
    from aqp.persistence.db import get_session
    from aqp.persistence.models import PipelineRecipe

    with get_session() as session:
        row = PipelineRecipe(
            name="my-recipe",
            shared_processors=[
                {
                    "class": "Fillna",
                    "module_path": "aqp.ml.processors",
                    "kwargs": {"value": 0.0},
                }
            ],
            infer_processors=[],
            learn_processors=[],
            fit_window={},
            tags=[],
            is_active=True,
        )
        session.add(row)
        session.flush()
        recipe_id = row.id

    spec = materialise_node_spec(recipe_id)
    assert spec["name"] == "transform.ml_preprocessing"
    assert spec["kwargs"]["recipe_id"] == recipe_id
    assert spec["kwargs"]["fit"] is True


def test_ml_feature_snapshot_sink_register() -> None:
    from aqp.data.engine.registry import get_node_class

    cls = get_node_class("sink.ml_feature_snapshot")
    assert cls is not None
