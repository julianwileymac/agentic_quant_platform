"""Resolve effective Iceberg namespace prefixes via the aspect store.

Falls back to the hardcoded LAYER_PREFIXES defaults when no
icebergNamespacePolicy aspect is set for the scope.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from aqp.metadata import parse_urn
from aqp.metadata.openmetadata import IcebergNamespacePolicy
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect

logger = logging.getLogger(__name__)

RESERVED_NAMESPACES: frozenset[str] = frozenset(
    {"aqp_cfpb", "aqp_uspto", "aqp_fda", "aqp_sec", "aqp_smoke"}
)
"""Namespaces that no policy can repurpose."""


@dataclass(frozen=True, slots=True)
class EffectivePolicy:
    """Materialized namespace policy used by medallion validators."""

    bronze_prefix: str
    silver_prefix: str
    gold_prefix: str
    forbidden_prefixes: frozenset[str]
    allowed_extra_prefixes: frozenset[str]
    source: Literal["default", "aspect"]


DEFAULT_POLICY: EffectivePolicy = EffectivePolicy(
    bronze_prefix="aqp_bronze_",
    silver_prefix="aqp_silver_",
    gold_prefix="aqp_gold_",
    forbidden_prefixes=RESERVED_NAMESPACES,
    allowed_extra_prefixes=frozenset(),
    source="default",
)


@dataclass(frozen=True, slots=True)
class ResolvedNamespacePolicy:
    """Backward-compatible legacy representation of policy resolution."""

    effective_prefixes: dict[str, str]
    extra_allowed_namespaces: tuple[str, ...]
    source_aspect_ids: tuple[str, ...]
    is_default: bool


def _namespace_head(namespace: str) -> str:
    return str(namespace or "").strip().split(".", 1)[0]


def _coerce_scope_urn(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> str | None:
    project = str(project_id or "").strip()
    if project:
        return f"urn:aqp:project:prod:{project}"
    workspace = str(workspace_id or "").strip()
    if workspace:
        return f"urn:aqp:workspace:prod:{workspace}"
    return None


def _matches_prefix(namespace: str, prefix: str) -> bool:
    prefix_clean = str(prefix or "").strip().lower()
    if not prefix_clean:
        return False
    namespace_clean = str(namespace or "").strip().lower()
    if prefix_clean.endswith("_"):
        return namespace_clean.startswith(prefix_clean)
    return namespace_clean == prefix_clean


def _resolve_with_session(
    *,
    session: Session,
    scope_urn: str,
) -> tuple[EffectivePolicy, str | None]:
    aspect_row = (
        session.execute(
            select(EntityAspect)
            .where(EntityAspect.urn == scope_urn)
            .where(EntityAspect.aspect_name == IcebergNamespacePolicy.aspect_name)
            .order_by(desc(EntityAspect.version), desc(EntityAspect.created_at))
            .limit(1)
        )
        .scalars()
        .first()
    )
    if aspect_row is None:
        logger.debug(
            "No icebergNamespacePolicy aspect found for scope=%s; using defaults",
            scope_urn,
        )
        return DEFAULT_POLICY, None

    payload = aspect_row.payload if isinstance(aspect_row.payload, dict) else {}
    try:
        policy_aspect = IcebergNamespacePolicy.model_validate(payload)
    except Exception:  # noqa: BLE001
        logger.debug(
            "Invalid icebergNamespacePolicy payload for aspect_id=%s; using defaults",
            aspect_row.id,
            exc_info=True,
        )
        return DEFAULT_POLICY, None

    resolved = EffectivePolicy(
        bronze_prefix=policy_aspect.bronze_prefix,
        silver_prefix=policy_aspect.silver_prefix,
        gold_prefix=policy_aspect.gold_prefix,
        forbidden_prefixes=frozenset(
            {
                *(str(v).strip().lower() for v in policy_aspect.forbidden_prefixes),
                *RESERVED_NAMESPACES,
            }
        ),
        allowed_extra_prefixes=frozenset(
            str(v).strip().lower() for v in policy_aspect.allowed_extra_prefixes if str(v).strip()
        ),
        source="aspect",
    )
    logger.debug(
        "Resolved icebergNamespacePolicy from aspect_id=%s for scope=%s",
        aspect_row.id,
        scope_urn,
    )
    return resolved, str(aspect_row.id)


def resolve_policy(
    *,
    scope_urn: str | None = None,
    context: Any | None = None,
) -> EffectivePolicy:
    """Resolve the effective policy for one scope URN (exact-match lookup)."""
    _ = context
    if scope_urn is None:
        logger.debug("No scope_urn supplied; using DEFAULT_POLICY")
        return DEFAULT_POLICY
    parse_urn(scope_urn)
    try:
        with get_session() as session:
            policy, _aspect_id = _resolve_with_session(session=session, scope_urn=scope_urn)
            return policy
    except Exception:  # noqa: BLE001
        logger.debug(
            "Namespace policy lookup failed for scope=%s; using defaults",
            scope_urn,
            exc_info=True,
        )
        return DEFAULT_POLICY


def expected_prefix(layer: str, *, policy: EffectivePolicy | None = None) -> str:
    """Return the expected namespace prefix for ``layer`` under ``policy``."""
    effective = policy or DEFAULT_POLICY
    layer_clean = str(layer or "").strip().lower()
    if layer_clean == "bronze":
        return effective.bronze_prefix
    if layer_clean == "silver":
        return effective.silver_prefix
    if layer_clean == "gold":
        return effective.gold_prefix
    raise ValueError(
        f"unknown medallion_layer {layer!r}; expected one of ['bronze', 'silver', 'gold']"
    )


def validate_namespace_with_policy(
    layer: str | None,
    namespace: str,
    *,
    policy: EffectivePolicy | None = None,
) -> None:
    """Validate namespace/layer alignment with reserved + override policy."""
    effective = policy or DEFAULT_POLICY
    namespace_clean = _namespace_head(namespace)
    if not namespace_clean:
        raise ValueError("namespace cannot be empty")

    if namespace_clean in RESERVED_NAMESPACES:
        raise ValueError(f"namespace {namespace_clean!r} is reserved and cannot be written")
    for forbidden in effective.forbidden_prefixes:
        if _matches_prefix(namespace_clean, forbidden):
            raise ValueError(
                f"namespace {namespace_clean!r} is forbidden by policy prefix {forbidden!r}"
            )

    if any(_matches_prefix(namespace_clean, prefix) for prefix in effective.allowed_extra_prefixes):
        return
    if layer is None:
        return

    expected = expected_prefix(layer, policy=effective)
    if _matches_prefix(namespace_clean, expected):
        return
    raise ValueError(
        f"medallion_layer={layer!r} requires namespace prefix {expected!r}; "
        f"got {namespace_clean!r}"
    )


def derive_scope_urn(context: Any) -> str | None:
    """Derive scope URN from request context (project -> workspace)."""
    if context is None:
        return None
    if isinstance(context, dict):
        project_id = context.get("project_id")
        workspace_id = context.get("workspace_id")
    else:
        project_id = getattr(context, "project_id", None)
        workspace_id = getattr(context, "workspace_id", None)
    return _coerce_scope_urn(workspace_id=workspace_id, project_id=project_id)


def clear_namespace_policy_cache() -> None:
    """Backward-compatible no-op cache clearer."""
    return None


def resolve_namespace_policy(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    domain: str | None = None,
    env: str | None = None,
    session: Session | None = None,
) -> ResolvedNamespacePolicy:
    """Backward-compatible shim over :func:`resolve_policy`."""
    _ = (domain, env)
    scope_urn = _coerce_scope_urn(workspace_id=workspace_id, project_id=project_id)
    if scope_urn is None:
        policy = DEFAULT_POLICY
        aspect_id = None
    elif session is not None:
        parse_urn(scope_urn)
        policy, aspect_id = _resolve_with_session(session=session, scope_urn=scope_urn)
    else:
        try:
            with get_session() as managed_session:
                policy, aspect_id = _resolve_with_session(
                    session=managed_session,
                    scope_urn=scope_urn,
                )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Legacy resolve_namespace_policy lookup failed for scope=%s",
                scope_urn,
                exc_info=True,
            )
            policy = DEFAULT_POLICY
            aspect_id = None
    return ResolvedNamespacePolicy(
        effective_prefixes={
            "bronze": policy.bronze_prefix,
            "silver": policy.silver_prefix,
            "gold": policy.gold_prefix,
        },
        extra_allowed_namespaces=tuple(sorted(policy.allowed_extra_prefixes)),
        source_aspect_ids=((aspect_id,) if (policy.source == "aspect" and aspect_id) else ()),
        is_default=policy.source == "default",
    )


def get_effective_prefix(
    layer: str,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    domain: str | None = None,
) -> str:
    """Backward-compatible prefix helper for legacy callers."""
    _ = domain
    scope_urn = _coerce_scope_urn(workspace_id=workspace_id, project_id=project_id)
    return expected_prefix(layer, policy=resolve_policy(scope_urn=scope_urn))


def is_allowed_extra_namespace(
    namespace: str,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    domain: str | None = None,
) -> bool:
    """Backward-compatible helper for legacy allow-list checks."""
    _ = domain
    scope_urn = _coerce_scope_urn(workspace_id=workspace_id, project_id=project_id)
    policy = resolve_policy(scope_urn=scope_urn)
    namespace_clean = _namespace_head(namespace)
    return any(
        _matches_prefix(namespace_clean, prefix) for prefix in policy.allowed_extra_prefixes
    )


__all__ = [
    "DEFAULT_POLICY",
    "EffectivePolicy",
    "RESERVED_NAMESPACES",
    "ResolvedNamespacePolicy",
    "clear_namespace_policy_cache",
    "derive_scope_urn",
    "expected_prefix",
    "get_effective_prefix",
    "is_allowed_extra_namespace",
    "resolve_namespace_policy",
    "resolve_policy",
    "validate_namespace_with_policy",
]
