"""Persistence-layer tests for the new ML alpha-backtest tables."""
from __future__ import annotations

from datetime import datetime


def test_backtest_run_has_new_fk_columns(in_memory_db) -> None:
    """Alembic 0025 added four FK columns to backtest_runs."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models import BacktestRun

    with get_session() as session:
        row = BacktestRun(
            status="completed",
            sharpe=1.0,
            sortino=1.2,
            max_drawdown=-0.1,
            total_return=0.2,
            mlflow_run_id="mlf-1",
            dataset_hash="abcd",
            model_version_id=None,
            ml_experiment_run_id=None,
            experiment_plan_id=None,
            model_deployment_id=None,
            created_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            metrics={},
        )
        session.add(row)
        session.flush()
        assert row.id


def test_ml_alpha_backtest_run_persists(in_memory_db) -> None:
    from aqp.persistence.db import get_session
    from aqp.persistence.models import MLAlphaBacktestRun

    with get_session() as session:
        row = MLAlphaBacktestRun(
            run_name="abr-1",
            status="completed",
            ml_metrics={"ic_spearman": 0.5},
            trading_metrics={"sharpe": 1.0},
            combined_metrics={"score": 0.7},
            attribution={"available": False},
            mlflow_run_id="mlf-parent",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        row_id = row.id

    with get_session() as session:
        fetched = session.get(MLAlphaBacktestRun, row_id)
        assert fetched is not None
        assert fetched.run_name == "abr-1"
        assert fetched.combined_metrics["score"] == 0.7


def test_ml_prediction_audit_cascade(in_memory_db) -> None:
    from aqp.persistence.db import get_session
    from aqp.persistence.models import MLAlphaBacktestRun, MLPredictionAudit

    with get_session() as session:
        run = MLAlphaBacktestRun(
            run_name="abr-2",
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        session.add(run)
        session.flush()
        run_id = run.id

        for i in range(3):
            session.add(
                MLPredictionAudit(
                    alpha_backtest_run_id=run_id,
                    vt_symbol="AAA",
                    ts=datetime(2024, 1, 1),
                    prediction=float(i),
                )
            )

    with get_session() as session:
        rows = session.query(MLPredictionAudit).filter_by(
            alpha_backtest_run_id=run_id
        ).all()
        assert len(rows) == 3
