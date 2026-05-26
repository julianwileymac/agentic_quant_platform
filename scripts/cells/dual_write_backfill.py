"""Backfill a tenant's historical rows into a per-cell data plane.

Phase 6 §9 (``RESTRUCTURING_PLAN.md``) — companion to the
``AQP_CELL_DUAL_WRITE`` switch. When migrating a tenant from the shared
cluster-wide Postgres into a ``silo-reg`` (or ``shared-prem``) cell, the
operator flow is:

1.  Provision the per-cell data plane via the
    ``aqp-cell-data-plane`` Helm chart.
2.  Flip ``AQP_CELL_DUAL_WRITE=true`` so new writes land in BOTH
    planes (caller mid-transaction at point of writeback). Application
    code stays untouched; the dual write happens behind
    ``aqp/persistence/db.py``.
3.  Run THIS script with ``--tenant <id> --target-cell <cell_id>`` to
    copy every historical row that pre-dates step 2.
4.  Reconcile (``--reconcile-only`` mode below) — row counts and
    SHA-256 of selected columns MUST match between planes.
5.  Cut the tenant over by updating ``tenant_cells.cell_id`` and
    flipping ``AQP_CELL_DUAL_WRITE=false`` again.

The script is intentionally read-mostly: it scans the source plane in
``--batch-size`` chunks, materialises one batch per insert, and writes
to the target plane via ``COPY ... FROM STDIN`` for throughput.

USAGE
-----

``--dry-run`` (default-on for safety) prints the plan without writing.
``--apply`` is the explicit go-button; both planes must be reachable
and the operator must have confirmed via stdin "I have read the runbook".

DESTRUCTIVE-OPERATION NOTE
--------------------------

This script writes to a new database. It NEVER deletes from the
source. The cutover (step 5 above) is a separate change request and
NEVER part of this script — operators MUST explicitly update
``tenant_cells.cell_id`` themselves, with audit logging.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tables in scope for the dual-write backfill.
#
# Order matters: parents before children so foreign keys validate. The
# rule of thumb is "what does the tenant see in the UI?" — backfill
# everything they own, skip cluster-wide tables like audit-log
# (audit-log lives in the audit/ bucket on MinIO with Object Lock).
# ---------------------------------------------------------------------------

_TENANT_OWNED_TABLES: list[tuple[str, str]] = [
    # (table_name, tenant_filter_column)
    ("workspaces", "organization_id"),
    ("strategy_specs", "organization_id"),
    ("agent_specs", "organization_id"),
    ("bot_specs", "organization_id"),
    ("rl_experiment_specs", "organization_id"),
    ("alpha_specs", "organization_id"),
    ("alpha_backtest_runs", "organization_id"),
    ("agent_runs_v2", "organization_id"),
    ("bot_runs", "organization_id"),
    ("rl_experiment_runs", "organization_id"),
    ("strategy_runs", "organization_id"),
    ("workload_runs", "organization_id"),
    ("portfolio_optimisation_runs", "organization_id"),
    ("paper_trading_accounts", "organization_id"),
    ("paper_trading_positions", "organization_id"),
    ("paper_trading_orders", "organization_id"),
    ("paper_trading_fills", "organization_id"),
    ("dataset_specs", "organization_id"),
    ("dataset_versions", "organization_id"),
]


def _resolve_source_engine() -> Any:
    """Return the cluster-wide source engine (the legacy shared plane)."""
    # Force the no-cell path by clearing the runtime context.
    from aqp.tenancy.runtime_context import reset_runtime_context, set_runtime_context

    tok = set_runtime_context(None)
    try:
        from aqp.persistence.db import _sync_engine_for_cell

        return _sync_engine_for_cell(None)
    finally:
        reset_runtime_context(tok)


def _resolve_target_engine(cell_id: str) -> Any:
    """Return the per-cell target engine."""
    from aqp.persistence.db import _sync_engine_for_cell

    return _sync_engine_for_cell(cell_id)


def _row_hash(row: Any) -> str:
    """Stable per-row SHA-256 used for reconciliation parity."""
    h = hashlib.sha256()
    for value in row:
        if value is None:
            h.update(b"\x00")
        elif isinstance(value, bytes):
            h.update(value)
        else:
            h.update(repr(value).encode("utf-8"))
        h.update(b"\x1f")  # ASCII unit separator
    return h.hexdigest()


def _count_and_hash(
    engine: Any, table: str, tenant_col: str, tenant_id: str
) -> tuple[int, str]:
    """Count + roll-up SHA-256 the per-tenant rows for parity checks."""
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"SELECT * FROM {table} "  # noqa: S608 - parameterised below
                f"WHERE {tenant_col} = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        )
        rows = result.fetchall()
    count = len(rows)
    h = hashlib.sha256()
    for row in sorted(rows, key=lambda r: tuple(repr(v) for v in r)):
        h.update(_row_hash(tuple(row)).encode("utf-8"))
    return count, h.hexdigest()


def _backfill_table(
    source_engine: Any,
    target_engine: Any,
    table: str,
    tenant_col: str,
    tenant_id: str,
    batch_size: int,
    dry_run: bool,
) -> int:
    """Copy a single table for one tenant. Returns the row count copied.

    Idempotency: the target is expected to be EMPTY for this tenant
    before the backfill. The script enforces this with a count check
    and aborts if the target already has rows for the same tenant.
    """
    from sqlalchemy import text

    # Pre-flight: target must be empty for this tenant.
    with target_engine.connect() as conn:
        existing = conn.execute(
            text(
                f"SELECT COUNT(*) FROM {table} "  # noqa: S608 - parameterised
                f"WHERE {tenant_col} = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        ).scalar_one()
        if existing > 0:
            raise RuntimeError(
                f"table {table!r}: target plane already has {existing} rows for "
                f"tenant {tenant_id!r}; refusing to backfill (would create duplicates)"
            )

    # Plan: select source rows in stable order, copy in batches.
    with source_engine.connect() as conn:
        result = conn.execute(
            text(
                f"SELECT * FROM {table} "  # noqa: S608 - parameterised
                f"WHERE {tenant_col} = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        )
        columns = list(result.keys())
        rows = result.fetchall()

    if dry_run:
        logger.info(
            "[DRY-RUN] would copy %d rows from %s for tenant %s "
            "(target plane is empty)",
            len(rows),
            table,
            tenant_id,
        )
        return len(rows)

    if not rows:
        logger.info("table %s: 0 rows for tenant %s (skipping)", table, tenant_id)
        return 0

    placeholder = ", ".join([f":c{i}" for i in range(len(columns))])
    insert_sql = text(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholder})"
    )

    total = 0
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        with target_engine.begin() as conn:
            for row in batch:
                params = {f"c{i}": row[i] for i in range(len(columns))}
                conn.execute(insert_sql, params)
        total += len(batch)
        logger.info(
            "table %s: copied %d/%d rows for tenant %s",
            table,
            total,
            len(rows),
            tenant_id,
        )
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dual_write_backfill",
        description="Backfill a tenant's historical rows into a per-cell data plane.",
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="The tenant (organization id) to migrate.",
    )
    parser.add_argument(
        "--target-cell",
        required=True,
        help="The destination cell id (e.g. cell-silo-reg-acme).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Insert batch size (default: 1000).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually write to the target plane. Without --apply the "
            "script runs in dry-run mode and only prints the plan."
        ),
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help=(
            "Skip the backfill; just print row counts + SHA-256 row hashes "
            "for both planes so the operator can verify parity."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    dry_run = not args.apply
    if dry_run and not args.reconcile_only:
        logger.warning(
            "DRY-RUN mode (no --apply). Add --apply to actually copy rows."
        )

    # Resolve engines.
    source = _resolve_source_engine()
    target = _resolve_target_engine(args.target_cell)
    logger.info(
        "Resolved engines: source=<shared-cluster>, target=%s",
        args.target_cell,
    )

    if args.reconcile_only:
        ok = True
        for table, tenant_col in _TENANT_OWNED_TABLES:
            try:
                s_count, s_hash = _count_and_hash(
                    source, table, tenant_col, args.tenant
                )
                t_count, t_hash = _count_and_hash(
                    target, table, tenant_col, args.tenant
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("%s: reconcile FAILED: %s", table, exc)
                ok = False
                continue
            match = s_count == t_count and s_hash == t_hash
            logger.info(
                "%s: source=%d/%s  target=%d/%s  %s",
                table,
                s_count,
                s_hash[:12],
                t_count,
                t_hash[:12],
                "OK" if match else "MISMATCH",
            )
            if not match:
                ok = False
        return 0 if ok else 2

    # Backfill mode.
    if not dry_run:
        confirmation = input(
            "I have read aqp_docs/docs/how-to/cell-data-plane-migration.md "
            "and verified that AQP_CELL_DUAL_WRITE is enabled. (yes/NO): "
        )
        if confirmation.strip().lower() != "yes":
            logger.error("Aborted by operator.")
            return 1

    total_rows = 0
    for table, tenant_col in _TENANT_OWNED_TABLES:
        try:
            count = _backfill_table(
                source,
                target,
                table,
                tenant_col,
                args.tenant,
                args.batch_size,
                dry_run,
            )
            total_rows += count
        except Exception as exc:  # noqa: BLE001
            logger.error("backfill FAILED for table %s: %s", table, exc)
            return 3

    logger.info(
        "%s: %d rows copied for tenant %s (target=%s)",
        "[DRY-RUN]" if dry_run else "[APPLIED]",
        total_rows,
        args.tenant,
        args.target_cell,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
