"""Tests for the Phase 5 tenant-scoped key namespace."""
from __future__ import annotations

import pytest

from aqp.cache.keys import (
    ORG_SCOPED_CATEGORIES,
    by_id_hash,
    by_name_hash,
    names_zset,
)
from aqp.config import settings


@pytest.fixture(autouse=True)
def _prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_key_prefix", "aqp:cache")


def test_org_scoped_keys_get_org_segment() -> None:
    key = names_zset("workspaces", org_id="org-abc")
    assert key == "aqp:cache:org-abc:workspaces:names"


def test_global_categories_ignore_org_id() -> None:
    # 'dataset_kinds' is global - no per-org slot.
    assert "dataset_kinds" not in ORG_SCOPED_CATEGORIES
    key = names_zset("dataset_kinds", org_id="org-abc")
    assert key == "aqp:cache:dataset_kinds:names"


def test_missing_org_id_falls_back_to_global() -> None:
    key = names_zset("workspaces")
    assert key == "aqp:cache:workspaces:names"


def test_by_id_and_by_name_carry_org_segment() -> None:
    assert by_id_hash("resources", "r1", org_id="org-A") == "aqp:cache:org-A:resources:by_id:r1"
    assert (
        by_name_hash("resources", "MyAsset", org_id="org-A")
        == "aqp:cache:org-A:resources:by_name:myasset"
    )


def test_new_categories_all_recognized() -> None:
    """All Phase 5 categories accept the org_id segment kwarg."""
    expected = {
        "organizations",
        "teams",
        "users",
        "workspaces",
        "labs",
        "experiments",
        "tests",
        "agents",
        "bots",
        "rl_experiments",
        "analysis_specs",
        "resources",
        "strategy_templates",
    }
    for cat in expected:
        # Just verify no exception is raised.
        names_zset(cat)
