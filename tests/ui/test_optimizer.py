"""Unit tests for the sweep-generation side of the new optimizer engine.

The Celery task is covered elsewhere (integration); here we pin down the
grid / random enumeration + the summarise helper.
"""
from __future__ import annotations

import pytest

from aqp.backtest.optimizer import ParameterSpec, generate_trials, summarise


def test_parameter_spec_enumerate_range() -> None:
    spec = ParameterSpec(path="x", low=0.0, high=1.0, step=0.5)
    assert spec.enumerate() == [0.0, 0.5, 1.0]


def test_parameter_spec_enumerate_ints() -> None:
    spec = ParameterSpec(path="x", low=5, high=10, step=1)
    values = spec.enumerate()
    assert values == [5, 6, 7, 8, 9, 10]
    assert all(isinstance(v, int) for v in values)


def test_parameter_spec_explicit_values() -> None:
    spec = ParameterSpec(path="x", values=[10, 20, 30])
    assert spec.enumerate() == [10, 20, 30]


def test_grid_search_cartesian_product() -> None:
    base = {"a": {"b": 0, "c": 0}}
    trials = list(
        generate_trials(
            base,
            [
                ParameterSpec(path="a.b", values=[1, 2]),
                ParameterSpec(path="a.c", values=[10, 20, 30]),
            ],
        )
    )
    assert len(trials) == 6
    # Spot-check that params + config are consistent.
    params, cfg = trials[0]
    assert set(params.keys()) == {"a.b", "a.c"}
    assert cfg["a"]["b"] == params["a.b"]
    assert cfg["a"]["c"] == params["a.c"]


def test_random_search_respects_cap() -> None:
    base = {"a": {"b": 0}}
    trials = list(
        generate_trials(
            base,
            [ParameterSpec(path="a.b", values=list(range(100)))],
            method="random",
            n_random=5,
            seed=1,
        )
    )
    assert len(trials) == 5
    assert len({t[0]["a.b"] for t in trials}) == 5


def test_random_search_caps_at_grid_size() -> None:
    base = {"a": 0}
    trials = list(
        generate_trials(
            base,
            [ParameterSpec(path="a", values=[1, 2])],
            method="random",
            n_random=10,
            seed=1,
        )
    )
    # Only two unique values exist; random sampler should not duplicate.
    assert len(trials) == 2


def test_summarise_picks_best_trial() -> None:
    trials = [
        {"trial_index": 0, "status": "completed", "sharpe": 0.5},
        {"trial_index": 1, "status": "completed", "sharpe": 1.7},
        {"trial_index": 2, "status": "completed", "sharpe": 1.1},
        {"trial_index": 3, "status": "error", "sharpe": None},
    ]
    s = summarise(trials, metric="sharpe")
    assert s["completed"] == 3
    assert s["best_trial_index"] == 1
    assert pytest.approx(s["best_metric_value"], rel=1e-6) == 1.7


def test_summarise_handles_empty() -> None:
    assert summarise([])["n_trials"] == 0
