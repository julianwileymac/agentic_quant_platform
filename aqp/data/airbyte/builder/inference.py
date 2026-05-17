"""Schema-inference utility for the visual builder.

Issues a single test request via httpx (with the configured
credential picked through the resolver) and walks the response to
infer top-level field names + JSON types so the operator can pick
streams without writing the schema by hand.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def infer_streams(state: dict[str, Any]) -> dict[str, Any]:
    """Issue a single probe request and infer stream schema.

    Returns ``{"ok": bool, "streams": [...], "preview": {...}}``.
    ``streams`` is a list of ``{name, fields}`` dicts. ``fields`` is
    a list of ``{name, type}`` pairs. ``preview`` is the first three
    decoded records (truncated to keep the response payload small).
    """
    requester = state.get("requester") or {}
    extractor = state.get("extractor") or {}
    streams = state.get("streams") or []
    if not streams:
        return {"ok": False, "error": "no streams configured", "streams": []}
    base_url = str(requester.get("base_url") or "").rstrip("/")
    method = str(requester.get("method") or "GET").upper()
    timeout_s = float(requester.get("timeout_s") or 30.0)
    headers = dict(requester.get("default_headers") or {})
    params = dict(requester.get("default_params") or {})
    record_path = str(extractor.get("record_path") or "$")
    auth = state.get("auth") or {}
    auth_kind = str(auth.get("auth_kind") or "none").lower()
    credential_ref = str(auth.get("credential_ref") or "").strip()

    token = _resolve_credential(credential_ref, auth_kind) if auth_kind != "none" else None
    if token:
        if auth_kind == "bearer":
            headers.setdefault("Authorization", f"Bearer {token}")
        elif auth_kind == "header":
            headers.setdefault(str(auth.get("auth_header_name") or "Authorization"), token)
        elif auth_kind == "query":
            params.setdefault(str(auth.get("auth_query_field") or "api_key"), token)

    try:
        import httpx
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"httpx unavailable: {exc}", "streams": []}

    out: list[dict[str, Any]] = []
    preview: dict[str, Any] = {}
    for stream in streams:
        name = str(stream.get("name") or "").strip()
        path = str(stream.get("path") or "").strip()
        if not name or not path:
            continue
        url = f"{base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.request(method, url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            out.append({"name": name, "fields": [], "error": str(exc)})
            continue
        records = _walk_record_path(payload, record_path)
        sample = records if isinstance(records, list) else [records] if records else []
        sample = sample[:3]
        fields_seen: dict[str, set[str]] = {}
        for record in sample:
            if not isinstance(record, dict):
                continue
            for key, value in record.items():
                fields_seen.setdefault(str(key), set()).add(_type_name(value))
        out.append(
            {
                "name": name,
                "fields": [
                    {"name": k, "type": ", ".join(sorted(v))}
                    for k, v in sorted(fields_seen.items())
                ],
            }
        )
        preview[name] = sample
    return {"ok": True, "streams": out, "preview": preview}


def _walk_record_path(payload: Any, path: str) -> Any:
    cursor = payload
    for segment in path.split("."):
        segment = segment.strip()
        if not segment or segment == "$":
            continue
        if isinstance(cursor, dict):
            cursor = cursor.get(segment)
        elif isinstance(cursor, list):
            try:
                cursor = cursor[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cursor


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _resolve_credential(ref: str, _auth_kind: str) -> str | None:
    if not ref:
        return None
    try:
        from aqp.credentials import CredentialKey, get_resolver

        from aqp.data.airbyte.builder.codegen_fetcher import _split_credential_ref

        service, account, field = _split_credential_ref(ref)
        bundle = get_resolver().resolve(CredentialKey(service, account))
        return bundle.get(field) or bundle.get("token") or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("inference credential resolve failed: %s", exc)
        return None


__all__ = ["infer_streams"]
