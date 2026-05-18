"""Active metadata management for the AQP data layer.

Threads three concepts through every Iceberg write:

1. **Medallion layering** — every dataset declares a layer
   (``bronze`` / ``silver`` / ``gold``). The wrapper in
   :mod:`aqp.data.iceberg_catalog` validates that the namespace prefix
   matches the declared layer (``aqp_bronze_*``, ``aqp_silver_*``,
   ``aqp_gold_*``).
2. **Business metadata** — ``data_owner``, ``semantic_definition``,
   ``reliability_score``, ``sla_class``, ``domain`` injected on every
   :class:`aqp.persistence.models.DatasetCatalog` upsert.
3. **Data contracts** — column-level type / required / range
   constraints validated against the incoming Arrow schema before
   writes are committed.

The single sanctioned entry point is :func:`register_dataset`. The
:func:`dataset` decorator is a syntactic-sugar wrapper around it for
fetcher / transform / sink classes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import select

from aqp.metadata import parse_urn
from aqp.metadata.namespace_policy import ResolvedPolicy, resolve_namespace_policy
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa  # noqa: F401

logger = logging.getLogger(__name__)


MedallionLayer = Literal["bronze", "silver", "gold"]
"""Three canonical layers of the AQP medallion architecture."""

LAYER_PREFIXES: dict[str, str] = {
    "bronze": "aqp_bronze_",
    "silver": "aqp_silver_",
    "gold": "aqp_gold_",
}


@dataclass(slots=True)
class BusinessMetadata:
    """Business-side metadata injected on dataset registration.

    Mirrors the columns added to :class:`DatasetCatalog.business_metadata`
    in migration ``0027``. Required fields raise on missing values so
    downstream agents can rely on ``data_owner`` and
    ``semantic_definition`` always being present on registered
    datasets.
    """

    data_owner: str
    semantic_definition: str
    reliability_score: float | None = None
    sla_class: str | None = None  # eg "tier-1-realtime", "tier-3-eod"
    domain: str | None = None  # eg "market.bars", "fundamentals.statements"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "data_owner": self.data_owner,
            "semantic_definition": self.semantic_definition,
        }
        if self.reliability_score is not None:
            out["reliability_score"] = float(self.reliability_score)
        if self.sla_class is not None:
            out["sla_class"] = str(self.sla_class)
        if self.domain is not None:
            out["domain"] = str(self.domain)
        if self.extras:
            out["extras"] = dict(self.extras)
        return out


@dataclass(slots=True)
class DataContract:
    """Column-level contract validated on every append.

    ``columns`` is a list of ``{"name", "type", "required", "range"}``
    dicts. ``type`` matches the Arrow type-name family
    (``int``, ``float``, ``string``, ``timestamp``, ``bool``, ``date``).
    ``range`` is optional ``[min, max]`` pair (numeric / timestamp).
    """

    columns: list[dict[str, Any]] = field(default_factory=list)
    description: str | None = None

    def column_names(self) -> set[str]:
        return {str(col.get("name")) for col in self.columns if col.get("name")}

    def required_names(self) -> set[str]:
        return {
            str(col["name"])
            for col in self.columns
            if col.get("name") and bool(col.get("required"))
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "description": self.description,
        }


@dataclass(slots=True)
class RegisterDatasetResult:
    """Outcome of :func:`register_dataset`."""

    catalog_id: str
    created: bool
    medallion_layer: MedallionLayer
    iceberg_identifier: str
    contract_violations: list[str] = field(default_factory=list)


def namespace_for_layer(
    layer: MedallionLayer,
    suffix: str,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    domain: str | None = None,
    policy: ResolvedPolicy | None = None,
) -> str:
    """Return the canonical namespace for a layer/source pair.

    Example: ``namespace_for_layer("silver", "alpha_vantage")`` returns
    ``"aqp_silver_alpha_vantage"``. Used by source adapters to derive
    their target namespace without hand-coding the prefix.
    """
    if layer not in LAYER_PREFIXES:
        raise ValueError(
            f"unknown medallion_layer {layer!r}; expected one of "
            f"{sorted(LAYER_PREFIXES)}"
        )
    suffix_clean = suffix.strip().strip("_").lower()
    if not suffix_clean:
        raise ValueError("namespace suffix cannot be empty")
    prefix = LAYER_PREFIXES[layer]
    if policy is not None:
        prefix = policy.prefix_for(layer)
    elif workspace_id is not None or project_id is not None or domain is not None:
        resolved = resolve_namespace_policy(
            workspace_id=workspace_id,
            project_id=project_id,
            domain=domain,
        )
        prefix = resolved.prefix_for(layer)
    return f"{prefix}{suffix_clean}"


def validate_layer_for_namespace(
    layer: MedallionLayer | None,
    namespace: str,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    domain: str | None = None,
    policy: ResolvedPolicy | None = None,
) -> None:
    """Raise :class:`ValueError` if ``namespace`` doesn't match ``layer``."""
    if layer is None:
        return
    if layer not in LAYER_PREFIXES:
        raise ValueError(
            f"unknown medallion_layer {layer!r}; expected one of "
            f"{sorted(LAYER_PREFIXES)}"
        )

    expected_prefix = LAYER_PREFIXES[layer]
    namespace_clean = namespace.split(".", 1)[0]
    if policy is None and namespace_clean.startswith(expected_prefix):
        return

    effective_prefix = expected_prefix
    if policy is not None:
        effective_prefix = policy.prefix_for(layer)
    elif workspace_id is not None or project_id is not None or domain is not None:
        resolved = resolve_namespace_policy(
            workspace_id=workspace_id,
            project_id=project_id,
            domain=domain,
        )
        effective_prefix = resolved.prefix_for(layer)

    if namespace_clean.startswith(effective_prefix):
        return
    raise ValueError(
        f"medallion_layer={layer!r} requires namespace prefix {expected_prefix!r} "
        f"(effective={effective_prefix!r}); got {namespace_clean!r}"
    )


