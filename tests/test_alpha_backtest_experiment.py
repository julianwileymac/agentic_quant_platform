"""Hermetic tests for AlphaBacktestExperiment.

These tests stub out MLflow + the heavy backtest runner so we can
verify the orchestrator's wiring (parent run, train + register +
deploy + backtest dispatch, metric rollup, persistence) without
touching MLflow, Iceberg, or DuckDB.
"""
from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest


class _FakeDataset:
    def __init__(self) -> None:
        idx = pd.date_range("2024-01-01", periods=100, freq="D")
        self._features = pd.DataFrame(
            np.random.default_rng(0).normal(size=(100, 3)),
            index=idx,
            columns=["f1", "f2", "f3"],
        )
        self._labels = pd.Series(
            np.random.default_rng(1).normal(size=100), index=idx, name="label"
        )

    def prepare(self, segment, col_set: str | None = None):
        if col_set == "label":
            return self._labels
        return pd.concat([self._features, self._labels.rename("label")], axis=1)


class _FakeModel:
    """Minimal Model double — returns a noisy version of the labels."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def fit(self, dataset):
        self._dataset = dataset
        return self

    def predict(self, dataset, segment="test"):
        labels = dataset.prepare(segment, col_set="label")
        rng = np.random.default_rng(2)
        return labels + rng.normal(scale=0.05, size=len(labels))

    def to_pickle(self, path):  # noqa: D401 - no-op, satisfies orchestrator
        from pathlib import Path

        Path(path).write_bytes(b"fake-model")


@contextmanager
def _fake_parent_run(*args, **kwargs):
    class _P:
        run_id = "fake-mlflow-parent"

        def log_metrics(self, metrics):
            self.last = metrics

    yield _P()


def test_alpha_backtest_experiment_smoke(monkeypatch, in_memory_db) -> None:
    """End-to-end smoke test with all heavy dependencies stubbed."""
    from aqp.ml import alpha_backtest_experiment as abe
    from aqp.mlops import mlflow_client

    # Stub MLflow parent + child run helpers
    monkeypatch.setattr(
        mlflow_client, "log_alpha_backtest_parent", _fake_parent_run
    )
    monkeypatch.setattr(
        mlflow_client, "ensure_experiment", lambda *a, **k: "exp-1"
    )
    monkeypatch.setattr(
        mlflow_client, "log_ml_experiment_run", lambda **k: "fake-train-run"
    )
    monkeypatch.setattr(
        "aqp.mlops.model_registry.register_alpha", lambda **k: "1"
    )
    # Stub the backtest dispatch so we don't need DuckDB or strategies.
    bt_called: dict = {}

    def _fake_backtest(cfg, run_name, persist=True, mlflow_log=True, strategy_id=None):
        bt_called["cfg"] = cfg
        return {
            "run_id": "fake-bt-row",
            "mlflow_run_id": "fake-mlflow-bt",
            "engine": "fake",
            "sharpe": 1.5,
            "sortino": 1.8,
            "max_drawdown": -0.1,
            "total_return": 0.2,
            "final_equity": 120000.0,
            "model_deployment_id": None,
        }

    monkeypatch.setattr(
        "aqp.backtest.runner.run_backtest_from_config", _fake_backtest
    )
    # Also need to bypass build_from_config so we don't try to instantiate
    # real classes — return a fake dataset / model when called.
    fake_dataset = _FakeDataset()
    fake_model = _FakeModel()

    def _fake_build(cfg):
        if not isinstance(cfg, dict):
            return cfg
        cls = cfg.get("class")
        if cls == "FakeDataset":
            return fake_dataset
        if cls == "FakeModel":
            return fake_model
        return None

    monkeypatch.setattr(
        "aqp.core.registry.build_from_config", _fake_build
    )
    monkeypatch.setattr(abe, "build_from_config", _fake_build)

    exp = abe.AlphaBacktestExperiment(
        dataset_cfg={"class": "FakeDataset"},
        model_cfg={"class": "FakeModel"},
        strategy_cfg={
            "class": "DummyStrategy",
            "kwargs": {"alpha_model": {"class": "DeployedModelAlpha"}},
        },
        backtest_cfg={"class": "DummyEngine", "kwargs": {}},
        run_name="smoke-alpha-backtest",
        train_first=True,
        capture_predictions=False,
        persist=True,
    )
    result = exp.run(task_id="t-smoke")

    assert result.status == "completed"
    assert result.mlflow_run_id == "fake-mlflow-parent"
    assert result.backtest_run_id == "fake-bt-row"
    assert result.trading_metrics["sharpe"] == 1.5
    assert "score" in result.combined_metrics
    assert bt_called, "backtest runner was not invoked"

    # MLAlphaBacktestRun row should be persisted
    from aqp.persistence.db import get_session
    from aqp.persistence.models import MLAlphaBacktestRun

    with get_session() as session:
        rows = session.query(MLAlphaBacktestRun).all()
        assert len(rows) == 1
        assert rows[0].status == "completed"
        assert rows[0].run_name == "smoke-alpha-backtest"


def test_alpha_backtest_experiment_requires_train_or_deployment() -> None:
    from aqp.ml.alpha_backtest_experiment import AlphaBacktestExperiment

    with pytest.raises(ValueError):
        AlphaBacktestExperiment(
            strategy_cfg={"class": "S"},
            backtest_cfg={"class": "B"},
            train_first=False,
            deployment_id=None,
        )


def test_alpha_backtest_experiment_requires_dataset_when_training() -> None:
    from aqp.ml.alpha_backtest_experiment import AlphaBacktestExperiment

    with pytest.raises(ValueError):
        AlphaBacktestExperiment(
            strategy_cfg={"class": "S"},
            backtest_cfg={"class": "B"},
            train_first=True,
            dataset_cfg={},
            model_cfg={"class": "M"},
        )
    with pytest.raises(ValueError):
        AlphaBacktestExperiment(
            strategy_cfg={"class": "S"},
            backtest_cfg={"class": "B"},
            train_first=True,
            dataset_cfg={"class": "D"},
            model_cfg={},
        )
