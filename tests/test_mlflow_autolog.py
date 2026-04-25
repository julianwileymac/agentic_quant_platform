"""Tests for the MLflow autolog helper functions (stub MLflow)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd


def test_log_paper_session_calls_mlflow(monkeypatch):
    from aqp.mlops import mlflow_client

    mlflow_mock = MagicMock()
    run_mock = MagicMock()
    run_mock.info.run_id = "paper-run"
    mlflow_mock.start_run.return_value.__enter__.return_value = run_mock
    mlflow_mock.start_run.return_value.__exit__.return_value = False
    monkeypatch.setattr(mlflow_client, "_client", lambda: mlflow_mock)
    monkeypatch.setattr(mlflow_client, "ensure_experiment", lambda *a, **kw: "exp-0")

    result = mlflow_client.log_paper_session(
        {"run_name": "t", "final_equity": 123.0, "bars_seen": 50},
        {"strategy": {"x": 1}},
    )
    assert result == "paper-run"
    mlflow_mock.start_run.assert_called()
    mlflow_mock.log_metric.assert_called()


def test_log_factor_run_handles_missing_stats(monkeypatch):
    from aqp.mlops import mlflow_client

    mlflow_mock = MagicMock()
    run_mock = MagicMock()
    run_mock.info.run_id = "factor-run"
    mlflow_mock.start_run.return_value.__enter__.return_value = run_mock
    mlflow_mock.start_run.return_value.__exit__.return_value = False
    monkeypatch.setattr(mlflow_client, "_client", lambda: mlflow_mock)
    monkeypatch.setattr(mlflow_client, "ensure_experiment", lambda *a, **kw: "exp-0")
    result = mlflow_client.log_factor_run(
        factor_name="rsi",
        ic_stats={"fwd_1": {"mean": 0.02, "ir": 0.3}},
        cumulative_returns=pd.DataFrame({"Q1": [0, 1, 2]}),
    )
    assert result == "factor-run"


def test_register_celery_signals_idempotent(monkeypatch):
    from aqp.mlops import autolog

    # Reset module state.
    autolog._registered_celery = False

    # First call should register, second should be a no-op.
    autolog.register_celery_signals()
    first_state = autolog._registered_celery
    autolog.register_celery_signals()
    assert autolog._registered_celery is first_state
