"""Cedar policy engine integration for AQP application-layer authz.

Phase 4 §7.3 (RESTRUCTURING_PLAN.md). Sits ALONGSIDE the existing
:mod:`aqp.api.security` (``require_scope`` / ``require_membership``) and
:mod:`aqp_platform_core.auth.resource_filter` — Cedar is the per-action
decision point for the ``/manage/*`` API surface and the agent-sandbox
tool surface. Resource filter stays for the high-throughput list-endpoint
case where evaluating Cedar on every row would dominate the budget.

The split:

- ``require_scope(...)`` — fast scope membership check, runs first.
- ``require_membership(...)`` — workspace / org membership check.
- ``require_cedar(action, resource_kind)`` — Cedar policy evaluation
  over the active :class:`RequestContext` + a typed resource entity.

Cedar policies live at
``aqp_platform/configs/cedar/policies/*.cedar`` and are loaded once
at process start. Each evaluation gets:

- ``principal`` = the authenticated :class:`CurrentUser` projected to
  a Cedar entity ``User::"<sub>"`` carrying scope / role / clearance
  attributes from the JWT claims namespace.
- ``action`` = ``Action::"<verb>"`` (e.g. ``Action::"manage_cell"``).
- ``resource`` = ``<Kind>::"<id>"`` with attributes from the inbound
  pydantic model.
- ``context`` = the per-request map (cell_id, region, source_ip, ...).

The decision MUST land in the audit ledger so a regulator can
reconstruct "who could have done X at time Y given policy state Z".
The :func:`_audit_decision` helper emits a structured log line plus
an OTEL span attribute ``aqp.cedar.decision`` that the kube-prom-stack
scrapes into Phoenix.

The Cedar engine is OPTIONAL — when ``cedarpy`` is not installed the
helper degrades to a deny-all gate with a logged-warning so we never
inadvertently allow an action that should have been Cedar-gated.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from aqp.auth.context import RequestContext
from aqp.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Policy loader
# ---------------------------------------------------------------------------


_POLICIES_DIR_DEFAULT = Path("aqp_platform/configs/cedar/policies")


@dataclass(frozen=True)
class CedarPolicySet:
    """In-memory snapshot of the loaded Cedar policy bundle."""

    policy_text: str
    policy_paths: tuple[str, ...]
    loaded_at: float

    def is_empty(self) -> bool:
        return not self.policy_text.strip()


_POLICY_SET: CedarPolicySet | None = None
_POLICY_LOCK = threading.RLock()


def _resolve_policies_dir() -> Path:
    """Return the directory holding ``.cedar`` policy files.

    Operators override via ``AQP_CEDAR_POLICIES_DIR``. The default points
    at the in-tree bundle so local development uses the canonical
    policies without extra configuration.
    """
    override = getattr(settings, "cedar_policies_dir", None) or ""
    if override:
        return Path(override)
    return _POLICIES_DIR_DEFAULT


def load_policies(force: bool = False) -> CedarPolicySet:
    """Load every ``*.cedar`` file under the policies directory.

    Cached for the process lifetime. Pass ``force=True`` to reload
    (used by the ``/manage/cedar/reload`` admin route, not in scope
    for Phase 4 but the lock keeps the door open).
    """
    global _POLICY_SET
    with _POLICY_LOCK:
        if _POLICY_SET is not None and not force:
            return _POLICY_SET
        directory = _resolve_policies_dir()
        if not directory.exists():
            logger.warning(
                "cedar: policies dir %s does not exist; using empty policy set",
                directory,
            )
            _POLICY_SET = CedarPolicySet(
                policy_text="", policy_paths=(), loaded_at=_now()
            )
            return _POLICY_SET
        paths: list[Path] = sorted(directory.glob("*.cedar"))
        parts: list[str] = []
        for p in paths:
            try:
                parts.append(f"// {p.name}\n{p.read_text(encoding='utf-8')}\n")
            except OSError:
                logger.exception("cedar: failed to read %s", p)
        _POLICY_SET = CedarPolicySet(
            policy_text="\n".join(parts),
            policy_paths=tuple(str(p) for p in paths),
            loaded_at=_now(),
        )
        logger.info(
            "cedar: loaded %d policy file(s) from %s",
            len(paths),
            directory,
        )
        return _POLICY_SET


def reset_cedar_cache() -> None:
    """Reset the cached policy set. Tests + admin reload."""
    global _POLICY_SET
    with _POLICY_LOCK:
        _POLICY_SET = None


def _now() -> float:
    import time

    return time.monotonic()


# ---------------------------------------------------------------------------
# Engine — thin wrapper around cedarpy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CedarRequest:
    """Inputs for one Cedar evaluation."""

    principal: str  # e.g. ``User::"auth0|abc"``
    action: str  # e.g. ``Action::"manage_cell"``
    resource: str  # e.g. ``Cell::"cell-shared-std-us-east-1a"``
    context: dict[str, Any] = field(default_factory=dict)
    entities: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class CedarDecision:
    decision: str  # "Allow" | "Deny"
    matched_policies: tuple[str, ...]
    reasons: tuple[str, ...]
    errors: tuple[str, ...]

    def is_allowed(self) -> bool:
        return self.decision == "Allow"


def evaluate(req: CedarRequest) -> CedarDecision:
    """Evaluate ``req`` against the loaded policy set.

    Returns a structured :class:`CedarDecision`. The function is
    defensive: when ``cedarpy`` is not installed (the runtime image
    didn't pull the ``[auth]`` extra) it returns ``Deny`` with a
    descriptive reason so callers can fall back to the stricter path
    (or surface the misconfiguration via the audit ledger).
    """
    try:
        import cedarpy
    except ImportError:
        return CedarDecision(
            decision="Deny",
            matched_policies=(),
            reasons=("cedarpy not installed; install the [auth] extra",),
            errors=("cedarpy_missing",),
        )

    policies = load_policies()
    if policies.is_empty():
        return CedarDecision(
            decision="Deny",
            matched_policies=(),
            reasons=("no Cedar policies loaded",),
            errors=("empty_policy_set",),
        )

    request_json = {
        "principal": req.principal,
        "action": req.action,
        "resource": req.resource,
        "context": req.context or {},
    }
    entities_json = list(req.entities or [])

    try:
        # cedarpy 4.x signature:
        #   is_authorized(request: dict, policies: str, entities: list[dict]) -> AuthzResult
        result = cedarpy.is_authorized(  # type: ignore[attr-defined]
            request=request_json,
            policies=policies.policy_text,
            entities=entities_json,
        )
    except Exception as exc:  # noqa: BLE001 - defensive against cedarpy errors
        logger.exception("cedar: evaluation failed for %s/%s", req.action, req.resource)
        return CedarDecision(
            decision="Deny",
            matched_policies=(),
            reasons=(f"cedar evaluation raised: {exc}",),
            errors=("evaluation_error",),
        )

    # cedarpy.AuthzResult.decision is a `cedarpy.Decision` enum
    # (Allow / Deny); normalise to a bare string for the dataclass.
    raw_decision = getattr(result, "decision", None)
    if raw_decision is None:
        decision = "Deny"
    else:
        decision = raw_decision.name if hasattr(raw_decision, "name") else str(raw_decision)
    diag = getattr(result, "diagnostics", None)
    if diag is None:
        matched: tuple[str, ...] = ()
        errors: tuple[str, ...] = ()
    else:
        # `Diagnostics` exposes `reason` (a list) + `errors` (a list).
        # Older cedarpy variants used `reasons`; check both.
        reasons_raw = (
            getattr(diag, "reason", None)
            or getattr(diag, "reasons", None)
            or (diag.get("reasons", None) if isinstance(diag, dict) else None)
            or ()
        )
        errors_raw = (
            getattr(diag, "errors", None)
            or (diag.get("errors", None) if isinstance(diag, dict) else None)
            or ()
        )
        matched = tuple(str(p) for p in reasons_raw)
        errors = tuple(str(e) for e in errors_raw)
    return CedarDecision(
        decision=decision,
        matched_policies=matched,
        reasons=matched,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


# Bound at first use; callers from `aqp.api.security` provide
# the existing require_authenticated dep so we don't take a hard
# import-time dep that would create a cycle.
_REQUIRE_AUTH_DEP: Callable[..., Any] | None = None


def set_require_auth_dep(dep: Callable[..., Any]) -> None:
    """Wire the auth dependency. Called by ``aqp/api/__init__.py``.

    Lets ``require_cedar`` reuse the existing JWT validation chain
    without re-importing ``aqp.api.security`` (which would create an
    import cycle since some auth providers themselves want Cedar gates).
    """
    global _REQUIRE_AUTH_DEP
    _REQUIRE_AUTH_DEP = dep


def _get_require_auth_dep() -> Callable[..., Any]:
    if _REQUIRE_AUTH_DEP is None:
        from aqp.api.security import require_authenticated

        return require_authenticated
    return _REQUIRE_AUTH_DEP


def _project_principal(user: Any) -> tuple[str, dict[str, Any]]:
    """Build the Cedar principal id + the entity attribute dict.

    The principal is ``User::"<sub>"``; the entity carries the user's
    org_id, roles, scopes, and clearances so the policies can reference
    them in their ``when {...}`` conditions.
    """
    sub = str(getattr(user, "sub", None) or getattr(user, "user_id", "anon"))
    roles = list(getattr(user, "roles", None) or ())
    scopes = list(getattr(user, "scopes", None) or ())
    clearances = list(getattr(user, "clearances", None) or ())
    attrs: dict[str, Any] = {
        "org_id": getattr(user, "org_id", None),
        "workspace_id": getattr(user, "workspace_id", None),
        "roles": roles,
        "scopes": scopes,
        "clearances": clearances,
    }
    # Filter out None values so Cedar doesn't see absent attrs as
    # explicit null (Cedar treats `principal has attr` as the gate).
    attrs = {k: v for k, v in attrs.items() if v is not None}
    return f'User::"{sub}"', attrs


def _project_resource(resource_kind: str, resource_id: str, attrs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Build the Cedar resource id + entity attrs from the route input."""
    return f'{resource_kind}::"{resource_id}"', dict(attrs)


def _audit_decision(
    *,
    user: Any,
    action: str,
    resource_id: str,
    decision: CedarDecision,
    request: Request,
) -> None:
    """Emit a structured audit line + OTEL span attribute."""
    log_payload = {
        "user_id": getattr(user, "sub", None),
        "action": action,
        "resource_id": resource_id,
        "decision": decision.decision,
        "matched_policies": list(decision.matched_policies),
        "errors": list(decision.errors),
        "request_id": request.headers.get("X-Request-Id"),
    }
    logger.info("cedar_decision %s", json.dumps(log_payload, default=str))
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is not None:
            span.set_attribute("aqp.cedar.decision", decision.decision)
            span.set_attribute("aqp.cedar.action", action)
            span.set_attribute("aqp.cedar.resource_id", resource_id)
            if decision.matched_policies:
                span.set_attribute(
                    "aqp.cedar.matched_policies",
                    ",".join(decision.matched_policies),
                )
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - never break the request on OTEL errors
        logger.debug("failed to stamp aqp.cedar.* span attributes", exc_info=True)


def require_cedar(
    action: str,
    resource_kind: str,
    *,
    resource_id_extractor: Callable[[Request], str] | None = None,
    resource_attrs_extractor: Callable[[Request], dict[str, Any]] | None = None,
) -> Callable[..., Any]:
    """Build a FastAPI dependency that evaluates Cedar before the route runs.

    The dep:

    1. Resolves the authenticated user via the existing auth chain.
    2. Extracts the resource id + attributes from the inbound request.
    3. Evaluates Cedar; raises 403 on ``Deny`` (or on ``cedarpy_missing``
       when running in strict mode).
    4. Stamps the audit ledger via :func:`_audit_decision`.

    Example::

        from aqp.api.security_cedar import require_cedar

        @router.post("/manage/cells/{cell_id}/state")
        async def update_cell_state(
            cell_id: str,
            state: str = Body(..., embed=True),
            user: CurrentUser = Depends(
                require_cedar(
                    "manage_cell",
                    resource_kind="Cell",
                    resource_id_extractor=lambda r: r.path_params["cell_id"],
                )
            ),
        ): ...

    The default extractors derive the resource id from the ``id``
    path parameter (or query parameter, if no path match) and pass
    the remaining path / query parameters as resource attributes.
    """

    def _default_resource_id(request: Request) -> str:
        # Common URL shapes: /resource/{id}, /resource/{kind}_id, /resource?id=...
        for key in ("id", "cell_id", "workspace_id", "project_id", "experiment_id"):
            v = request.path_params.get(key) or request.query_params.get(key)
            if v:
                return str(v)
        return "*"

    def _default_resource_attrs(request: Request) -> dict[str, Any]:
        return dict(request.query_params)

    extractor_id = resource_id_extractor or _default_resource_id
    extractor_attrs = resource_attrs_extractor or _default_resource_attrs

    def _dep(request: Request, user: Any = Depends(_get_require_auth_dep())) -> Any:
        principal_id, principal_attrs = _project_principal(user)
        resource_id = extractor_id(request)
        resource_id_full, resource_attrs = _project_resource(
            resource_kind, resource_id, extractor_attrs(request)
        )

        # Build the entities list. Cedar needs explicit entity rows
        # carrying the attribute maps for both principal and resource.
        entities = [
            {
                "uid": {"type": "User", "id": principal_id.split('::')[1].strip('"')},
                "attrs": principal_attrs,
                "parents": [],
            },
            {
                "uid": {
                    "type": resource_kind,
                    "id": resource_id_full.split('::')[1].strip('"'),
                },
                "attrs": resource_attrs,
                "parents": [],
            },
        ]

        # Read the per-request cell_id from the request context, if any.
        ctx_attrs: dict[str, Any] = {}
        rc = getattr(request.state, "aqp_context", None)
        if rc is not None:
            for attr_name in (
                "cell_id",
                "region",
                "tenancy_strategy_alias",
                "workspace_id",
                "project_id",
            ):
                v = getattr(rc, attr_name, None)
                if v is not None:
                    ctx_attrs[attr_name] = v

        decision = evaluate(
            CedarRequest(
                principal=principal_id,
                action=f'Action::"{action}"',
                resource=resource_id_full,
                context=ctx_attrs,
                entities=entities,
            )
        )
        _audit_decision(
            user=user,
            action=action,
            resource_id=resource_id_full,
            decision=decision,
            request=request,
        )
        if not decision.is_allowed():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "cedar_denied",
                    "action": action,
                    "resource": resource_id_full,
                    "errors": list(decision.errors),
                },
            )
        return user

    return _dep


__all__ = [
    "CedarDecision",
    "CedarPolicySet",
    "CedarRequest",
    "evaluate",
    "load_policies",
    "require_cedar",
    "reset_cedar_cache",
    "set_require_auth_dep",
]
