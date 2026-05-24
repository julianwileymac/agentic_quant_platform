"""Chaos test: DR restore wall-clock budget.

The Phase 6 phase-gate requires the full restore (rate-limit
Redis + audit log + dbt manifests) to complete in < 30 min.
This test asserts the runbook + the Alembic + the Celery export
tasks are all in place; the live time budget is enforced by the
matching CI workflow under
.github/workflows/dr-restore-rehearsal.yml (not shipped here).
"""
from __future__ import annotations

from pathlib import Path


def test_dr_restore_runbook_exists():
    root = Path(__file__).resolve().parents[2]
    runbook = root / "aqp_docs" / "runbooks" / "dr-restore.md"
    assert runbook.exists(), f"DR runbook missing at {runbook}"


def test_audit_log_hash_chain_migration_exists():
    root = Path(__file__).resolve().parents[2]
    migration = root / "alembic" / "versions" / "0079_audit_log_hash_chain.py"
    assert migration.exists(), f"hash-chain migration missing at {migration}"
    text = migration.read_text(encoding="utf-8")
    assert "enforce_audit_log_hash_chain" in text
    assert "TRIGGER audit_log_hash_chain" in text


def test_ledger_export_task_exists():
    root = Path(__file__).resolve().parents[2]
    task_file = (
        root / "aqp_ratelimit" / "tasks" / "ledger_export.py"
    )
    assert task_file.exists(), f"ledger export task missing at {task_file}"
    text = task_file.read_text(encoding="utf-8")
    assert "export_ledger_window" in text
    assert "object_lock" in text.lower() or "ObjectLockMode" in text