def validate_namespace_with_policy(
    layer: MedallionLayer | None,
    namespace: str,
    *,
    policy: ResolvedPolicy | None = None,
) -> None:
    """Compatibility wrapper for callers that already resolved a policy."""
    validate_layer_for_namespace(layer, namespace, policy=policy)


def validate_contract_against_schema(
    contract: DataContract | None, arrow_schema: Any
) -> list[str]:
    """Return a list of human-readable contract violations.

    Empty list = no violations. Catches:

    - missing required columns
    - type-family mismatches (``int`` vs ``string``, etc.)

    Range validation is left to row-level :func:`Processor` nodes
    because PyArrow schemas don't carry value statistics.
    """
    if contract is None:
        return []
    if arrow_schema is None:
        return []
    try:
        present_columns = set(arrow_schema.names)
    except Exception:
        return []
    violations: list[str] = []
    for required in contract.required_names():
        if required not in present_columns:
            violations.append(f"missing required column: {required!r}")
    type_map = {col["name"]: col.get("type") for col in contract.columns if col.get("name")}
    for column_name in present_columns & contract.column_names():
        wanted = type_map.get(column_name)
        if not wanted:
            continue
        try:
            arrow_type = arrow_schema.field(column_name).type
        except Exception:
            continue
        actual = _arrow_type_family(arrow_type)
        if actual is None:
            continue
        if str(wanted).lower() != actual:
            violations.append(
                f"column {column_name!r} expected type-family "
                f"{wanted!r}, got {actual!r}"
            )
    return violations


def _arrow_type_family(arrow_type: Any) -> str | None:
    """Map a PyArrow type to one of the contract type-family strings."""
    try:
        import pyarrow as pa
    except ImportError:
        return None
    if pa.types.is_integer(arrow_type):
        return "int"
    if pa.types.is_floating(arrow_type):
        return "float"
    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return "string"
    if pa.types.is_boolean(arrow_type):
        return "bool"
    if pa.types.is_timestamp(arrow_type):
        return "timestamp"
    if pa.types.is_date(arrow_type):
        return "date"
    return None


