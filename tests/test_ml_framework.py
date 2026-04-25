"""Tests for the native aqp.ml framework."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest


def test_ml_base_classes_exposed() -> None:
    from aqp.ml import DataHandler, DataHandlerLP, DatasetH, Model, ModelFT

    assert issubclass(DataHandlerLP, DataHandler)
    assert issubclass(ModelFT, Model)
    assert callable(DatasetH)


def test_expressions_new_operators() -> None:
    from aqp.data.expressions import OPERATORS

    for op in ["Var", "Skew", "Kurt", "Med", "Quantile", "Slope", "Rsquare", "Resi", "EMA", "WMA", "Cov", "If", "Mask"]:
        assert op in OPERATORS, f"missing operator {op}"


def test_alpha158_expression_count() -> None:
    from aqp.ml.features.alpha158 import Alpha158DL

    exprs, names = Alpha158DL.get_feature_config()
    assert len(exprs) == len(names)
    # 9 kbar + 4 price * 1 window + 1 volume + 30 rolling families * 5 windows
    assert len(exprs) >= 100


def test_alpha360_expression_count() -> None:
    from aqp.ml.features.alpha360 import Alpha360DL

    exprs, names = Alpha360DL.get_feature_config(n_steps=60)
    assert len(exprs) == 360
    assert any(n.startswith("CLOSE") for n in names)
    assert any(n.startswith("VOLUME") for n in names)


def test_dataset_h_prepare_with_static_loader(synthetic_bars) -> None:
    from aqp.ml.dataset import DatasetH
    from aqp.ml.handler import DataHandlerLP
    from aqp.ml.loader import StaticDataLoader

    # Static data loader bypasses DuckDB so we can exercise the contract.
    df = synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].copy()
    df["feature_close"] = df["close"] / df["close"].shift(1) - 1
    df["label_fwd"] = df["feature_close"].shift(-1)
    df = df.dropna()
    loader = StaticDataLoader(df[["timestamp", "vt_symbol", "feature_close", "label_fwd"]])

    handler = DataHandlerLP(
        instruments=["AAA.NASDAQ"],
        start_time="2021-01-01",
        end_time="2023-12-29",
        data_loader=loader,
    )
    handler.setup_data()
    assert handler._data is not None
    assert isinstance(handler._data.index, pd.MultiIndex)

    dataset = DatasetH(
        handler=handler,
        segments={"train": ["2021-01-01", "2022-12-31"], "test": ["2023-01-01", "2023-12-29"]},
    )
    train = dataset.prepare("train")
    test = dataset.prepare("test")
    assert not train.empty
    assert not test.empty


def test_linear_model_fits_small_dataset(synthetic_bars) -> None:
    from aqp.ml.dataset import DatasetH
    from aqp.ml.handler import DataHandlerLP
    from aqp.ml.loader import StaticDataLoader
    from aqp.ml.models.linear import LinearModel

    df = synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].copy()
    df["feature_close"] = df["close"].pct_change()
    df["feature_vol"] = df["volume"].pct_change()
    df["label_fwd"] = df["feature_close"].shift(-1)
    df = df.dropna()
    loader = StaticDataLoader(df[["timestamp", "vt_symbol", "feature_close", "feature_vol", "label_fwd"]])
    handler = DataHandlerLP(instruments=["AAA.NASDAQ"], data_loader=loader)
    handler.setup_data()
    ds = DatasetH(
        handler=handler,
        segments={"train": ["2021-01-01", "2022-06-30"], "test": ["2022-07-01", "2023-12-29"]},
    )
    model = LinearModel(estimator="ridge", alpha=1.0)
    model.fit(ds)
    pred = model.predict(ds, segment="test")
    assert isinstance(pred, pd.Series)
    assert len(pred) > 0


def test_tree_model_registered_but_guarded() -> None:
    """The decorator-registered LGBModel should appear in the registry."""
    from aqp.core.registry import list_registered

    # Import triggers registration.
    from aqp.ml.models import tree as _tree  # noqa: F401

    assert "LGBModel" in list_registered()
    assert "XGBModel" in list_registered()


def test_tier_b_stubs_raise_not_implemented() -> None:
    from aqp.ml.models.torch.stubs import HISTModel

    model = HISTModel()
    with pytest.raises(NotImplementedError):
        model.fit(None)
