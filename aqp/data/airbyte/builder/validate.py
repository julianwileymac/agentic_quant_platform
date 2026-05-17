"""Structural validation for the visual builder state."""
from __future__ import annotations

from typing import Any

ALLOWED_AUTH_KINDS = {"none", "bearer", "header", "query", "basic"}
ALLOWED_PAGINATOR_KINDS = {
    "none",
    "page_increment",
    "offset_increment",
    "cursor_field",
    "next_link_url",
}
ALLOWED_METHODS = {"GET", "POST", "PUT"}


def validate_manifest(state: dict[str, Any]) -> dict[str, list[str]]:
    """Return ``{"errors": [...], "warnings": [...]}`` for ``state``.

    The frontend surfaces both lists; the codegen helpers raise on
    non-empty errors.
    """
    errors: list[str] = []
    warnings: list[str] = []

    metadata = state.get("metadata") or {}
    connector_id = str(metadata.get("connector_id") or "").strip().lower()
    if not connector_id:
        errors.append("metadata.connector_id is required")
    elif not connector_id.replace("-", "_").replace("_", "").isalnum():
        errors.append("metadata.connector_id must be alphanumeric / dashes / underscores only")
    if not str(metadata.get("display_name") or "").strip():
        errors.append("metadata.display_name is required")

    auth = state.get("auth") or {}
    auth_kind = str(auth.get("auth_kind") or "none").lower()
    if auth_kind not in ALLOWED_AUTH_KINDS:
        errors.append(f"auth.auth_kind must be one of {sorted(ALLOWED_AUTH_KINDS)}")
    elif auth_kind != "none" and not str(auth.get("credential_ref") or "").strip():
        errors.append(
            "auth.credential_ref is required when auth_kind is not 'none' "
            "(picked through EntityPicker kind=credentials)"
        )
    if auth_kind == "header" and not str(auth.get("auth_header_name") or "").strip():
        warnings.append("header auth without auth_header_name; defaulting to 'Authorization'")

    requester = state.get("requester") or {}
    if not str(requester.get("base_url") or "").strip():
        errors.append("requester.base_url is required")
    method = str(requester.get("method") or "GET").upper()
    if method not in ALLOWED_METHODS:
        errors.append(f"requester.method must be one of {sorted(ALLOWED_METHODS)}")

    paginator = state.get("paginator") or {}
    paginator_kind = str(paginator.get("paginator_kind") or "none").lower()
    if paginator_kind not in ALLOWED_PAGINATOR_KINDS:
        errors.append(f"paginator.paginator_kind must be one of {sorted(ALLOWED_PAGINATOR_KINDS)}")
    if paginator_kind == "cursor_field" and not str(paginator.get("cursor_field") or "").strip():
        errors.append("paginator.cursor_field is required for cursor_field strategy")

    streams = state.get("streams") or []
    if not isinstance(streams, list) or not streams:
        errors.append("at least one stream is required")
    else:
        seen: set[str] = set()
        for idx, stream in enumerate(streams):
            name = str(stream.get("name") or "").strip()
            if not name:
                errors.append(f"streams[{idx}].name is required")
                continue
            if name in seen:
                errors.append(f"duplicate stream name: {name!r}")
            seen.add(name)
            if not str(stream.get("path") or "").strip():
                errors.append(f"streams[{idx}].path is required")

    return {"errors": errors, "warnings": warnings}


__all__ = ["validate_manifest"]
