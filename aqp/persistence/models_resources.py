"""Polymorphic Resource registry (Phase 1 of the multi-tenant graph expansion).

A Resource is the universal handle for any *content asset* in the
platform that isn't already a first-class ORM (e.g. dataset templates,
strategy templates, model artefacts, configuration documents,
notebooks, research papers, agent templates, bot templates, report
artefacts). The same row can be owned by an Organization, a Team, a
Workspace, a Project, or a User — the ``owner_scope_kind`` /
``owner_scope_id`` pair stores the polymorphic owner.

Why polymorphic rather than one table per type?

- The MCP catalog (``data.ownership.*``, ``data.strategies.templates.*``)
  needs a uniform "resources visible to me" query that crosses dozens
  of asset types without a giant UNION.
- The frontend ``EntityPicker`` reads from a single Redis cache
  category ``resources``; tens of sibling categories would balloon
  payload sizes without adding clarity.
- New asset types (e.g. "LEAN strategy template", "agent skill pack")
  show up by adding to :data:`RESOURCE_TYPES` and writing the
  ingestion script — no migration needed.

The existing single-purpose ORMs (``DatasetCatalog``,
``StrategyTemplateRow`` if ever needed, etc.) stay as the source of
truth for typed columns; they cross-reference back to
``resources.uri`` via the resource_relations table so the graph can
walk them uniformly.

AGENTS.md hard rule 33 (added in this rollout): All ownership /
membership queries that traverse more than one hop MUST go through
:class:`aqp.graph.OwnershipGraphStore`. Don't hand-write joins over
``organizations / teams / users / memberships / resources``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# The set of asset types the universal registry covers. Open-ended —
# new types are added by appending here + writing the ingestion path.
# The frontend ``EntityPicker(kind="resources")`` filters on this column.
RESOURCE_TYPES: tuple[str, ...] = (
    "strategy_template",     # LEAN, community, internal references
    "dataset_template",      # alternative-data subscriptions etc.
    "model_artifact",        # serialized weights, ONNX, MLflow uri
    "config",                # YAML / TOML / JSON blobs (paper configs etc.)
    "notebook",              # exported .ipynb / .py
    "document",              # markdown / PDF / research write-up
    "agent_template",        # AgentSpec YAML
    "bot_template",          # BotSpec YAML
    "report",                # equity report / governance audit
    "sink_template",         # SinkRow reference
    "rl_curriculum",         # RLExperimentSpec template
    # Phase 8 of hybrid agentic-RL: symbolic alpha factor formula
    # authored via the Alpha Factor Studio (rule 39 AST-sandboxed).
    # `meta` carries {formula, rationale, metrics, used_operators,
    # used_fields, expected_horizon_bars, expected_direction}.
    "alpha_factor",
)


# Polymorphic owner discriminator. ``user`` resources are private,
# ``team`` resources are shared within a team, ``workspace`` resources
# follow the workspace's visibility setting, ``project`` resources
# inherit project membership, ``organization`` resources are visible
# to every member of the org.
OWNER_SCOPE_KINDS: tuple[str, ...] = (
    "organization",
    "team",
    "workspace",
    "project",
    "user",
)


# Relation discriminators on resource_relations. Mirrors the
# OwnershipGraphStore edge kinds in Phase 2 so the Neo4j projector
# doesn't need a translation table.
RESOURCE_RELATIONS: tuple[str, ...] = (
    "derived_from",     # this resource was forked from another
    "clones",           # 1:1 copy
    "uses",             # references another resource at runtime
    "references",       # weaker than uses (e.g. docs cite)
    "translated_from",  # LEAN template -> FrameworkAlgorithm skeleton
)


class Resource(Base, ProjectScopedMixin):
    """A polymorphic content asset with a polymorphic owner.

    Identity:

    - ``id`` is the canonical UUID.
    - ``slug`` is the URL-safe handle the UI shows.
    - ``uri`` is the optional fully-qualified locator (e.g.
      ``lean://algorithm.python/MACDTrendAlgorithm``,
      ``mlflow://runs/<run_id>``, ``iceberg://aqp_gold_x.y``).

    Ownership:

    - ``owner_scope_kind`` + ``owner_scope_id`` is the polymorphic
      pointer. The :class:`ProjectScopedMixin` columns
      (``owner_user_id`` / ``workspace_id`` / ``project_id``) are still
      stamped for traversal even when the *primary* owner is e.g. an
      organization.

    Payload:

    - ``metadata`` is a free-form jsonb blob (tags, categories,
      provenance).
    - ``data_payload`` is an OPTIONAL inline byte payload for small
      assets (config blob, source code). Anything > 64 KB should live
      in object storage and be referenced via ``uri``.
    """

    # Table name carries the ``aqp_`` prefix so it never collides with
    # an MLflow / Airflow / dbt artefact named ``resources`` in the
    # shared Postgres database.
    __tablename__ = "aqp_resources"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(240), nullable=False)
    slug = Column(String(180), nullable=False, index=True)
    resource_type = Column(String(48), nullable=False, index=True)
    uri = Column(String(1024), nullable=True, index=True)
    description = Column(Text, nullable=True)
    owner_scope_kind = Column(String(24), nullable=False, index=True)
    owner_scope_id = Column(String(36), nullable=False, index=True)
    meta = Column(JSON, default=dict)
    data_payload = Column(LargeBinary, nullable=True)
    tags = Column(JSON, default=list)
    visibility = Column(String(24), nullable=False, default="private", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "owner_scope_kind",
            "owner_scope_id",
            "resource_type",
            "slug",
            name="uq_resources_owner_type_slug",
        ),
    )


Index(
    "ix_resources_owner_type",
    Resource.owner_scope_kind,
    Resource.owner_scope_id,
    Resource.resource_type,
)
Index(
    "ix_resources_workspace_type",
    Resource.workspace_id,
    Resource.resource_type,
)


class ResourceRelation(Base):
    """Edge between two :class:`Resource` rows (derived_from, uses, clones, ...).

    Postgres carries the canonical edge; the Phase 2 Neo4j projector
    mirrors them into the graph store for fast multi-hop traversal.
    No tenancy mixin here — the Resource endpoints already carry
    ownership, and the edges themselves are global metadata.
    """

    __tablename__ = "aqp_resource_relations"

    id = Column(String(36), primary_key=True, default=_uuid)
    from_id = Column(
        String(36),
        nullable=False,
        index=True,
    )
    to_id = Column(
        String(36),
        nullable=False,
        index=True,
    )
    relation = Column(String(32), nullable=False, index=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "from_id", "to_id", "relation", name="uq_resource_relations_edge"
        ),
    )


Index(
    "ix_resource_relations_to_relation",
    ResourceRelation.to_id,
    ResourceRelation.relation,
)


__all__ = [
    "OWNER_SCOPE_KINDS",
    "RESOURCE_RELATIONS",
    "RESOURCE_TYPES",
    "Resource",
    "ResourceRelation",
]
