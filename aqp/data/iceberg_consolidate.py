"""Physical consolidation of Iceberg part-tables into a single table.

When an upstream loader writes a logically-single dataset as multiple
Iceberg tables (``foo_part_1``, ``foo_part_2``, …), this module merges
them by:

1. Validating schema compatibility (column names + types) across all
   members.
2. Reading the union of all data files via PyIceberg's table scan.
3. Creating (or replacing) the target table at ``group_name``.
4. Appending the consolidated Arrow table.
5. Optionally dropping the member tables and removing their
   ``DatasetCatalog`` rows.

Designed to be **destructive only when explicitly confirmed**: callers
should default to ``dry_run=True`` and require an out-of-band ``confirm``
flag before flipping ``drop_members=True``.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aqp.data import iceberg_catalog
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)


@dataclass
class MemberReport:
    identifier: str
    rows: int = 0
    columns: list[str] = field(default_factory=list)
    error: str | None = None
    dropped: bool = False


@dataclass
class ConsolidationReport:
    group_name: str
    members: list[MemberReport] = field(default_factory=list)
    total_rows: int = 0
    schema_columns: list[str] = field(default_factory=list)
    schema_compatible: bool = True
    schema_conflicts: list[str] = field(default_factory=list)
    target_created: bool = False
    target_rows_after: int = 0
    dry_run: bool = True
    drop_members: bool = False
    catalog_rows_deleted: int = 0
    started_at: str = ""
    finished_at: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_name": self.group_name,
            "members": [
                {
                    "identifier": m.identifier,
                    "rows": m.rows,
                    "columns": m.columns,
                    "error": m.error,
                    "dropped": m.dropped,
                }
                for m in self.members
            ],
            "total_rows": self.total_rows,
            "schema_columns": self.schema_columns,
            "schema_compatible": self.schema_compatible,
            "schema_conflicts": self.schema_conflicts,
            "target_created": self.target_created,
            "target_rows_after": self.target_rows_after,
            "dry_run": self.dry_run,
            "drop_members": self.drop_members,
            "catalog_rows_deleted": self.catalog_rows_deleted,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


ProgressCallback = Callable[[float, str], None]


def _read_member(identifier: str) -> tuple[Any | None, MemberReport]:
    """Return ``(arrow_table, MemberReport)`` for a single member, or ``(None, …)`` on miss."""
    report = MemberReport(identifier=identifier)
    table = iceberg_catalog.load_table(identifier)
    if table is None:
        report.error = "table not found"
        return None, report
    try:
        arrow = table.scan().to_arrow()
    except Exception as exc:  # noqa: BLE001
        report.error = f"scan failed: {exc}"
        return None, report
    if arrow is None:
        report.error = "empty scan"
        return None, report
    report.rows = int(arrow.num_rows)
    report.columns = [str(f.name) for f in arrow.schema]
    return arrow, report


def _delete_catalog_rows(identifiers: list[str]) -> int:
    """Best-effort delete of ``DatasetCatalog`` rows for the given members."""
    from sqlalchemy import select

    from aqp.persistence.models import DatasetCatalog

    if not identifiers:
        return 0
    deleted = 0
    try:
        with get_session() as session:
            stmt = select(DatasetCatalog).where(
                DatasetCatalog.iceberg_identifier.in_(identifiers)
            )
            for row in session.execute(stmt).scalars().all():
                session.delete(row)
                deleted += 1
            session.flush()
    except Exception:  # noqa: BLE001
        logger.warning("catalog row deletion failed", exc_info=True)
    return deleted


def _normalise_schema_columns(arrow_table: Any) -> list[tuple[str, str]]:
    """Return ``[(name, str(type)), ...]`` to use as a hashable schema key."""
    return [(str(f.name), str(f.type)) for f in arrow_table.schema]


def consolidate_group(
    group_name: str,
    members: list[str],
    *,
    dry_run: bool = True,
    drop_members: bool = True,
    on_progress: ProgressCallback | None = None,
) -> ConsolidationReport:
    """Merge ``members`` into a single Iceberg table at ``group_name``.

    Parameters
    ----------
    group_name:
        Target identifier (``"namespace.name"``). Created if missing.
    members:
        List of Iceberg identifiers to merge.
    dry_run:
        When ``True``, validate schemas + report counts, but do **not**
        write a new table or drop members.
    drop_members:
        When ``True`` AND ``dry_run`` is ``False``, drop the source tables
        and their ``DatasetCatalog`` rows after the merge succeeds.
    on_progress:
        Optional callable ``(percent, message)`` for streaming progress.
    """
    report = ConsolidationReport(
        group_name=group_name,
        dry_run=dry_run,
        drop_members=drop_members,
        started_at=datetime.utcnow().isoformat(),
    )
    try:
        import pyarrow as pa  # local import — pyiceberg already requires it
    except Exception as exc:  # noqa: BLE001
        report.error = f"pyarrow unavailable: {exc}"
        report.finished_at = datetime.utcnow().isoformat()
        return report

    deduped_members = [str(m).strip() for m in members if str(m).strip()]
    deduped_members = list(dict.fromkeys(deduped_members))
    if len(deduped_members) < 2:
        report.error = "consolidation requires at least 2 members"
        report.finished_at = datetime.utcnow().isoformat()
        return report
    if group_name in deduped_members:
        report.error = "group_name cannot be one of the members"
        report.finished_at = datetime.utcnow().isoformat()
        return report

    if on_progress:
        on_progress(2.0, f"Reading {len(deduped_members)} member tables")

    # 1) Read each member.
    arrow_tables: list[Any] = []
    schemas_seen: set[tuple[tuple[str, str], ...]] = set()
    schema_conflicts: list[str] = []
    for idx, identifier in enumerate(deduped_members):
        if on_progress:
            on_progress(
                2.0 + (idx / max(1, len(deduped_members))) * 30.0,
                f"Reading {identifier}",
            )
        arrow, member_report = _read_member(identifier)
        report.members.append(member_report)
        if arrow is None:
            schema_conflicts.append(f"{identifier}: {member_report.error}")
            continue
        schema_key = tuple(_normalise_schema_columns(arrow))
        if schemas_seen and schema_key not in schemas_seen:
            schema_conflicts.append(
                f"{identifier}: schema mismatch with previous members "
                f"(cols={[c for c, _ in schema_key]})"
            )
        schemas_seen.add(schema_key)
        arrow_tables.append(arrow)

    if not arrow_tables:
        report.error = "no readable member tables"
        report.schema_compatible = False
        report.schema_conflicts = schema_conflicts
        report.finished_at = datetime.utcnow().isoformat()
        return report

    if len(schemas_seen) > 1:
        report.schema_compatible = False
        report.schema_conflicts = schema_conflicts
        report.finished_at = datetime.utcnow().isoformat()
        report.error = (
            f"{len(schemas_seen)} different schemas across members; refusing to merge. "
            "Edit column docs / promote types and retry."
        )
        return report

    # 2) Concatenate.
    if on_progress:
        on_progress(35.0, "Concatenating Arrow tables")
    try:
        merged = pa.concat_tables(arrow_tables, promote_options="default")
    except Exception as exc:  # noqa: BLE001
        report.error = f"concat_tables failed: {exc}"
        report.finished_at = datetime.utcnow().isoformat()
        return report

    report.total_rows = int(merged.num_rows)
    report.schema_columns = [str(f.name) for f in merged.schema]

    if dry_run:
        report.target_rows_after = 0
        if on_progress:
            on_progress(100.0, "Dry-run complete")
        report.finished_at = datetime.utcnow().isoformat()
        return report

    # 3) Replace target table + append.
    if on_progress:
        on_progress(50.0, f"Creating target table {group_name}")
    try:
        iceberg_catalog.create_or_replace_table(group_name, merged.schema)
        report.target_created = True
    except Exception as exc:  # noqa: BLE001
        report.error = f"create_or_replace_table failed: {exc}"
        report.finished_at = datetime.utcnow().isoformat()
        return report

    if on_progress:
        on_progress(70.0, "Appending merged data")
    try:
        target_table = iceberg_catalog.append_arrow(group_name, merged, create_if_missing=False)
        try:
            arrow_after = target_table.scan().to_arrow()
            report.target_rows_after = int(arrow_after.num_rows) if arrow_after is not None else 0
        except Exception:  # noqa: BLE001
            report.target_rows_after = report.total_rows
    except Exception as exc:  # noqa: BLE001
        report.error = f"append_arrow failed: {exc}"
        report.finished_at = datetime.utcnow().isoformat()
        return report

    # 4) Optional cleanup.
    dropped_ids: list[str] = []
    if drop_members:
        for idx, identifier in enumerate(deduped_members):
            if on_progress:
                on_progress(
                    85.0 + (idx / max(1, len(deduped_members))) * 10.0,
                    f"Dropping {identifier}",
                )
            try:
                ok = iceberg_catalog.drop_table(identifier)
                for member_report in report.members:
                    if member_report.identifier == identifier:
                        member_report.dropped = bool(ok)
                if ok:
                    dropped_ids.append(identifier)
            except Exception:  # noqa: BLE001
                logger.warning("drop_table %s failed", identifier, exc_info=True)
        report.catalog_rows_deleted = _delete_catalog_rows(dropped_ids)

    if on_progress:
        on_progress(100.0, "Consolidation complete")
    report.finished_at = datetime.utcnow().isoformat()
    return report


__all__ = ["ConsolidationReport", "MemberReport", "consolidate_group"]
