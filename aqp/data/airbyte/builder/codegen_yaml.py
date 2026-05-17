"""Render builder state into a Low-Code CDK YAML manifest.

Round-trippable: ``state_to_yaml(state)`` plus the matching parser
(future work — Phase 2 only ships the writer; the frontend keeps the
state dict authoritative). Keeps the manifest deterministic so two
edits with identical content produce byte-identical YAML.
"""
from __future__ import annotations

from typing import Any

from aqp.data.airbyte.builder.validate import validate_manifest


def state_to_yaml(state: dict[str, Any]) -> str:
    """Emit a Low-Code CDK YAML manifest from builder state.

    Raises :class:`ValueError` if validation fails so the caller
    surfaces the structured error list to the UI.
    """
    report = validate_manifest(state)
    if report["errors"]:
        raise ValueError(f"manifest validation failed: {report['errors']}")
    metadata = state.get("metadata") or {}
    auth = state.get("auth") or {}
    requester = state.get("requester") or {}
    paginator = state.get("paginator") or {}
    extractor = state.get("extractor") or {}
    streams = state.get("streams") or []

    connector_id = str(metadata.get("connector_id") or "").strip().lower()
    base_url = str(requester.get("base_url") or "").strip()
    method = str(requester.get("method") or "GET").upper()
    auth_kind = str(auth.get("auth_kind") or "none").lower()
    paginator_kind = str(paginator.get("paginator_kind") or "none").lower()

    lines: list[str] = []
    lines.append("version: \"0.50.0\"")
    lines.append(f"type: DeclarativeSource")
    lines.append("")
    lines.append("definitions:")
    lines.append("  selector:")
    lines.append("    extractor:")
    lines.append("      type: DpathExtractor")
    record_path = str(extractor.get("record_path") or "$").strip()
    lines.append(f"      field_path: {_dpath(record_path)}")
    lines.append("  requester:")
    lines.append("    type: HttpRequester")
    lines.append(f"    url_base: \"{_yaml_string(base_url)}\"")
    lines.append(f"    http_method: \"{method}\"")
    if auth_kind != "none":
        lines.extend(_render_auth(auth_kind, auth))
    headers = requester.get("default_headers") or {}
    if isinstance(headers, dict) and headers:
        lines.append("    request_headers:")
        for key, value in headers.items():
            lines.append(f"      {_yaml_string(str(key))}: \"{_yaml_string(str(value))}\"")
    params = requester.get("default_params") or {}
    if isinstance(params, dict) and params:
        lines.append("    request_parameters:")
        for key, value in params.items():
            lines.append(f"      {_yaml_string(str(key))}: \"{_yaml_string(str(value))}\"")
    lines.append("  retriever:")
    lines.append("    type: SimpleRetriever")
    lines.append("    record_selector:")
    lines.append("      $ref: \"#/definitions/selector\"")
    lines.append("    requester:")
    lines.append("      $ref: \"#/definitions/requester\"")
    if paginator_kind != "none":
        lines.extend(_render_paginator(paginator_kind, paginator))

    lines.append("")
    lines.append("streams:")
    for stream in streams:
        name = str(stream.get("name") or "").strip()
        path = str(stream.get("path") or "").strip()
        lines.append(f"  - type: DeclarativeStream")
        lines.append(f"    name: \"{_yaml_string(name)}\"")
        lines.append("    retriever:")
        lines.append("      $ref: \"#/definitions/retriever\"")
        lines.append("      requester:")
        lines.append("        $ref: \"#/definitions/requester\"")
        lines.append(f"        path: \"{_yaml_string(path)}\"")
        primary_key = str(stream.get("primary_key") or "").strip()
        if primary_key:
            keys = [k.strip() for k in primary_key.split(",") if k.strip()]
            lines.append(f"    primary_key: {keys}")
        cursor = str(stream.get("cursor_field") or "").strip()
        if cursor:
            lines.append(f"    incremental_sync:")
            lines.append(f"      type: DatetimeBasedCursor")
            lines.append(f"      cursor_field: \"{_yaml_string(cursor)}\"")

    lines.append("")
    lines.append("check:")
    lines.append("  type: CheckStream")
    if streams:
        first = str(streams[0].get("name") or "")
        lines.append(f"  stream_names: [\"{_yaml_string(first)}\"]")
    lines.append("")
    lines.append(f"# Connector id: {connector_id}")
    return "\n".join(lines) + "\n"


def _render_auth(kind: str, auth: dict[str, Any]) -> list[str]:
    cred_ref = str(auth.get("credential_ref") or "").strip()
    out: list[str] = ["    authenticator:"]
    if kind == "bearer":
        out.append("      type: BearerAuthenticator")
        out.append(f"      api_token: \"{{{{ config['{cred_ref}'] }}}}\"")
    elif kind == "header":
        header = str(auth.get("auth_header_name") or "Authorization")
        out.append("      type: ApiKeyAuthenticator")
        out.append("      inject_into:")
        out.append("        type: RequestOption")
        out.append("        inject_into: header")
        out.append(f"        field_name: \"{_yaml_string(header)}\"")
        out.append(f"      api_token: \"{{{{ config['{cred_ref}'] }}}}\"")
    elif kind == "query":
        field = str(auth.get("auth_query_field") or "api_key")
        out.append("      type: ApiKeyAuthenticator")
        out.append("      inject_into:")
        out.append("        type: RequestOption")
        out.append("        inject_into: request_parameter")
        out.append(f"        field_name: \"{_yaml_string(field)}\"")
        out.append(f"      api_token: \"{{{{ config['{cred_ref}'] }}}}\"")
    elif kind == "basic":
        out.append("      type: BasicHttpAuthenticator")
        out.append(f"      username: \"{{{{ config['{cred_ref}_username'] }}}}\"")
        out.append(f"      password: \"{{{{ config['{cred_ref}_password'] }}}}\"")
    return out


def _render_paginator(kind: str, pag: dict[str, Any]) -> list[str]:
    page_size = int(pag.get("page_size") or 100)
    page_param = str(pag.get("page_param") or "page")
    out: list[str] = ["    paginator:"]
    out.append("      type: DefaultPaginator")
    out.append("      page_token_option:")
    out.append("        type: RequestOption")
    out.append("        inject_into: request_parameter")
    out.append(f"        field_name: \"{_yaml_string(page_param)}\"")
    if kind == "page_increment":
        out.append("      pagination_strategy:")
        out.append("        type: PageIncrement")
        out.append(f"        page_size: {page_size}")
    elif kind == "offset_increment":
        out.append("      pagination_strategy:")
        out.append("        type: OffsetIncrement")
        out.append(f"        page_size: {page_size}")
    elif kind == "cursor_field":
        cursor = str(pag.get("cursor_field") or "")
        out.append("      pagination_strategy:")
        out.append("        type: CursorPagination")
        out.append(f"        cursor_value: \"{{{{ response.{cursor} }}}}\"")
    elif kind == "next_link_url":
        out.append("      pagination_strategy:")
        out.append("        type: CursorPagination")
        out.append("        cursor_value: \"{{ response.next_url }}\"")
    return out


def _dpath(record_path: str) -> list[str]:
    if record_path in ("$", "", None):
        return []
    return [seg for seg in record_path.split(".") if seg]


def _yaml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


__all__ = ["state_to_yaml"]
