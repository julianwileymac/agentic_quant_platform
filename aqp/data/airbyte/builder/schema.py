"""Opinionated subset of the Airbyte Low-Code CDK schema.

We deliberately ship a *condensed* schema rather than vendoring the
full CDK json — the visual builder needs the 80% case (auth,
requester, paginator, record selector, streams), and the long tail
(custom transformations, complex nested authenticators) is handled
by escaping into the AQP Fetcher stub. The latter never executes
inside Airbyte's worker container, so unsafe-code mode stays off.

`BuilderField` / `BuilderSection` are intentionally simple — they map
1:1 to the JSON the frontend `ConnectorBuilderForm` consumes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FieldKind = Literal[
    "string",
    "url",
    "secret",
    "number",
    "boolean",
    "select",
    "json",
    "credential_ref",
]


@dataclass(slots=True)
class BuilderField:
    """One leaf input in the visual builder."""

    name: str
    label: str
    kind: FieldKind = "string"
    description: str = ""
    required: bool = False
    default: Any = None
    options: list[str] = field(default_factory=list)
    placeholder: str = ""

    def to_json(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", [])}


@dataclass(slots=True)
class BuilderSection:
    """A grouped collection of fields rendered together."""

    key: str
    title: str
    description: str = ""
    fields: list[BuilderField] = field(default_factory=list)
    repeatable: bool = False  # streams use repeatable=True

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "fields": [f.to_json() for f in self.fields],
            "repeatable": self.repeatable,
        }


# ----------------------------------------------------------------- canonical schema

BUILDER_SCHEMA: list[BuilderSection] = [
    BuilderSection(
        key="metadata",
        title="Connector metadata",
        fields=[
            BuilderField(
                name="connector_id",
                label="Connector id",
                kind="string",
                required=True,
                description="Lower-case slug. Used as `airbyte_connectors.connector_id`.",
            ),
            BuilderField(
                name="display_name",
                label="Display name",
                kind="string",
                required=True,
            ),
            BuilderField(
                name="docs_url",
                label="Docs URL",
                kind="url",
            ),
        ],
    ),
    BuilderSection(
        key="auth",
        title="Authentication",
        description=(
            "Pick a credential reference (managed by aqp.credentials) instead of pasting "
            "raw secrets. The builder stores the reference; the runtime resolves it."
        ),
        fields=[
            BuilderField(
                name="auth_kind",
                label="Auth kind",
                kind="select",
                options=["none", "bearer", "header", "query", "basic"],
                default="none",
            ),
            BuilderField(
                name="credential_ref",
                label="Credential reference",
                kind="credential_ref",
                description="Picked through EntityPicker kind=credentials.",
            ),
            BuilderField(
                name="auth_header_name",
                label="Auth header name (header auth)",
                kind="string",
                placeholder="Authorization",
            ),
            BuilderField(
                name="auth_query_field",
                label="Auth query field (query auth)",
                kind="string",
                placeholder="api_key",
            ),
        ],
    ),
    BuilderSection(
        key="requester",
        title="HTTP request",
        fields=[
            BuilderField(
                name="base_url",
                label="Base URL",
                kind="url",
                required=True,
            ),
            BuilderField(
                name="method",
                label="HTTP method",
                kind="select",
                options=["GET", "POST", "PUT"],
                default="GET",
            ),
            BuilderField(
                name="default_headers",
                label="Default headers (JSON object)",
                kind="json",
                default={},
            ),
            BuilderField(
                name="default_params",
                label="Default query params (JSON object)",
                kind="json",
                default={},
            ),
            BuilderField(
                name="timeout_s",
                label="Timeout (seconds)",
                kind="number",
                default=30,
            ),
        ],
    ),
    BuilderSection(
        key="paginator",
        title="Pagination",
        fields=[
            BuilderField(
                name="paginator_kind",
                label="Strategy",
                kind="select",
                options=[
                    "none",
                    "page_increment",
                    "offset_increment",
                    "cursor_field",
                    "next_link_url",
                ],
                default="none",
            ),
            BuilderField(
                name="page_size",
                label="Page size",
                kind="number",
                default=100,
            ),
            BuilderField(
                name="page_param",
                label="Page param name",
                kind="string",
                default="page",
            ),
            BuilderField(
                name="cursor_field",
                label="Cursor field (response path, dot-notation)",
                kind="string",
            ),
        ],
    ),
    BuilderSection(
        key="extractor",
        title="Record extractor",
        fields=[
            BuilderField(
                name="record_path",
                label="Record path (dot-notation, '$' = root)",
                kind="string",
                default="$",
            ),
        ],
    ),
    BuilderSection(
        key="streams",
        title="Streams",
        repeatable=True,
        fields=[
            BuilderField(
                name="name",
                label="Stream name",
                kind="string",
                required=True,
            ),
            BuilderField(
                name="path",
                label="Path (relative to base URL)",
                kind="string",
                required=True,
            ),
            BuilderField(
                name="primary_key",
                label="Primary key (comma-separated)",
                kind="string",
            ),
            BuilderField(
                name="cursor_field",
                label="Cursor field (incremental sync)",
                kind="string",
            ),
        ],
    ),
]


def schema_to_json() -> list[dict[str, Any]]:
    """Return the full builder schema as JSON for the frontend."""
    return [section.to_json() for section in BUILDER_SCHEMA]


__all__ = [
    "BUILDER_SCHEMA",
    "BuilderField",
    "BuilderSection",
    "schema_to_json",
]
