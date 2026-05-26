"""Cell registry ORM models (Phase 3 §6.2 of RESTRUCTURING_PLAN.md).

Two tables back the cell topology:

- :class:`Cell` — one row per deployment cell. Mirrors the
  ``aqp_platform/configs/deployment/topology.yaml::cells`` section
  shape (which is the bootstrap seed). The ORM row is the live
  source of truth once the control plane is up.
- :class:`CellTenant` — pinning table mapping tenant ids to cells
  with a placement state. The ``aqp-tenant-router`` service does
  sub-millisecond lookups against this table to resolve a JWT
  ``(sub, workspace_id)`` to ``(cell_id, k8s_namespace, routes)``.

These models are CONTROL-PLANE entities — they are not user-scoped
and therefore do NOT carry :class:`ProjectScopedMixin` / workspace
FKs. Only AQP super-admins mutate cell rows via the control-plane
``/manage/cells/*`` routes (Phase 3 §6.2).

Schema migration: :mod:`alembic.versions.0082_cell_registry`.
The ``cell_id`` FK addition on audit tables ships in
:mod:`alembic.versions.0083_audit_cell_id_column`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    func,
)

from aqp.persistence.models import Base


# Allow-listed values mirrored from
# ``aqp_platform_core.topology.models.CellTier`` etc. The ORM enforces
# them via CheckConstraint matching the Alembic migration's CHECK
# clauses, so the database rejects bad inserts even if the Pydantic
# layer is bypassed.
CELL_TIERS: tuple[str, ...] = (
    "shared-std",
    "shared-prem",
    "silo-reg",
    "silo-custom",
)
CELL_TENANCY_STRATEGIES: tuple[str, ...] = (
    "shared_schema_rls",
    "schema_per_tenant",
    "database_per_enterprise",
    "hybrid",
)
CELL_STATES: tuple[str, ...] = (
    "provisioning",
    "active",
    "draining",
    "suspended",
    "maintenance",
    "decommissioning",
    "archived",
)
CELL_PLACEMENT_STATES: tuple[str, ...] = (
    "active",
    "draining",
    "migrated",
    "evicted",
)


class Cell(Base):
    """One deployment cell.

    Application-layer + data-layer + K8s-namespace composition unit.
    Owned by the control plane; mutations go through
    ``/manage/cells/*`` (Phase 3 §6.2). Reads via
    ``CellRepository.list_active()`` / ``CellRepository.get(cell_id)``.
    """

    __tablename__ = "cells"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('" + "','".join(CELL_TIERS) + "')",
            name="ck_cells_tier",
        ),
        CheckConstraint(
            "tenancy_strategy IN ('" + "','".join(CELL_TENANCY_STRATEGIES) + "')",
            name="ck_cells_tenancy_strategy",
        ),
        CheckConstraint(
            "state IN ('" + "','".join(CELL_STATES) + "')",
            name="ck_cells_state",
        ),
        CheckConstraint(
            "capacity_max_tenants >= 1",
            name="ck_cells_capacity_min_one",
        ),
    )

    id: str = Column(String(120), primary_key=True)
    tier: str = Column(String(32), nullable=False, index=True)
    tenancy_strategy: str = Column(String(64), nullable=False)
    region: str = Column(String(64), nullable=False, index=True)
    availability_zone: str = Column(String(64), nullable=False)
    k8s_namespace: str = Column(
        String(63), nullable=False, unique=True, index=True
    )
    capacity_max_tenants: int = Column(
        Integer, nullable=False, default=1, server_default="1"
    )
    state: str = Column(
        String(32),
        nullable=False,
        default="provisioning",
        server_default="provisioning",
        index=True,
    )
    pinned_tenants = Column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    routes = Column(JSON, nullable=False, default=dict, server_default="{}")
    labels = Column(JSON, nullable=False, default=dict, server_default="{}")
    annotations = Column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    created_at: datetime = Column(
        DateTime, nullable=False, default=datetime.utcnow, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=datetime.utcnow,
    )
    created_by: str | None = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_modified_by: str | None = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    state_transitioned_at: datetime | None = Column(DateTime, nullable=True)
    drained_at: datetime | None = Column(DateTime, nullable=True)
    decommissioned_at: datetime | None = Column(DateTime, nullable=True)

    def is_active(self) -> bool:
        return self.state == "active"


class CellTenant(Base):
    """Tenant-to-cell pinning row.

    ``placement`` lifecycle:

    - ``active`` — tenant is hosted in the cell; serves all traffic.
    - ``draining`` — tenant is being migrated to ``migrated_to_cell_id``;
      writes still go to the source cell but the tenant-router has
      started shadowing reads against the target.
    - ``migrated`` — migration complete; the row stays for audit so
      operators can reconstruct the migration path.
    - ``evicted`` — tenant was forcibly removed (incident response /
      compliance hold). ``drained_at`` is set.
    """

    __tablename__ = "cell_tenants"
    __table_args__ = (
        PrimaryKeyConstraint("cell_id", "tenant_id", name="pk_cell_tenants"),
        CheckConstraint(
            "placement IN ('" + "','".join(CELL_PLACEMENT_STATES) + "')",
            name="ck_cell_tenants_placement",
        ),
    )

    cell_id: str = Column(
        String(120),
        ForeignKey("cells.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: str = Column(String(36), nullable=False, index=True)
    placement: str = Column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )
    placed_at: datetime = Column(
        DateTime, nullable=False, default=datetime.utcnow, server_default=func.now()
    )
    drained_at: datetime | None = Column(DateTime, nullable=True)
    migrated_to_cell_id: str | None = Column(String(120), nullable=True)


__all__ = [
    "CELL_PLACEMENT_STATES",
    "CELL_STATES",
    "CELL_TENANCY_STRATEGIES",
    "CELL_TIERS",
    "Cell",
    "CellTenant",
]
