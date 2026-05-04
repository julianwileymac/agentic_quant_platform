"""The default-* UUID constants must match across migration / Settings / models.

Migration 0017 hard-codes the default UUIDs (because Alembic revisions
shouldn't import from app code). This test guarantees the
``aqp.config.defaults`` module stays in sync — drift would mean
backfilled rows from 0018 point at non-existent IDs.
"""
from __future__ import annotations

from aqp.config import (
    DEFAULT_LAB_ID,
    DEFAULT_ORG_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_TEAM_ID,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
)


def test_default_org_id_matches_canonical_uuid() -> None:
    assert DEFAULT_ORG_ID == "00000000-0000-0000-0000-000000000001"


def test_default_team_id_matches_canonical_uuid() -> None:
    assert DEFAULT_TEAM_ID == "00000000-0000-0000-0000-000000000002"


def test_default_user_id_matches_canonical_uuid() -> None:
    assert DEFAULT_USER_ID == "00000000-0000-0000-0000-000000000003"


def test_default_workspace_id_matches_canonical_uuid() -> None:
    assert DEFAULT_WORKSPACE_ID == "00000000-0000-0000-0000-000000000004"


def test_default_project_id_matches_canonical_uuid() -> None:
    assert DEFAULT_PROJECT_ID == "00000000-0000-0000-0000-000000000005"


def test_default_lab_id_matches_canonical_uuid() -> None:
    assert DEFAULT_LAB_ID == "00000000-0000-0000-0000-000000000006"


def test_settings_exposes_default_ids_as_env_overridable() -> None:
    """Settings has fields for each default-*-id env override."""
    from aqp.config import Settings

    s = Settings()
    assert s.default_org_id == DEFAULT_ORG_ID
    assert s.default_team_id == DEFAULT_TEAM_ID
    assert s.default_user_id == DEFAULT_USER_ID
    assert s.default_workspace_id == DEFAULT_WORKSPACE_ID
    assert s.default_project_id == DEFAULT_PROJECT_ID
    assert s.default_lab_id == DEFAULT_LAB_ID


def test_migration_0017_uses_same_constants() -> None:
    """Module-level constants in the migration mirror aqp.config.defaults."""
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[2]
    migration = here / "alembic" / "versions" / "0017_tenancy_foundation.py"
    spec = importlib.util.spec_from_file_location("_tenancy_migration", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.DEFAULT_ORG_ID == DEFAULT_ORG_ID
    assert module.DEFAULT_TEAM_ID == DEFAULT_TEAM_ID
    assert module.DEFAULT_USER_ID == DEFAULT_USER_ID
    assert module.DEFAULT_WORKSPACE_ID == DEFAULT_WORKSPACE_ID
    assert module.DEFAULT_PROJECT_ID == DEFAULT_PROJECT_ID
    assert module.DEFAULT_LAB_ID == DEFAULT_LAB_ID


def test_migration_0021_uses_same_constants_and_targets_deployments() -> None:
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[2]
    migration = here / "alembic" / "versions" / "0021_default_tenancy_normalization.py"
    spec = importlib.util.spec_from_file_location("_tenancy_normalization_migration", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.DEFAULT_ORG_ID == DEFAULT_ORG_ID
    assert module.DEFAULT_TEAM_ID == DEFAULT_TEAM_ID
    assert module.DEFAULT_USER_ID == DEFAULT_USER_ID
    assert module.DEFAULT_WORKSPACE_ID == DEFAULT_WORKSPACE_ID
    assert module.DEFAULT_PROJECT_ID == DEFAULT_PROJECT_ID
    assert module.DEFAULT_LAB_ID == DEFAULT_LAB_ID
    assert module.down_revision == "0020_bots"
    assert module.NORMALIZED_TABLES == (
        "model_deployments",
        "bots",
        "bot_versions",
        "bot_deployments",
    )
