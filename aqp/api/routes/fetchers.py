"""Fetcher catalog + probe endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
# Eager import side-effect: registering every bundled fetcher / transform /
# sink with the engine + upserting its row in ``data_sources``. Imported here
# rather than in ``aqp.api.main`` so the registration pass happens once
# regardless of which route boots the API.
import aqp.data.fetchers  # noqa: F401  (registration side effect)
from aqp.data.engine import list_nodes, list_nodes_by_kind
from aqp.data.engine.manifest import FetchSliceSpec
from aqp.data.engine.nodes import NodeKind
from aqp.data.engine.registry import build_node, get_node_class

router = secure_router(prefix="/fetchers", tags=["fetchers"], default_scope="data:read")


class NodeSummary(BaseModel):
    name: str
    kind: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    module: str | None = None
    class_name: str | None = None


class ProbeRequest(BaseModel):
    name: str
    kwargs: dict[str, Any] = Field(default_factory=dict)


COMMON_FETCH_UI_FIELDS = [
    {
        "name": "symbol_mode",
        "label": "Symbol mode",
        "kind": "select",
        "path": ["slice", "symbol_mode"],
        "default": "explicit",
        "options": ["explicit", "all_active", "query", "universe"],
        "description": "How the source resolves the symbol universe.",
    },
    {
        "name": "symbols",
        "label": "Symbols",
        "kind": "multi_string",
        "path": ["slice", "symbols"],
        "default": [],
        "description": "Explicit tickers or vt_symbols to fetch.",
    },
    {
        "name": "query",
        "label": "Universe query",
        "kind": "string",
        "path": ["slice", "query"],
        "default": "",
        "description": "Provider/catalog query used when symbol mode is query.",
    },
    {
        "name": "date_range",
        "label": "Date range",
        "kind": "date_range",
        "path": ["slice", "date_range"],
        "default": None,
        "description": "Inclusive start/end range for historical data.",
    },
    {
        "name": "interval",
        "label": "Interval",
        "kind": "select",
        "path": ["slice", "interval"],
        "default": "1d",
        "options": ["1min", "5min", "15min", "30min", "60min", "1d", "1wk", "1mo"],
    },
    {
        "name": "limit",
        "label": "Limit",
        "kind": "number",
        "path": ["slice", "limit"],
        "default": None,
        "description": "Maximum rows/symbols/components to fetch.",
    },
    {
        "name": "offset",
        "label": "Offset",
        "kind": "number",
        "path": ["slice", "offset"],
        "default": 0,
        "description": "Zero-based offset for paged providers.",
    },
    {
        "name": "provider_options",
        "label": "Provider options",
        "kind": "json",
        "path": ["slice", "provider_options"],
        "default": {},
        "description": "Provider-specific knobs not covered by common fields.",
    },
]


@router.get("", response_model=list[NodeSummary])
def list_all_nodes() -> list[dict[str, Any]]:
    return list_nodes()


@router.get("/sources", response_model=list[NodeSummary])
def list_source_nodes() -> list[dict[str, Any]]:
    return list_nodes_by_kind(NodeKind.SOURCE)


@router.get("/transforms", response_model=list[NodeSummary])
def list_transform_nodes() -> list[dict[str, Any]]:
    return list_nodes_by_kind(NodeKind.TRANSFORM)


@router.get("/sinks", response_model=list[NodeSummary])
def list_sink_nodes() -> list[dict[str, Any]]:
    return list_nodes_by_kind(NodeKind.SINK)


@router.get("/{node_name}/schema")
def get_node_schema(node_name: str) -> dict[str, Any]:
    """Return a synthesized JSON schema fragment for a node's kwargs."""
    try:
        cls = get_node_class(node_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    import inspect

    sig = inspect.signature(cls.__init__)
    fields: list[dict[str, Any]] = []
    for name, param in sig.parameters.items():
        if name in {"self", "args", "kwargs"} or name.startswith("**"):
            continue
        annotation = (
            str(param.annotation)
            if param.annotation is not inspect.Parameter.empty
            else "Any"
        )
        fields.append(
            {
                "name": name,
                "annotation": annotation,
                "required": param.default is inspect.Parameter.empty,
                "default": (
                    None if param.default is inspect.Parameter.empty else param.default
                ),
            }
        )
    return {
        "name": node_name,
        "class_name": cls.__name__,
        "module": cls.__module__,
        "doc": (cls.__doc__ or "").strip(),
        "fields": fields,
    }


@router.get("/{node_name}/ui-schema")
def get_node_ui_schema(node_name: str) -> dict[str, Any]:
    """Return typed UI controls for common fetch slicing plus node kwargs."""

    schema = get_node_schema(node_name)
    constructor_fields = []
    for field in schema["fields"]:
        constructor_fields.append(
            {
                "name": f"kwargs.{field['name']}",
                "label": field["name"].replace("_", " ").title(),
                "kind": _ui_kind_for_annotation(str(field.get("annotation") or "")),
                "path": ["kwargs", field["name"]],
                "required": bool(field.get("required")),
                "default": field.get("default"),
                "description": f"Constructor kwarg for {node_name}.",
            }
        )
    return {
        "name": node_name,
        "class_name": schema["class_name"],
        "module": schema["module"],
        "doc": schema["doc"],
        "slice_model": FetchSliceSpec.model_json_schema(),
        "fields": [*COMMON_FETCH_UI_FIELDS, *constructor_fields],
    }


def _ui_kind_for_annotation(annotation: str) -> str:
    normalized = annotation.lower()
    if "bool" in normalized:
        return "boolean"
    if "int" in normalized or "float" in normalized:
        return "number"
    if "dict" in normalized or "list" in normalized:
        return "json"
    return "string"


@router.post("/probe")
def probe_fetcher(payload: ProbeRequest) -> dict[str, Any]:
    """Instantiate a source-node and run its ``probe`` method."""
    try:
        node = build_node(payload.name, payload.kwargs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not hasattr(node, "probe"):
        return {"name": payload.name, "ok": True, "note": "no probe() method"}
    try:
        result = node.probe()
    except Exception as exc:  # noqa: BLE001
        return {"name": payload.name, "ok": False, "error": str(exc)}
    return {"name": payload.name, "ok": True, "result": result}
