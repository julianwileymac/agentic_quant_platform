"""Chaos test: dbt snapshot pool deadlock recovery.

Verifies the canonical fix from
`aqp_docs/runbooks/snapshot-deadlock.md`: the
`free_slots_after_run_end_seconds=300` knob on the
`dbt_snapshots` pool prevents the deadlock the Dagster docs
describe ("a single cancelled run will permanently deadlock all
future runs for that pool").

This test reads the dagster.yaml + asserts the knob is present
without spinning up the full Dagster instance.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


def test_dagster_yaml_has_free_slots_knob():
    """The dagster.yaml must declare free_slots_after_run_end_seconds."""
    root = Path(__file__).resolve().parents[2] / "aqp" / "dagster" / "dagster.yaml"
    assert root.exists(), f"dagster.yaml missing at {root}"
    parsed = yaml.safe_load(root.read_text(encoding="utf-8"))
    rm = parsed.get("run_monitoring") or {}
    assert rm.get("enabled") is True
    assert int(rm.get("free_slots_after_run_end_seconds") or 0) >= 60


def test_dagster_yaml_has_dbt_snapshots_pool_limit_one():
    """The dbt_snapshots pool must serialise at limit=1."""
    root = Path(__file__).resolve().parents[2] / "aqp" / "dagster" / "dagster.yaml"
    parsed = yaml.safe_load(root.read_text(encoding="utf-8"))
    pools = (parsed.get("concurrency") or {}).get("pools") or {}
    config = pools.get("config") or {}
    snapshots = config.get("dbt_snapshots") or {}
    assert int(snapshots.get("limit") or 0) == 1