def register_dataset(
    iceberg_identifier: str,
    *,
    medallion_layer: MedallionLayer,
    business_metadata: BusinessMetadata | dict[str, Any],
    data_contract: DataContract | dict[str, Any] | None = None,
    name: str | None = None,
    provider: str | None = None,
    domain: str | None = None,
    arrow_schema: Any = None,
    description: str | None = None,
    tags: list[str] | None = None,
    extras: dict[str, Any] | None = None,
    context: Any | None = None,
    policy_urn: str | None = None,
) -> RegisterDatasetResult:
    """Idempotent :class:`DatasetCatalog` upsert with active metadata.

    Validates the namespace against the declared layer and (when
    ``arrow_schema`` is supplied) the data contract. Returns the
    catalog row id and any contract violations so callers can decide
    whether to fail-loud or log-and-continue.

    ``context`` is the active :class:`RequestContext`; when omitted the
    helper reads it from the request-scoped contextvar so the upsert
    stamps ``owner_user_id`` / ``workspace_id`` / ``project_id`` on
    every catalog row that flows through ``append_arrow``. Falling back
    to NULL ownership for callers without a bound context preserves
    the legacy single-tenant behaviour.
    """
    bm = (
        business_metadata
        if isinstance(business_metadata, BusinessMetadata)
        else BusinessMetadata(**dict(business_metadata))
    )
    contract: DataContract | None
    if data_contract is None:
        contract = None
    elif isinstance(data_contract, DataContract):
        contract = data_contract
    else:
        contract = DataContract(**dict(data_contract))

    violations = (
        validate_contract_against_schema(contract, arrow_schema)
        if arrow_schema is not None
        else []
    )

    # Resolve tenancy from the supplied context, falling back to the
    # request-scoped contextvar (FastAPI deps), then to no ownership.
    if context is None:
        try:
            from aqp.auth.contextvars import current_request_context

            context = current_request_context.get()
        except Exception:  # pragma: no cover - defensive
            context = None

    owner_user_id = getattr(context, "user_id", None) if context is not None else None
    workspace_id = getattr(context, "workspace_id", None) if context is not None else None
    project_id = getattr(context, "project_id", None) if context is not None else None

    namespace, table_name = _split_identifier(iceberg_identifier)
    final_name = name or table_name
    final_provider = provider or _provider_from_namespace(namespace)
    final_domain = domain or bm.domain or "data.unknown"
    resolved_policy: ResolvedPolicy | None = None
    policy_urn_clean = str(policy_urn or "").strip() or None
    if policy_urn_clean is not None:
        from aqp.metadata.aspect_lookup import load_aspect
        from aqp.metadata.openmetadata import IcebergNamespacePolicy

        parse_urn(policy_urn_clean)
        policy_payload = load_aspect(
            policy_urn_clean,
            IcebergNamespacePolicy.aspect_name,
        )
        if policy_payload is None:
            raise ValueError(
                f"policy_urn {policy_urn_clean!r} does not have an "
                "'icebergNamespacePolicy' aspect"
            )
        policy_model = IcebergNamespacePolicy.model_validate(policy_payload)
        resolved_policy = ResolvedPolicy(
            bronze=policy_model.bronze_prefix,
            silver=policy_model.silver_prefix,
            gold=policy_model.gold_prefix,
            policy_urn=policy_model.urn,
            priority=int(policy_model.priority),
            source="aspect",
        )
    else:
        resolved_policy = resolve_namespace_policy(
            workspace_id=workspace_id,
            project_id=project_id,
            domain=final_domain,
        )

    merged_extras = dict(extras or {})
    if policy_urn_clean is not None:
        merged_extras["policy_urn"] = policy_urn_clean

    validate_layer_for_namespace(
        medallion_layer,
        iceberg_identifier,
        workspace_id=workspace_id,
        project_id=project_id,
        domain=final_domain,
        policy=resolved_policy,
    )

    schema_json = _arrow_schema_to_json(arrow_schema) if arrow_schema is not None else {}

    created = False
    with get_session() as session:
        existing = (
            session.execute(
                select(DatasetCatalog).where(
                    DatasetCatalog.iceberg_identifier == iceberg_identifier
                )
            )
            .scalars()
            .first()
        )
        now = datetime.utcnow()
        if existing is None:
            row_kwargs: dict[str, Any] = dict(
                name=final_name,
                provider=final_provider,
                domain=final_domain,
                iceberg_identifier=iceberg_identifier,
                medallion_layer=medallion_layer,
                business_metadata=bm.to_json(),
                data_contract_json=contract.to_json() if contract else {},
                schema_json=schema_json,
                description=description,
                tags=list(tags) if tags else [],
                meta=dict(merged_extras) if merged_extras else {},
                created_at=now,
                updated_at=now,
            )
            if owner_user_id:
                row_kwargs["owner_user_id"] = owner_user_id
            if workspace_id:
                row_kwargs["workspace_id"] = workspace_id
            if project_id:
                row_kwargs["project_id"] = project_id
            row = DatasetCatalog(**row_kwargs)
            session.add(row)
            session.flush()
            catalog_id = str(row.id)
            created = True
        else:
            existing.medallion_layer = medallion_layer
            existing.business_metadata = bm.to_json()
            if contract is not None:
                existing.data_contract_json = contract.to_json()
            if schema_json:
                existing.schema_json = schema_json
            if description is not None:
                existing.description = description
            if tags is not None:
                existing.tags = list(tags)
            if merged_extras:
                merged_meta = dict(existing.meta or {})
                merged_meta.update(merged_extras)
                existing.meta = merged_meta
            # Backfill ownership when the existing row was created
            # before the tenancy refactor and the active call has a
            # context to stamp. Never overwrite an already-owned row.
            if existing.owner_user_id is None and owner_user_id:
                existing.owner_user_id = owner_user_id
            if existing.workspace_id is None and workspace_id:
                existing.workspace_id = workspace_id
            if existing.project_id is None and project_id:
                existing.project_id = project_id
            existing.updated_at = now
            catalog_id = str(existing.id)
        session.commit()

    return RegisterDatasetResult(
        catalog_id=catalog_id,
        created=created,
        medallion_layer=medallion_layer,
        iceberg_identifier=iceberg_identifier,
        contract_violations=violations,
    )


