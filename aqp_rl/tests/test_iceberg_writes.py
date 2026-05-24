"""Tests for the in-memory + Iceberg trajectory writers (skip Iceberg if unavailable)."""
from __future__ import annotations

import pytest

from aqp_rl.core.replay import InMemoryTrajectoryStore


def test_in_memory_trajectory_store_records():
    store = InMemoryTrajectoryStore()
    store.append_step({"run_id": "r1", "episode": 0, "step": 0, "reward": 0.5})
    store.append_equity({"run_id": "r1", "episode": 0, "step": 0, "portfolio_value": 100.0})
    store.append_action({"run_id": "r1", "episode": 0, "step": 0, "asset_idx": 0, "action_value": 0.1})
    store.append_reward_decomposition([{"run_id": "r1", "term_name": "pnl", "contribution": 0.5}])
    store.flush()
    assert len(store.steps) == 1
    assert len(store.equity) == 1
    assert len(store.actions) == 1
    assert len(store.reward_terms) == 1


def test_iceberg_trajectory_store_module_importable():
    pytest.importorskip("pyarrow", reason="pyarrow required for IcebergTrajectoryStore")
    from aqp_rl.trajectories.iceberg_writer import IcebergTrajectoryStore

    store = IcebergTrajectoryStore(run_id="test", flush_every=10)
    store.append_step({"run_id": "test", "episode": 0, "step": 0, "reward": 0.0, "ts": "2024-01-01"})
    # Don't flush — that would require an Iceberg catalog.
    assert len(store._steps) == 1  # noqa: SLF001
