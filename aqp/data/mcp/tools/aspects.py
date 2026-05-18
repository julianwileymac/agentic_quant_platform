"""Aspect-oriented metadata DataMCP tools (Phase 3 of metadata consolidation)."""
from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import and_, asc, desc, literal, or_, select

from aqp.data.catalog.namespace_policy import resolve_namespace_policy
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.metadata import parse_urn, write_aspect
from aqp.metadata.namespace_policy import register_namespace_policy
from aqp.metadata.openmetadata import (
    EntityLineage,
    IcebergNamespacePolicy,
    LineageEdge,
    MlFeature,
    MlHyperParameter,
    MlModel,
)
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect

logger = logging.getLogger(__name__)


def _workspace_scope_clause_for_workspace(workspace_id: str | None) -> Any:
    """Return the canonical workspace scope filter for metadata aspects."""
    if workspace_id:
        return or_(
            EntityAspect.workspace_id == workspace_id,
            EntityAspect.workspace_id.is_(None),
        )
    return EntityAspect.workspace_id.is_(None)


def _workspace_scope_clause(ctx: MCPToolContext) -> Any:
    """Return the canonical workspace scope filter for metadata aspects."""
    return _workspace_scope_clause_for_workspace(ctx.workspace_id)


def _dedupe_aspects(rows: list[EntityAspect]) -> list[EntityAspect]:
    """Deduplicate aspect rows preserving first-seen order."""
    out: list[EntityAspect] = []
    seen_ids: set[str] = set()
    for row in rows:
        row_id = str(row.id)
        if row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        out.append(row)
    return out


def _rows_to_lineage_edges(rows: list[EntityAspect]) -> list[LineageEdge]:
    """Convert ``EntityAspect`` rows to validated ``LineageEdge`` payloads."""
    edges: list[LineageEdge] = []
    for row in _dedupe_aspects(rows):
        payload = row.payload if isinstance(row.payload, dict) else {}
        try:
            edges.append(LineageEdge(**payload))
        except Exception:  # noqa: BLE001
            logger.debug(
                "Skipping invalid lineage edge payload for aspect=%s",
                row.id,
                exc_info=True,
            )
    return edges


def _walk_lineage_postgres_direction(
    *,
    session: Any,
    urn: str,
    depth: int,
    direction: Literal["upstream", "downstream"],
    workspace_id: str | None,
) -> list[EntityAspect]:
    """Walk lineage with a recursive CTE for PostgreSQL deployments."""
    from_entity_expr = EntityAspect.payload["from_entity"].as_string()
    to_entity_expr = EntityAspect.payload["to_entity"].as_string()
    scope_clause = _workspace_scope_clause_for_workspace(workspace_id)

    if direction == "downstream":
        anchor_predicate = from_entity_expr == urn
        next_urn_expr = to_entity_expr
    else:
        anchor_predicate = to_entity_expr == urn
        next_urn_expr = from_entity_expr

    anchor = (
        select(
            EntityAspect.id.label("aspect_id"),
            EntityAspect.urn.label("urn"),
            next_urn_expr.label("next_urn"),
            literal(1).label("hop"),
        )
        .where(EntityAspect.aspect_name == "lineageEdge")
        .where(anchor_predicate)
        .where(scope_clause)
    )
    lineage_walk = anchor.cte("lineage_walk", recursive=True)
    if direction == "downstream":
        recursive_join = from_entity_expr == lineage_walk.c.next_urn
    else:
        recursive_join = to_entity_expr == lineage_walk.c.next_urn

    recursive_part = (
        select(
            EntityAspect.id.label("aspect_id"),
            EntityAspect.urn.label("urn"),
            next_urn_expr.label("next_urn"),
            (lineage_walk.c.hop + 1).label("hop"),
        )
        .select_from(EntityAspect)
        .join(lineage_walk, recursive_join)
        .where(EntityAspect.aspect_name == "lineageEdge")
        .where(scope_clause)
        .where(lineage_walk.c.hop < depth)
    )
    union_cte = lineage_walk.union_all(recursive_part)

    rows = session.execute(
        select(EntityAspect, union_cte.c.hop)
        .join(
            union_cte,
            and_(
                EntityAspect.urn == union_cte.c.urn,
                EntityAspect.id == union_cte.c.aspect_id,
            ),
        )
        .order_by(asc(union_cte.c.hop), asc(EntityAspect.created_at))
    ).all()
    return _dedupe_aspects([row[0] for row in rows])


