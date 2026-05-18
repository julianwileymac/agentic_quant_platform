"""Smoke tests for the ``0051_seed_wiley_tech`` migration.

The migration itself is exercised end-to-end by the standard
``alembic upgrade head`` fixture in :mod:`tests.persistence.conftest`.
These tests assert the deterministic UUID derivation + the
helper-table coverage list so the seed stays reproducible across
clusters.
"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def seed_module():
    """Import the migration module; skip if alembic isn't installed."""
    pytest.importorskip("alembic")
    from alembic.versions import _0051_seed_wiley_tech as _seed  # type: ignore[attr-defined]
    return _seed


def test_seed_uuids_are_deterministic(seed_module):
    """Seed UUIDs derive from uuid5(NAMESPACE_DNS, "<scope>.wiley-tech.aqp")."""
    expected_org = str(
        uuid.uuid5(uuid.NAMESPACE_DNS, "org.wiley-tech.aqp")
    )
    assert seed_module.WILEY_TECH_ORG_ID == expected_org

    expected_user = str(
        uuid.uuid5(uuid.NAMESPACE_DNS, "user.wiley-tech.aqp")
    )
    assert seed_module.WILEY_TECH_USER_ID == expected_user


def test_seed_uuids_distinct_across_scopes(seed_module):
    ids = {
        seed_module.WILEY_TECH_ORG_ID,
        seed_module.WILEY_TECH_TEAM_ID,
        seed_module.WILEY_TECH_USER_ID,
        seed_module.WILEY_TECH_WORKSPACE_ID,
        seed_module.WILEY_TECH_PROJECT_ID,
        seed_module.WILEY_TECH_LAB_ID,
    }
    assert len(ids) == 6, "every seeded scope must have a distinct UUID"


def test_restamp_table_coverage(seed_module):
    """The restamp list covers every existing typed run + spec table.

    AGENTS rule 34: every new run-producing flow MUST populate
    ``experiment_id`` (and ``test_id`` where applicable) on its run
    row. The seed migration restamps tenancy refs on every legacy
    row so the new Wiley Tech org inherits ownership.
    """
    table_set = {tup[0] for tup in seed_module._LEGACY_STAMP_TABLES}
    must_cover = {
        "strategies",
        "backtest_runs",
        "paper_trading_runs",
        "bots",
        "bot_versions",
        "bot_deployments",
        "agent_runs",
        "agent_runs_v2",
        "agent_spec_versions",
        "rl_runs",
        "rl_experiment_versions",
        "analysis_runs",
        "analysis_spec_versions",
        "workflow_runs",
        "aqp_experiments",
        "aqp_tests",
        "resources",
        "ml_alpha_backtest_runs",
        "ml_experiment_runs",
    }
    missing = must_cover - table_set
    assert not missing, (
        f"seed migration does not restamp tables: {sorted(missing)}"
    )


def test_seed_membership_id_is_stable(seed_module):
    """Each scope_kind gets a deterministic membership id (uuid5)."""
    org_membership = seed_module._wiley_membership_id("org")
    expected = str(
        uuid.uuid5(uuid.NAMESPACE_DNS, "membership.org.wiley-tech.aqp")
    )
    assert org_membership == expected
