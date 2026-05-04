"""Tests for the expanded aqp.ml.flows catalog."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


class _FakeDataset:
    """Minimal Dataset double mirroring DatasetH.prepare(segment, col_set=...)."""

    def __init__(self) -> None:
        rng = np.random.default_rng(42)
        n = 200
        # Use a (datetime, vt_symbol) MultiIndex to match what predict_to_series
        # expects. We use a single symbol for simplicity.
        timestamps = pd.date_range("2024-01-01", periods=n, freq="D")
        midx = pd.MultiIndex.from_product(
            [timestamps, ["AAA"]], names=["datetime", "vt_symbol"]
        )
        features = pd.DataFrame(
            rng.normal(size=(n, 4)),
            index=midx,
            columns=["f1", "f2", "f3", "f4"],
        )
        labels = (
            2.0 * features["f1"]
            - 0.5 * features["f2"]
            + 0.1 * rng.normal(size=n)
        ).rename("label")
        # Build a multi-column frame matching the (feature, label) split contract
        feat = features.copy()
        feat.columns = pd.MultiIndex.from_product([["feature"], features.columns])
        lab = labels.to_frame()
        lab.columns = pd.MultiIndex.from_product([["label"], ["label"]])
        self._frame = pd.concat([feat, lab], axis=1)
        self._labels = labels

    def prepare(self, segment, col_set=None, data_key=None):
        if col_set == "label":
            return self._labels
        if col_set == "feature":
            return self._frame["feature"]
        return self._frame


def _patched_build(monkeypatch) -> _FakeDataset:
    fake = _FakeDataset()

    def _build(cfg):
        return fake

    monkeypatch.setattr("aqp.ml.flows.build_from_config", _build)
    return fake


def test_list_flows_catalog() -> None:
    from aqp.ml.flows import list_flows

    catalog = list_flows()
    flows = {entry["flow"] for entry in catalog}
    expected = {
        "linear",
        "decomposition",
        "forecast",
        "regression_diagnostics",
        "unit_root",
        "acf_pacf",
        "granger_causality",
        "cointegration",
        "garch",
        "change_point",
        "clustering",
        "pca_summary",
    }
    assert expected.issubset(flows)


def test_run_linear_flow_validates_estimator(monkeypatch) -> None:
    from aqp.ml.flows import run_linear_flow

    _patched_build(monkeypatch)
    with pytest.raises(ValueError):
        run_linear_flow({"class": "X"}, estimator="not-real")


def test_run_linear_flow_smoke(monkeypatch) -> None:
    pytest.importorskip("sklearn")
    from aqp.ml.flows import run_linear_flow

    _patched_build(monkeypatch)
    result = run_linear_flow({"class": "X"}, estimator="ridge", segment="train")
    assert result.flow == "linear"
    assert "n_predictions" in result.metrics
    assert isinstance(result.rows, list)


def test_run_pca_summary_flow(monkeypatch) -> None:
    pytest.importorskip("sklearn")
    from aqp.ml.flows import run_pca_summary_flow

    _patched_build(monkeypatch)
    result = run_pca_summary_flow({"class": "X"}, segment="train", n_components=3)
    assert result.flow == "pca_summary"
    assert result.metrics["n_components"] == 3
    assert len(result.rows) == 3
    # Cumulative variance is monotone non-decreasing.
    cum = [row["cumulative_variance"] for row in result.rows]
    assert cum == sorted(cum)


def test_run_clustering_kmeans(monkeypatch) -> None:
    pytest.importorskip("sklearn")
    from aqp.ml.flows import run_clustering_flow

    _patched_build(monkeypatch)
    result = run_clustering_flow(
        {"class": "X"}, segment="train", backend="kmeans", n_clusters=3
    )
    assert result.flow == "clustering"
    assert result.metrics["backend"] == "kmeans"
    assert result.metrics["n_clusters"] == 3


def test_run_unit_root_flow(monkeypatch) -> None:
    pytest.importorskip("statsmodels")
    from aqp.ml.flows import run_unit_root_flow

    _patched_build(monkeypatch)
    out = run_unit_root_flow({"class": "X"}, segment="train", test="adf")
    assert out.flow == "unit_root"
    assert "adf_stat" in out.metrics


def test_run_acf_pacf_flow(monkeypatch) -> None:
    pytest.importorskip("statsmodels")
    from aqp.ml.flows import run_acf_pacf_flow

    _patched_build(monkeypatch)
    out = run_acf_pacf_flow({"class": "X"}, segment="train", nlags=5)
    assert out.flow == "acf_pacf"
    assert len(out.rows) >= 1


def test_run_flow_dispatch_unknown() -> None:
    from aqp.ml.flows import run_flow

    with pytest.raises(ValueError):
        run_flow("nonexistent", {})
