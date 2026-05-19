"""Auth0 custom-claim namespace helpers.

The canonical namespace is ``https://aqp.internal/``. The legacy
``https://aqp/`` namespace stays readable for one release while
existing tokens age out — see ADR 003.

Use :func:`extract_claim` instead of bare ``payload[key]`` to get
backward-compat lookup against both namespaces for free.
"""
from __future__ import annotations

from typing import Any

CANONICAL_CLAIMS_NAMESPACE = "https://aqp.internal/"
LEGACY_CLAIMS_NAMESPACE = "https://aqp/"

# Canonical claim names used across the platform.
CLAIM_ORG_ID = "org_id"
CLAIM_WORKSPACE_ID = "workspace_id"
CLAIM_TEAM_IDS = "team_ids"
CLAIM_ROLES = "roles"
CLAIM_RESOURCES = "resources"
CLAIM_SCOPES = "scopes"


def claim_key(name: str, *, namespace: str = CANONICAL_CLAIMS_NAMESPACE) -> str:
    """Build the fully-qualified claim key for ``name`` in ``namespace``.

    ``claim_key("resources")`` -> ``"https://aqp.internal/resources"``.
    """
    if not namespace.endswith("/"):
        namespace = namespace + "/"
    return f"{namespace}{name}"


def extract_claim(
    payload: dict[str, Any],
    name: str,
    *,
    default: Any = None,
    namespaces: tuple[str, ...] = (CANONICAL_CLAIMS_NAMESPACE, LEGACY_CLAIMS_NAMESPACE),
) -> Any:
    """Return ``payload[<namespace><name>]`` for the first matching namespace.

    Tries each entry in ``namespaces`` in order. Returns ``default`` if
    no key is present. This is the canonical way to read AQP custom
    claims — never index ``payload`` directly because the namespace
    migration is in flight.
    """
    for ns in namespaces:
        key = claim_key(name, namespace=ns)
        if key in payload:
            return payload[key]
    return default


__all__ = [
    "CANONICAL_CLAIMS_NAMESPACE",
    "LEGACY_CLAIMS_NAMESPACE",
    "CLAIM_ORG_ID",
    "CLAIM_WORKSPACE_ID",
    "CLAIM_TEAM_IDS",
    "CLAIM_ROLES",
    "CLAIM_RESOURCES",
    "CLAIM_SCOPES",
    "claim_key",
    "extract_claim",
]
