"""Split planning tests."""
from __future__ import annotations

import pandas as pd

from aqp.ml.dataset import materialize_segments
from aqp.ml.planning import build_split_plan


def _one_symbol(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame["vt_symbol"] == "AAA.NASDAQ"].copy().reset_index(drop=True)


def test_fixed_split_plan_is_deterministic(synthetic_bars: pd.DataFrame) -> None:
    frame = _one_symbol(synthetic_bars)
    config = {
        "segments": {
            "train": ["2021-01-01", "2022-12-30"],
            "valid": ["2023-01-02", "2023-06-30"],
            "test": ["2023-07-03", "2023-12-29"],
        }
    }
    artifacts_a, segments_a = build_split_plan(frame, method="fixed", config=config)
    artifacts_b, segments_b = build_split_plan(frame, method="fixed", config=config)
    assert segments_a == segments_b
    assert len(artifacts_a) == 3
    assert [a.indices for a in artifacts_a] == [b.indices for b in artifacts_b]


def test_purged_kfold_materializes_segments(synthetic_bars: pd.DataFrame) -> None:
    frame = _one_symbol(synthetic_bars)
    artifacts, segments = build_split_plan(
        frame,
        method="purged_kfold",
        config={"n_splits": 4, "embargo_days": 2},
    )
    assert artifacts
    assert "train" in segments
    assert "test" in segments
    first_fold_segments = materialize_segments(
        [
            {
                "fold_name": a.fold_name,
                "segment": a.segment,
                "start_time": a.start_time,
                "end_time": a.end_time,
                "indices": a.indices,
                "meta": a.meta,
            }
            for a in artifacts
        ],
        fold_name="fold_0",
    )
    assert "train" in first_fold_segments
    assert "test" in first_fold_segments


def test_walk_forward_split_produces_multiple_folds(synthetic_bars: pd.DataFrame) -> None:
    frame = _one_symbol(synthetic_bars)
    artifacts, _ = build_split_plan(
        frame,
        method="walk_forward",
        config={"window_days": 220, "step_days": 40, "min_train_days": 200},
    )
    folds = {a.fold_name for a in artifacts}
    assert len(folds) >= 2
