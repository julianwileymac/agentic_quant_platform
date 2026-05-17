"""Deterministic-random dataset pipeline smoke from the four-source cache."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests.four_source_random import SELECTED_ASSETS, SEED, pick_assets


def test_pipeline_selection_manifest_is_stable() -> None:
    assert pick_assets(SEED) == SELECTED_ASSETS
    assert SELECTED_ASSETS["pipeline"] == "finrl_fundamentals_panel_sample"


def test_selected_pipeline_dispatch_and_ingest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from aqp.data.dataset_presets import get_preset
    from aqp.data.pipelines import dataset_preset_pipelines as pipelines
    from aqp.tasks.dataset_preset_tasks import _TASKS_BY_PRESET, dispatch_preset_ingest

    selected = SELECTED_ASSETS["pipeline"]
    preset = get_preset(selected)
    assert selected in _TASKS_BY_PRESET
    assert selected in preset.ingestion_task

    captured_kwargs: dict[str, object] = {}

    class _DummyAsyncResult:
        id = "task-random-four-source"

    def _fake_delay(**kwargs):
        captured_kwargs.update(kwargs)
        return _DummyAsyncResult()

    monkeypatch.setattr(_TASKS_BY_PRESET[selected], "delay", _fake_delay)
    queued = dispatch_preset_ingest(selected, csv_path="sample.csv")
    assert getattr(queued, "id", None) == "task-random-four-source"
    assert captured_kwargs.get("csv_path") == "sample.csv"

    def _fake_write(identifier: str, df: pd.DataFrame) -> dict[str, object]:
        return {
            "status": "ok",
            "rows": len(df),
            "iceberg_identifier": identifier,
            "columns": list(df.columns),
        }

    monkeypatch.setattr(pipelines, "_write_to_iceberg", _fake_write)

    if selected == "finrl_fundamentals_panel_sample":
        csv_path = tmp_path / "fundamentals.csv"
        pd.DataFrame(
            {
                "datadate": ["2024-01-31", "2024-01-31", "2024-02-29"],
                "ticker": ["AAPL", "MSFT", "AAPL"],
                "close": [182.3, 411.8, 187.1],
                "volume": [1000, 1200, 1100],
                "revenue_growth": ["0.12", "0.08", "0.11"],
                "y_return": [0.01, -0.02, 0.03],
            }
        ).to_csv(csv_path, index=False)
        result = pipelines.ingest_finrl_fundamentals_panel_sample(csv_path=str(csv_path))
    elif selected == "quant_trading_oil_money_sample":
        csv_path = tmp_path / "oil_money.csv"
        pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "uso": [70.0, 71.2, 70.8],
                "fxc": [24.1, 24.0, 24.3],
            }
        ).to_csv(csv_path, index=False)
        result = pipelines.ingest_quant_oil_money_sample(csv_path=str(csv_path))
    else:
        pytest.skip(f"selected pipeline {selected!r} is network-bound in this hermetic test")

    assert result["status"] == "ok"
    assert result["rows"] > 0
    assert result["iceberg_identifier"] == preset.iceberg_identifier