def _walk_lineage_sqlite_direction(
    *,
    edges: list[EntityAspect],
    urn: str,
    depth: int,
    direction: Literal["upstream", "downstream"],
) -> list[EntityAspect]:
    """Walk lineage in Python for sqlite tests that lack recursive JSON CTEs."""
    frontier: set[str] = {urn}
    seen_nodes: set[str] = {urn}
    seen_edges: set[str] = set()
    collected: list[EntityAspect] = []

    for _ in range(depth):
        if not frontier:
            break
        next_frontier: set[str] = set()
        for edge in edges:
            payload = edge.payload if isinstance(edge.payload, dict) else {}
            from_entity = payload.get("from_entity")
            to_entity = payload.get("to_entity")
            if not isinstance(from_entity, str) or not isinstance(to_entity, str):
                continue

            if direction == "downstream":
                matches_frontier = from_entity in frontier
                next_node = to_entity
            else:
                matches_frontier = to_entity in frontier
                next_node = from_entity

            if not matches_frontier:
                continue
            edge_id = str(edge.id)
            if edge_id in seen_edges:
                continue
            seen_edges.add(edge_id)
            collected.append(edge)
            if next_node not in seen_nodes:
                seen_nodes.add(next_node)
                next_frontier.add(next_node)
        frontier = next_frontier
    return collected


def _walk_lineage(
    *,
    session: Any,
    urn: str,
    depth: int,
    direction: Literal["upstream", "downstream", "both"],
    workspace_id: str | None,
) -> dict[str, Any]:
    """Return an ``EntityLineage`` payload for one focal entity URN."""
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""

    upstream_rows: list[EntityAspect] = []
    downstream_rows: list[EntityAspect] = []

    if dialect_name == "postgresql":
        if direction in {"upstream", "both"}:
            upstream_rows = _walk_lineage_postgres_direction(
                session=session,
                urn=urn,
                depth=depth,
                direction="upstream",
                workspace_id=workspace_id,
            )
        if direction in {"downstream", "both"}:
            downstream_rows = _walk_lineage_postgres_direction(
                session=session,
                urn=urn,
                depth=depth,
                direction="downstream",
                workspace_id=workspace_id,
            )
    else:
        scope_clause = _workspace_scope_clause_for_workspace(workspace_id)
        lineage_edges = session.execute(
            select(EntityAspect)
            .where(EntityAspect.aspect_name == "lineageEdge")
            .where(scope_clause)
            .order_by(asc(EntityAspect.created_at), asc(EntityAspect.version))
        ).scalars().all()
        if direction in {"upstream", "both"}:
            upstream_rows = _walk_lineage_sqlite_direction(
                edges=lineage_edges,
                urn=urn,
                depth=depth,
                direction="upstream",
            )
        if direction in {"downstream", "both"}:
            downstream_rows = _walk_lineage_sqlite_direction(
                edges=lineage_edges,
                urn=urn,
                depth=depth,
                direction="downstream",
            )

    lineage = EntityLineage(
        entity=urn,
        upstream_edges=_rows_to_lineage_edges(upstream_rows),
        downstream_edges=_rows_to_lineage_edges(downstream_rows),
        depth=depth,
    )
    return lineage.model_dump(mode="json")


def _extract_validation_fields(exc: ValidationError) -> list[str]:
    """Flatten Pydantic ``loc`` tuples to dotted field paths."""
    fields: list[str] = []
    for error in exc.errors():
        location = error.get("loc", ())
        if not location:
            continue
        dotted = ".".join(str(part) for part in location if part != "__root__")
        if dotted and dotted not in fields:
            fields.append(dotted)
    return fields


def _validation_guidance(fields: list[str]) -> str:
    """Build human-actionable guidance from field-level validation paths."""
    if any(path == "target" or path.startswith("target.") for path in fields):
        return "the predicted variable (target) is required"
    if any("feature_sources" in path for path in fields):
        return (
            "each feature_source must carry a source_urn referencing a "
            "registered dataset URN"
        )
    return "see field-level error messages for details"


def _namespace_policy_validation_guidance(fields: list[str]) -> str:
    """Build guidance for namespace policy validation failures."""
    if any(path.endswith("_prefix") for path in fields):
        return (
            "namespace prefixes must end with '_' and match "
            "^[a-z][a-z0-9_]{0,63}_$"
        )
    if "urn" in fields:
        return "urn must match urn:aqp:<entity_type>:<env>:<id>"
    return "see field-level error messages for details"


