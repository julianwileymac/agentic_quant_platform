"""Reusable loading templates for interactive data workflows."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


FieldKind = Literal[
    "string",
    "number",
    "boolean",
    "select",
    "json",
    "date",
    "date_range",
    "multi_string",
]


class LoadingTemplateField(BaseModel):
    """Editable field metadata rendered by the workflow UI."""

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    kind: FieldKind = "string"
    path: list[str | int] = Field(
        default_factory=list,
        description="Path in the template payload that this field updates.",
    )
    description: str | None = None
    default: Any = None
    required: bool = False
    options: list[str] = Field(default_factory=list)


class LoadingTemplate(BaseModel):
    """Serializable template shared by the API and visual editor."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    category: str
    provider: str | None = None
    endpoint: str
    run_kind: str
    tags: list[str] = Field(default_factory=list)
    default_payload: dict[str, Any] = Field(default_factory=dict)
    fields: list[LoadingTemplateField] = Field(default_factory=list)
    flow_graph: dict[str, Any] = Field(default_factory=dict)

    def merged_payload(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a deep-merged payload without mutating the template."""
        payload = deepcopy(self.default_payload)
        _deep_merge(payload, overrides or {})
        return payload


def list_loading_templates() -> list[LoadingTemplate]:
    """Return the curated templates used by the data loading UI."""
    return list(_TEMPLATES)


def get_loading_template(template_id: str) -> LoadingTemplate:
    """Look up a template by id."""
    for template in _TEMPLATES:
        if template.id == template_id:
            return template
    raise KeyError(template_id)


def build_template_payload(
    template_id: str,
    overrides: dict[str, Any] | None = None,
) -> tuple[LoadingTemplate, dict[str, Any]]:
    """Resolve a template and apply caller overrides."""
    template = get_loading_template(template_id)
    return template, template.merged_payload(overrides)


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
            continue
        target[key] = deepcopy(value)


_TEMPLATES: tuple[LoadingTemplate, ...] = (
    LoadingTemplate(
        id="alpha-vantage-intraday-2y-all-active",
        title="Alpha Vantage intraday, all active instruments, 2 years",
        description=(
            "Build a resumable month-by-month intraday manifest for every active "
            "instrument in the catalog, then load one batch into the Iceberg "
            "intraday table. Re-run the same template until the manifest is drained."
        ),
        category="market-data",
        provider="alpha_vantage",
        endpoint="/pipelines/alpha-vantage/intraday/delta",
        run_kind="alpha_vantage_intraday_delta",
        tags=["intraday", "iceberg", "resumable", "all_active"],
        default_payload={
            "plan": {
                "symbols": "all_active",
                "filters": {},
                "limit": None,
                "interval": "1min",
                "lookback_months": 24,
                "manifest_dir": None,
                "entitlement": None,
            },
            "load": {
                "batch_size": 25,
                "repair": False,
                "cache": True,
                "cache_ttl": None,
            },
        },
        fields=[
            LoadingTemplateField(
                name="symbols",
                label="Symbols",
                kind="string",
                path=["plan", "symbols"],
                default="all_active",
                required=True,
                description=(
                    "Use all_active for every active Instrument row, or provide "
                    "a vt_symbol list in JSON overrides."
                ),
            ),
            LoadingTemplateField(
                name="interval",
                label="Interval",
                kind="select",
                path=["plan", "interval"],
                default="1min",
                options=["1min", "5min", "15min", "30min", "60min"],
            ),
            LoadingTemplateField(
                name="lookback_months",
                label="Lookback months",
                kind="number",
                path=["plan", "lookback_months"],
                default=24,
                description="24 months is the two-year backfill requested here.",
            ),
            LoadingTemplateField(
                name="limit",
                label="Symbol limit",
                kind="number",
                path=["plan", "limit"],
                default=None,
                description="Optional cap when symbols is all_active.",
            ),
            LoadingTemplateField(
                name="batch_size",
                label="Batch size",
                kind="number",
                path=["load", "batch_size"],
                default=25,
                description="Number of manifest components processed by each queued load task.",
            ),
            LoadingTemplateField(
                name="repair",
                label="Repair mode",
                kind="boolean",
                path=["load", "repair"],
                default=False,
                description="Retry missing or failed manifest components.",
            ),
            LoadingTemplateField(
                name="cache",
                label="Use cache",
                kind="boolean",
                path=["load", "cache"],
                default=True,
            ),
            LoadingTemplateField(
                name="cache_ttl",
                label="Cache TTL",
                kind="number",
                path=["load", "cache_ttl"],
                default=None,
                description="Optional cache TTL in seconds.",
            ),
            LoadingTemplateField(
                name="entitlement",
                label="Entitlement",
                kind="string",
                path=["plan", "entitlement"],
                default=None,
                description="Optional Alpha Vantage entitlement tier.",
            ),
            LoadingTemplateField(
                name="filters",
                label="Universe filters",
                kind="json",
                path=["plan", "filters"],
                default={},
                description="Optional Instrument filters, e.g. exchange/security_type.",
            ),
        ],
        flow_graph={
            "domain": "data",
            "version": 1,
            "nodes": [
                {
                    "id": "template-av-intraday",
                    "type": "aqp",
                    "position": {"x": 80, "y": 80},
                    "data": {
                        "kind": "Template",
                        "label": "2y all-active intraday",
                        "params": {
                            "template_id": "alpha-vantage-intraday-2y-all-active",
                            "overrides": {},
                        },
                        "notes": "Plan all active instruments for the last 24 months, then load a resumable batch.",
                    },
                },
                {
                    "id": "plan-intraday",
                    "type": "aqp",
                    "position": {"x": 360, "y": 80},
                    "data": {
                        "kind": "Plan",
                        "label": "Build monthly manifest",
                        "params": {"lookback_months": 24, "interval": "1min"},
                    },
                },
                {
                    "id": "load-intraday",
                    "type": "aqp",
                    "position": {"x": 640, "y": 80},
                    "data": {
                        "kind": "Load",
                        "label": "Load component batch",
                        "params": {"batch_size": 25},
                    },
                },
                {
                    "id": "sink-iceberg",
                    "type": "aqp",
                    "position": {"x": 920, "y": 80},
                    "data": {
                        "kind": "Iceberg",
                        "label": "aqp_alpha_vantage.time_series_intraday",
                        "params": {
                            "namespace": "aqp_alpha_vantage",
                            "table": "time_series_intraday",
                        },
                    },
                },
            ],
            "edges": [
                {
                    "id": "e-template-plan",
                    "source": "template-av-intraday",
                    "target": "plan-intraday",
                },
                {
                    "id": "e-plan-load",
                    "source": "plan-intraday",
                    "target": "load-intraday",
                },
                {
                    "id": "e-load-sink",
                    "source": "load-intraday",
                    "target": "sink-iceberg",
                },
            ],
        },
    ),
    LoadingTemplate(
        id="local-path-director-iceberg",
        title="Local files through Director to Iceberg",
        description=(
            "Discover a folder or archive, preview the Director plan, and "
            "materialize datasets into Iceberg."
        ),
        category="file-ingest",
        provider="local",
        endpoint="/pipelines/ingest",
        run_kind="ingest_local_path",
        tags=["local", "director", "iceberg"],
        default_payload={
            "path": "",
            "namespace": "aqp",
            "table_prefix": None,
            "annotate": True,
            "max_rows_per_dataset": None,
            "max_files_per_dataset": None,
        },
        fields=[
            LoadingTemplateField(name="path", label="Path", path=["path"], required=True),
            LoadingTemplateField(
                name="namespace",
                label="Namespace",
                path=["namespace"],
                default="aqp",
            ),
            LoadingTemplateField(
                name="annotate",
                label="Annotate",
                kind="boolean",
                path=["annotate"],
                default=True,
            ),
        ],
        flow_graph={
            "domain": "data",
            "version": 1,
            "nodes": [
                {
                    "id": "template-local",
                    "type": "aqp",
                    "position": {"x": 80, "y": 80},
                    "data": {
                        "kind": "Template",
                        "label": "Local files",
                        "params": {
                            "template_id": "local-path-director-iceberg",
                            "overrides": {},
                        },
                    },
                },
                {
                    "id": "discover-local",
                    "type": "aqp",
                    "position": {"x": 360, "y": 80},
                    "data": {"kind": "Plan", "label": "Discover + Director", "params": {}},
                },
                {
                    "id": "sink-local",
                    "type": "aqp",
                    "position": {"x": 640, "y": 80},
                    "data": {
                        "kind": "Iceberg",
                        "label": "Iceberg tables",
                        "params": {"namespace": "aqp"},
                    },
                },
            ],
            "edges": [
                {
                    "id": "e-local-plan",
                    "source": "template-local",
                    "target": "discover-local",
                },
                {
                    "id": "e-local-sink",
                    "source": "discover-local",
                    "target": "sink-local",
                },
            ],
        },
    ),
    LoadingTemplate(
        id="alpha-vantage-endpoint-bulk",
        title="Alpha Vantage endpoint bulk load",
        description=(
            "Load selected Alpha Vantage endpoint families for a symbol list "
            "or active universe into Iceberg."
        ),
        category="market-data",
        provider="alpha_vantage",
        endpoint="/pipelines/alpha-vantage/endpoints",
        run_kind="alpha_vantage_endpoints",
        tags=["alpha_vantage", "fundamentals", "iceberg"],
        default_payload={
            "endpoints": ["OVERVIEW", "EARNINGS"],
            "symbols": "all_active",
            "filters": {},
            "limit": None,
            "cache": True,
            "cache_ttl": None,
        },
        fields=[
            LoadingTemplateField(
                name="endpoints",
                label="Endpoints",
                kind="json",
                path=["endpoints"],
                default=["OVERVIEW", "EARNINGS"],
                required=True,
            ),
            LoadingTemplateField(
                name="symbols",
                label="Symbols",
                path=["symbols"],
                default="all_active",
                required=True,
            ),
            LoadingTemplateField(
                name="limit",
                label="Limit",
                kind="number",
                path=["limit"],
                default=None,
            ),
        ],
        flow_graph={
            "domain": "data",
            "version": 1,
            "nodes": [
                {
                    "id": "template-av-endpoints",
                    "type": "aqp",
                    "position": {"x": 80, "y": 80},
                    "data": {
                        "kind": "Template",
                        "label": "AV endpoint load",
                        "params": {"template_id": "alpha-vantage-endpoint-bulk", "overrides": {}},
                    },
                },
                {
                    "id": "sink-av-endpoints",
                    "type": "aqp",
                    "position": {"x": 360, "y": 80},
                    "data": {
                        "kind": "Iceberg",
                        "label": "Endpoint tables",
                        "params": {"namespace": "aqp_alpha_vantage"},
                    },
                },
            ],
            "edges": [
                {
                    "id": "e-av-endpoints",
                    "source": "template-av-endpoints",
                    "target": "sink-av-endpoints",
                }
            ],
        },
    ),
)


__all__ = [
    "LoadingTemplate",
    "LoadingTemplateField",
    "build_template_payload",
    "get_loading_template",
    "list_loading_templates",
]