def dataset(
    *,
    layer: MedallionLayer,
    owner: str,
    semantic_definition: str,
    reliability: float | None = None,
    sla_class: str | None = None,
    domain: str | None = None,
    contract: DataContract | dict[str, Any] | None = None,
    iceberg_identifier: str | None = None,
):
    """Decorator that attaches an :class:`ActiveMetadataSpec` to a class.

    Used on fetcher / transform / sink classes that produce a single
    target Iceberg table. The decorator stores the spec on a
    ``__aqp_dataset__`` attribute so callers like
    :func:`aqp.data.iceberg_catalog.append_arrow` can read it and call
    :func:`register_dataset` on first append. The class itself is
    returned unchanged so existing import / instantiation logic keeps
    working.

    .. code-block:: python

        @dataset(
            layer="silver",
            owner="data-team",
            semantic_definition="Daily OHLCV bars normalised against UTC.",
            reliability=0.95,
            iceberg_identifier="aqp_silver_alpha_vantage.daily_bars",
        )
        class AlphaVantageDailyBarsSink(SinkNode):
            ...
    """

    def decorator(cls):
        spec = {
            "layer": layer,
            "iceberg_identifier": iceberg_identifier,
            "business_metadata": BusinessMetadata(
                data_owner=owner,
                semantic_definition=semantic_definition,
                reliability_score=reliability,
                sla_class=sla_class,
                domain=domain,
            ),
            "contract": (
                contract.to_json()
                if isinstance(contract, DataContract)
                else dict(contract or {})
            ),
        }
        setattr(cls, "__aqp_dataset__", spec)
        return cls

    return decorator


def get_active_metadata_spec(target: Any) -> dict[str, Any] | None:
    """Return the :func:`dataset` spec attached to ``target`` (class or instance)."""
    return getattr(target, "__aqp_dataset__", None)


def _split_identifier(iceberg_identifier: str) -> tuple[str, str]:
    if "." not in iceberg_identifier:
        return "aqp", iceberg_identifier
    namespace, _, table_name = iceberg_identifier.rpartition(".")
    return namespace, table_name


def _provider_from_namespace(namespace: str) -> str:
    head = namespace.split(".", 1)[0]
    for prefix in LAYER_PREFIXES.values():
        if head.startswith(prefix):
            return head[len(prefix):] or "aqp"
    if head.startswith("aqp_"):
        return head[4:] or "aqp"
    return head or "aqp"


def _arrow_schema_to_json(arrow_schema: Any) -> dict[str, Any]:
    try:
        return {
            "fields": [
                {
                    "name": str(field.name),
                    "type": str(field.type),
                    "nullable": bool(field.nullable),
                }
                for field in arrow_schema
            ]
        }
    except Exception:  # noqa: BLE001
        return {}


__all__ = [
    "BusinessMetadata",
    "DataContract",
    "LAYER_PREFIXES",
    "MedallionLayer",
    "RegisterDatasetResult",
    "dataset",
    "get_active_metadata_spec",
    "namespace_for_layer",
    "register_dataset",
    "validate_contract_against_schema",
    "validate_layer_for_namespace",
    "validate_namespace_with_policy",
]