class QueryLineageArgs(BaseModel):
    """Arguments for ``aspect.query_entity_lineage``."""

    model_config = ConfigDict(extra="forbid")

    urn: str = Field(
        ...,
        description=(
            "AQP URN of the focal entity, eg. "
            "urn:aqp:dataset:prod:aqp_silver_alpha_vantage.daily_bars."
        ),
    )
    depth: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Number of hops to traverse outward from the focal entity.",
    )
    direction: Literal["upstream", "downstream", "both"] = Field(
        default="both",
        description=(
            "Whether to walk only upstream, only downstream, or both directions."
        ),
    )


@register_data_mcp_tool
class QueryEntityLineageTool(DataMCPTool):
    """Walk the metadata lineage graph from a focal AQP URN."""

    name = "aspect.query_entity_lineage"
    description = (
        "Walk the EntityLineage DAG outward from an AQP URN up to a configurable "
        "depth. Returns the full structured EntityLineage payload with upstream "
        "and downstream LineageEdge rows. Use this before referencing a downstream "
        "model in a paper-trading config so you can confirm its training data lineage."
    )
    args_schema = QueryLineageArgs
    category = "metadata"
    tags = ("metadata", "lineage")
    required_scopes = ("data:read",)
    mutates = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
        urn: str,
        depth: int = 2,
        direction: Literal["upstream", "downstream", "both"] = "both",
    ) -> MCPToolResult:
        """Return upstream/downstream lineage edges for a focal entity URN."""
        try:
            parse_urn(urn)
        except ValueError as exc:
            return MCPToolResult(ok=False, error=f"invalid urn: {exc}")

        with get_session() as session:
            payload = _walk_lineage(
                session=session,
                urn=urn,
                depth=depth,
                direction=direction,
                workspace_id=ctx.workspace_id,
            )

        lineage = EntityLineage.model_validate(payload)
        edge_count = len(lineage.upstream_edges) + len(lineage.downstream_edges)
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"walked {edge_count} edges from {urn}",
            rows_returned=edge_count,
        )


class RegisterModelArgs(BaseModel):
    """Arguments for ``aspect.register_model``."""

    model_config = ConfigDict(extra="forbid")

    urn: str = Field(
        ...,
        description="AQP URN for the ML model entity to register/update.",
    )
    name: str = Field(
        ...,
        description="Human-readable name for the model.",
    )
    algorithm: str = Field(
        ...,
        description="Model algorithm alias (must match a registered model kind).",
    )
    ml_features: list[MlFeature] = Field(
        default_factory=list,
        description="Feature definitions used to train the model.",
    )
    ml_hyper_parameters: list[MlHyperParameter] = Field(
        default_factory=list,
        description="Hyperparameter key/value pairs recorded for the model run.",
    )
    target: str | None = Field(
        default=None,
        description="Predicted variable for the model, eg. forward_return_1d.",
    )
    status: Literal["Development", "Staging", "Production", "Deprecated"] = Field(
        ...,
        description="Lifecycle status of the model.",
    )
    model_version: str | None = Field(
        default=None,
        description="Optional model version label, eg. v1.2.0.",
    )
    mlflow_run_id: str | None = Field(
        default=None,
        description="Optional MLflow run ID linked to this metadata record.",
    )


class RegisterPolicyArgs(BaseModel):
    """Arguments for ``aspect.register_namespace_policy``."""

    model_config = ConfigDict(extra="forbid")

    urn: str = Field(
        ...,
        description=(
            "AQP URN of the namespace_policy entity, eg. "
            "urn:aqp:namespace_policy:prod:tenant_acme."
        ),
    )
    policy_name: str = Field(
        ...,
        description="Operator-friendly name for the policy.",
    )
    bronze_prefix: str = Field(
        default="aqp_bronze_",
        description="Iceberg namespace prefix for the bronze medallion layer.",
    )
    silver_prefix: str = Field(
        default="aqp_silver_",
        description="Iceberg namespace prefix for the silver medallion layer.",
    )
    gold_prefix: str = Field(
        default="aqp_gold_",
        description="Iceberg namespace prefix for the gold medallion layer.",
    )
    applies_to_workspace_id: str | None = Field(
        default=None,
        description="Optional workspace scope. None means global/project default.",
    )
    applies_to_project_id: str | None = Field(
        default=None,
        description="Optional project scope for the namespace policy.",
    )
    applies_to_domain_pattern: str | None = Field(
        default=None,
        description="Optional regex matched against BusinessMetadata.domain.",
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=1000,
        description="Higher priority wins when multiple policies match.",
    )


