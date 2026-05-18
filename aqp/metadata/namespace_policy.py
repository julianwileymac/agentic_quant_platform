"""Aspect-driven Iceberg medallion namespace policy.

Resolves a layer-prefix at runtime by consulting the entity_aspects
store first; falls back to the hardcoded LAYER_PREFIXES defaults when
no policy aspect matches the active workspace / project / domain.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Literal

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from aqp.cache.invalidation import cache_write_through
from aqp.cache.keys import by_id_hash
from aqp.cache.client import get_cache
from aqp.metadata.openmetadata import IcebergNamespacePolicy
from aqp.metadata.urn import parse_urn
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect

logger = logging.getLogger(__name__)

MedallionLayer = Literal["bronze", "silver", "gold"]

DEFAULT_PREFIXES: dict[MedallionLayer, str] = {
    "bronze": "aqp_bronze_",
    "silver": "aqp_silver_",
    "gold": "aqp_gold_",
}

_POLICY_CACHE_TTL_SECONDS = 60
_SCOPE_WILDCARD = "*"


@dataclass(frozen=True, slots=True)
class ResolvedPolicy:
    """Concrete medallion prefix policy materialized for one runtime scope."""

    bronze: str
    silver: str
    gold: str
    policy_urn: str | None
    priority: int
    source: Literal["aspect", "default"]

    def prefix_for(self, layer: MedallionLayer) -> str:
        """Return the namespace prefix for a medallion ``layer``."""
        if layer == "bronze":
            return self.bronze
        if layer == "silver":
            return self.silver
        return self.gold


def _normalise_scope_value(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _cache_scope_key(
    workspace_id: str | None,
    project_id: str | None,
    domain_pattern: str | None,
) -> str:
    return "|".join(
        (
            workspace_id or _SCOPE_WILDCARD,
            project_id or _SCOPE_WILDCARD,
            domain_pattern or _SCOPE_WILDCARD,
        )
    )


def _policy_cache_payload(
    policy: IcebergNamespacePolicy,
    *,
    aspect_id: str | None,
    version: int | None,
) -> dict[str, object]:
    scope_key = _cache_scope_key(
        policy.applies_to_workspace_id,
        policy.applies_to_project_id,
        policy.applies_to_domain_pattern,
    )
    return {
        "id": scope_key,
        "name": scope_key,
        "policy_urn": policy.urn,
        "policy_name": policy.policy_name,
        "workspace_id": policy.applies_to_workspace_id or "",
        "project_id": policy.applies_to_project_id or "",
        "domain_pattern": policy.applies_to_domain_pattern or "",
        "priority": int(policy.priority),
        "bronze_prefix": policy.bronze_prefix,
        "silver_prefix": policy.silver_prefix,
        "gold_prefix": policy.gold_prefix,
        "aspect_id": aspect_id or "",
        "version": int(version or 0),
        "updated_at": datetime.utcnow().isoformat(),
    }


def _resolved_from_policy(policy: IcebergNamespacePolicy) -> ResolvedPolicy:
    return ResolvedPolicy(
        bronze=policy.bronze_prefix,
        silver=policy.silver_prefix,
        gold=policy.gold_prefix,
        policy_urn=policy.urn,
        priority=int(policy.priority),
        source="aspect",
    )


def _default_resolved_policy() -> ResolvedPolicy:
    return ResolvedPolicy(
        bronze=DEFAULT_PREFIXES["bronze"],
        silver=DEFAULT_PREFIXES["silver"],
        gold=DEFAULT_PREFIXES["gold"],
        policy_urn=None,
        priority=0,
        source="default",
    )


def _policy_matches_context(
    policy: IcebergNamespacePolicy,
    *,
    workspace_id: str | None,
    project_id: str | None,
    domain: str | None,
) -> bool:
    workspace_match = (
        policy.applies_to_workspace_id is None
        or policy.applies_to_workspace_id == workspace_id
    )
    if not workspace_match:
        return False

    project_match = (
        policy.applies_to_project_id is None
        or policy.applies_to_project_id == project_id
    )
    if not project_match:
        return False

    pattern = _normalise_scope_value(policy.applies_to_domain_pattern)
    if pattern is None:
        return True
    if not domain:
        return False
    try:
        return bool(re.match(pattern, domain))
    except re.error:
        logger.warning(
            "Skipping invalid applies_to_domain_pattern for policy %s: %r",
            policy.urn,
            pattern,
            exc_info=True,
        )
        return False


def _latest_policy_rows(
    *,
    session: Session,
    workspace_id: str | None,
) -> list[EntityAspect]:
    stmt = select(EntityAspect).where(
        EntityAspect.aspect_name == IcebergNamespacePolicy.aspect_name
    )
    if workspace_id is None:
        stmt = stmt.where(EntityAspect.workspace_id.is_(None))
    else:
        stmt = stmt.where(
            or_(
                EntityAspect.workspace_id == workspace_id,
                EntityAspect.workspace_id.is_(None),
            )
        )
    rows = session.execute(
        stmt.order_by(
            EntityAspect.urn.asc(),
            desc(EntityAspect.version),
            desc(EntityAspect.created_at),
        )
    ).scalars().all()

    latest_by_urn: dict[str, EntityAspect] = {}
    for row in rows:
        urn = str(row.urn)
        if urn not in latest_by_urn:
            latest_by_urn[urn] = row
    return list(latest_by_urn.values())


def _candidate_scope_keys(
    *,
    workspace_id: str | None,
    project_id: str | None,
    domain: str | None,
) -> list[str]:
    workspace_options = [workspace_id, None]
    project_options = [project_id, None]
    domain_options = [domain, None]

    keys: list[str] = []
    for workspace_option in workspace_options:
        for project_option in project_options:
            for domain_option in domain_options:
                keys.append(
                    _cache_scope_key(
                        workspace_option,
                        project_option,
                        domain_option,
                    )
                )
    return keys


def _resolve_from_cache(
    *,
    workspace_id: str | None,
    project_id: str | None,
    domain: str | None,
) -> ResolvedPolicy | None:
    try:
        cache = get_cache()
    except Exception:  # pragma: no cover - defensive
        return None

    candidates: list[tuple[int, ResolvedPolicy]] = []
    for scope_key in _candidate_scope_keys(
        workspace_id=workspace_id,
        project_id=project_id,
        domain=domain,
    ):
        payload = cache.hgetall(by_id_hash("namespace_policies", scope_key))
        if not payload:
            continue
        try:
            priority = int(payload.get("priority") or 0)
            resolved = ResolvedPolicy(
                bronze=str(payload["bronze_prefix"]),
                silver=str(payload["silver_prefix"]),
                gold=str(payload["gold_prefix"]),
                policy_urn=str(payload.get("policy_urn") or "") or None,
                priority=priority,
                source="aspect",
            )
        except Exception:
            logger.debug(
                "Skipping malformed namespace policy cache payload key=%s",
                scope_key,
                exc_info=True,
            )
            continue
        candidates.append((priority, resolved))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _resolve_namespace_policy_uncached(
    *,
    workspace_id: str | None,
    project_id: str | None,
    domain: str | None,
    session: Session | None,
) -> ResolvedPolicy:
    cached = _resolve_from_cache(
        workspace_id=workspace_id,
        project_id=project_id,
        domain=domain,
    )
    if cached is not None:
        return cached

    def _resolve_with_session(db: Session) -> ResolvedPolicy:
        rows = _latest_policy_rows(session=db, workspace_id=workspace_id)
        matches: list[IcebergNamespacePolicy] = []
        for row in rows:
            payload = row.payload if isinstance(row.payload, dict) else {}
            try:
                policy = IcebergNamespacePolicy.model_validate(payload)
            except Exception:
                logger.debug(
                    "Skipping invalid icebergNamespacePolicy payload id=%s",
                    row.id,
                    exc_info=True,
                )
                continue
            if not _policy_matches_context(
                policy,
                workspace_id=workspace_id,
                project_id=project_id,
                domain=domain,
            ):
                continue
            matches.append(policy)

        if not matches:
            return _default_resolved_policy()
        matches.sort(key=lambda policy: int(policy.priority), reverse=True)
        return _resolved_from_policy(matches[0])

    if session is not None:
        return _resolve_with_session(session)
    with get_session() as managed_session:
        return _resolve_with_session(managed_session)


@lru_cache(maxsize=512)
def _resolve_namespace_policy_cached(
    workspace_id: str | None,
    project_id: str | None,
    domain: str | None,
    ttl_bucket: int,
) -> ResolvedPolicy:
    del ttl_bucket
    return _resolve_namespace_policy_uncached(
        workspace_id=workspace_id,
        project_id=project_id,
        domain=domain,
        session=None,
    )


def clear_policy_cache() -> None:
    """Clear the in-process namespace policy resolver cache."""
    _resolve_namespace_policy_cached.cache_clear()


def resolve_namespace_policy(
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    domain: str | None = None,
    session: Session | None = None,
) -> ResolvedPolicy:
    """Resolve the effective medallion namespace policy for a runtime scope."""
    workspace_key = _normalise_scope_value(workspace_id)
    project_key = _normalise_scope_value(project_id)
    domain_key = _normalise_scope_value(domain)
    if session is not None:
        return _resolve_namespace_policy_uncached(
            workspace_id=workspace_key,
            project_id=project_key,
            domain=domain_key,
            session=session,
        )
    ttl_bucket = int(time.time() // _POLICY_CACHE_TTL_SECONDS)
    return _resolve_namespace_policy_cached(
        workspace_key,
        project_key,
        domain_key,
        ttl_bucket,
    )


def register_namespace_policy(
    policy: IcebergNamespacePolicy,
    *,
    session: Session | None = None,
) -> str:
    """Write an immutable ``icebergNamespacePolicy`` aspect and refresh caches."""
    policy = IcebergNamespacePolicy.model_validate(policy.model_dump(mode="json"))
    parse_urn(policy.urn)

    def _write(db: Session) -> tuple[str | None, int | None]:
        from aqp.metadata import write_aspect

        aspect = write_aspect(
            db,
            policy.urn,
            IcebergNamespacePolicy.aspect_name,
            policy,
        )
        return str(aspect.id), int(aspect.version)

    if session is not None:
        aspect_id, version = _write(session)
    else:
        with get_session() as managed_session:
            aspect_id, version = _write(managed_session)

    cache_write_through(
        "namespace_policies",
        _policy_cache_payload(
            policy,
            aspect_id=aspect_id,
            version=version,
        ),
    )
    clear_policy_cache()
    return policy.urn


__all__ = [
    "DEFAULT_PREFIXES",
    "ResolvedPolicy",
    "clear_policy_cache",
    "register_namespace_policy",
    "resolve_namespace_policy",
]