class ResolveNamespacePolicyArgs(BaseModel):
    """Arguments for ``aspect.resolve_namespace_policy``."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str | None = Field(
        default=None,
        description="Optional workspace identifier for scope matching.",
    )
    project_id: str | None = Field(
        default=None,
        description="Optional project identifier for scope matching.",
    )
    domain: str | None = Field(
        default=None,
        description="Optional domain identifier for scope matching.",
    )
    env: str | None = Field(
        default=None,
        description="Optional environment identifier for scope matching.",
    )


@register_data_mcp_tool
class ResolveNamespacePolicyTool(DataMCPTool):
    """Resolve the effective namespace policy for a tenancy scope."""

    name = "aspect.resolve_namespace_policy"
    description = (
        "Resolve the effective Iceberg namespace prefix policy for the given "
        "workspace/project/domain combination. Returns the effective per-layer "
        "prefixes plus any allow-listed extra namespaces. Read-only; consult "
        "before registering a new dataset in a non-default scope."
    )
    args_schema = ResolveNamespacePolicyArgs
    category = "metadata"
    tags = ("metadata", "aspects", "iceberg")
    required_scopes = ("data:read",)
    mutates = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
        workspace_id: str | None = None,
        project_id: str | None = None,
        domain: str | None = None,
        env: str | None = None,
    ) -> MCPToolResult:
        """Return effective namespace policy materialized for caller scope."""
        _ = ctx
        resolved = resolve_namespace_policy(
            workspace_id=workspace_id,
            project_id=project_id,
            domain=domain,
            env=env,
        )
        data = {
            "effective_prefixes": dict(resolved.effective_prefixes),
            "extra_allowed_namespaces": list(resolved.extra_allowed_namespaces),
            "source_aspect_ids": list(resolved.source_aspect_ids),
            "is_default": resolved.is_default,
        }
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data["source_aspect_ids"]),
            summary=(
                "resolved namespace policy from defaults"
                if resolved.is_default
                else "resolved namespace policy from scoped aspects"
            ),
        )


@register_data_mcp_tool
class RegisterModelTool(DataMCPTool):
    """Register/update an ``mlModelMetadata`` aspect from validated Pydantic input."""

    name = "aspect.register_model"
    description = (
        "Register or update an MlModel by writing a new mlModelMetadata aspect. "
        "Returns the new aspect_id and version. Validation rejects missing target, "
        "unlinked feature_sources, or unknown algorithm with a semantic "
        "MetadataValidationError payload."
    )
    args_schema = RegisterModelArgs
    category = "metadata"
    tags = ("metadata", "ml", "mutating")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:
        """Apply scope policy then enforce session write permissions."""
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        urn: str,
        name: str,
        algorithm: str,
        ml_features: list[MlFeature] | None = None,
        ml_hyper_parameters: list[MlHyperParameter] | None = None,
        target: str | None = None,
        status: Literal["Development", "Staging", "Production", "Deprecated"],
        model_version: str | None = None,
        mlflow_run_id: str | None = None,
    ) -> MCPToolResult:
        """Write a new immutable ``mlModelMetadata`` aspect when payload changes."""
        try:
            ml_model = MlModel(
                urn=urn,
                name=name,
                algorithm=algorithm,
                ml_features=list(ml_features or []),
                ml_hyper_parameters=list(ml_hyper_parameters or []),
                target=target,
                status=status,
                model_version=model_version,
                mlflow_run_id=mlflow_run_id,
            )
        except ValidationError as exc:
            fields = _extract_validation_fields(exc)
            return MCPToolResult(
                ok=False,
                error="MetadataValidationError",
                metadata={
                    "fields": fields,
                    "guidance": _validation_guidance(fields),
                    "details": exc.errors(),
                },
            )

        with get_session() as session:
            aspect = write_aspect(
                session,
                ml_model.urn,
                "mlModelMetadata",
                ml_model,
            )
            session.commit()
            return MCPToolResult(
                ok=True,
                data={
                    "aspect_id": aspect.id,
                    "version": aspect.version,
                    "urn": ml_model.urn,
                },
                summary=f"registered {ml_model.urn} v{aspect.version}",
            )


@register_data_mcp_tool
class RegisterNamespacePolicyTool(DataMCPTool):
    """Register/update an ``icebergNamespacePolicy`` aspect."""

    name = "aspect.register_namespace_policy"
    description = (
        "Register or update an IcebergNamespacePolicy. Lets agents declare "
        "per-tenant or per-domain medallion-prefix overrides without touching code."
    )
    args_schema = RegisterPolicyArgs
    category = "metadata"
    tags = ("metadata", "aspects", "iceberg", "mutating")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:
        """Apply scope policy then enforce session write permissions."""
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        urn: str,
        policy_name: str,
        bronze_prefix: str = "aqp_bronze_",
        silver_prefix: str = "aqp_silver_",
        gold_prefix: str = "aqp_gold_",
        applies_to_workspace_id: str | None = None,
        applies_to_project_id: str | None = None,
        applies_to_domain_pattern: str | None = None,
        priority: int = 0,
    ) -> MCPToolResult:
        """Write a new immutable ``icebergNamespacePolicy`` aspect."""
        _ = ctx
        try:
            policy = IcebergNamespacePolicy(
                urn=urn,
                policy_name=policy_name,
                bronze_prefix=bronze_prefix,
                silver_prefix=silver_prefix,
                gold_prefix=gold_prefix,
                applies_to_workspace_id=applies_to_workspace_id,
                applies_to_project_id=applies_to_project_id,
                applies_to_domain_pattern=applies_to_domain_pattern,
                priority=priority,
            )
        except ValidationError as exc:
            fields = _extract_validation_fields(exc)
            return MCPToolResult(
                ok=False,
                error="MetadataValidationError",
                metadata={
                    "fields": fields,
                    "guidance": _namespace_policy_validation_guidance(fields),
                    "details": exc.errors(),
                },
            )

        with get_session() as session:
            written_urn = register_namespace_policy(policy, session=session)
            latest = session.execute(
                select(EntityAspect)
                .where(EntityAspect.urn == written_urn)
                .where(EntityAspect.aspect_name == IcebergNamespacePolicy.aspect_name)
                .order_by(desc(EntityAspect.version))
                .limit(1)
            ).scalars().first()
            if latest is None:
                return MCPToolResult(
                    ok=False,
                    error="MetadataValidationError",
                    metadata={
                        "fields": ["urn"],
                        "guidance": "policy aspect write did not persist",
                        "details": [],
                    },
                )

            return MCPToolResult(
                ok=True,
                data={
                    "aspect_id": str(latest.id),
                    "version": int(latest.version),
                    "urn": written_urn,
                    "resolved_prefixes": {
                        "bronze": policy.bronze_prefix,
                        "silver": policy.silver_prefix,
                        "gold": policy.gold_prefix,
                    },
                },
                summary=f"registered {written_urn} v{int(latest.version)}",
            )


class GetAspectHistoryArgs(BaseModel):
    """Arguments for ``aspect.get_history``."""

    model_config = ConfigDict(extra="forbid")

    urn: str = Field(
        ...,
        description="AQP URN of the entity.",
    )
    aspect_name: str = Field(
        ...,
        description=(
            "Aspect name to retrieve history for, eg. mlModelMetadata, "
            "datasetProperties, businessMetadata."
        ),
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of historical versions to return.",
    )


@register_data_mcp_tool
class GetAspectHistoryTool(DataMCPTool):
    """Read versioned aspect history for one URN/aspect pair."""

    name = "aspect.get_history"
    description = (
        "Return all historical versions of a named aspect for an AQP URN, "
        "ordered by version DESC. Use this to audit how an MlModel evolved "
        "or to fetch a specific version's payload for replay."
    )
    args_schema = GetAspectHistoryArgs
    category = "metadata"
    tags = ("metadata", "history")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        urn: str,
        aspect_name: str,
        limit: int = 10,
    ) -> MCPToolResult:
        """Fetch immutable aspect versions newest-first."""
        try:
            parse_urn(urn)
        except ValueError as exc:
            return MCPToolResult(ok=False, error=f"invalid urn: {exc}")

        with get_session() as session:
            rows = session.execute(
                select(EntityAspect)
                .where(EntityAspect.urn == urn)
                .where(EntityAspect.aspect_name == aspect_name)
                .where(_workspace_scope_clause(ctx))
                .order_by(desc(EntityAspect.version))
                .limit(limit)
            ).scalars().all()
            data = [
                {
                    "id": row.id,
                    "urn": row.urn,
                    "aspect_name": row.aspect_name,
                    "version": row.version,
                    "payload": row.payload,
                    "payload_hash": row.payload_hash,
                    "system_metadata": row.system_metadata,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "created_by": row.created_by,
                }
                for row in rows
            ]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"returned {len(data)} versions for {urn}:{aspect_name}",
        )


__all__ = [
    "GetAspectHistoryTool",
    "QueryEntityLineageTool",
    "RegisterNamespacePolicyTool",
    "ResolveNamespacePolicyTool",
    "RegisterModelTool",
    "_walk_lineage",
]
