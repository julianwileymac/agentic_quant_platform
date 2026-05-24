"""Mapper from AQP :class:`LineageEvent` to OpenLineage ``RunEvent`` (Workstream B).

OpenLineage models three entities — **Job** (definition), **Run**
(instance), **Dataset** (input/output) — with metadata enriched via
facets. The mapper below translates AQP's flat
:class:`LineageEvent` shape into the equivalent OL JSON payload.

The mapping is intentionally conservative: we emit only the fields
OpenLineage requires plus a small set of well-defined facets. Custom
AQP-specific metadata (medallion layer, manifest id, run id, MCP tool
name) is carried in a ``customFacets`` block under the AQP namespace so
downstream consumers can interpret it without colliding with the
core OL spec.

OpenLineage HTTP transport spec:
https://openlineage.io/docs/spec/object-model/
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


_OL_NAMESPACE = "aqp"
_AQP_FACET_NS = "https://github.com/julianwileymac/agentic_quant_platform"


# ---------------------------------------------------------------------------
# Public mapper
# ---------------------------------------------------------------------------


def aqp_event_to_openlineage(
    event: Any,
    *,
    ol_namespace: str | None = None,
    event_type: str = "COMPLETE",
) -> dict[str, Any]:
    """Return an OpenLineage RunEvent dict for the given AQP event.

    ``event_type`` defaults to ``COMPLETE`` because the AQP lineage
    surface emits one event per finished motion. ``START`` / ``FAIL``
    can be passed explicitly when the caller (e.g. a future workflow
    runtime) reports both.

    The function NEVER raises — invalid inputs produce a minimal
    payload that still validates against the OL schema. This is by
    design: the relay queue must keep moving even when the source
    event is malformed.
    """
    ns = ol_namespace or _OL_NAMESPACE
    transform_kind = str(getattr(event, "transform_kind", "unknown") or "unknown")
    target_table_id = str(getattr(event, "target_table_id", "") or "")
    source_table_id = str(getattr(event, "source_table_id", "") or "")
    run_id_raw = getattr(event, "run_id", None)
    run_id = str(run_id_raw) if run_id_raw else str(uuid.uuid4())
    rows_written = getattr(event, "rows_written", None)
    medallion_layer = getattr(event, "medallion_layer", None)
    manifest_id = getattr(event, "manifest_id", None)
    mcp_tool_name = getattr(event, "mcp_tool_name", None)
    service_name = getattr(event, "service_name", None)
    actor = str(getattr(event, "actor", None) or "unknown")
    actor_kind = str(getattr(event, "actor_kind", None) or "service")
    details = dict(getattr(event, "details", {}) or {})
    summary = getattr(event, "summary", None)

    job_handle = target_table_id or source_table_id or transform_kind
    job_name = f"{transform_kind}:{job_handle}" if job_handle else transform_kind

    job: dict[str, Any] = {
        "namespace": ns,
        "name": job_name,
        "facets": {
            "documentation": {
                "_producer": _AQP_FACET_NS,
                "_schemaURL": "https://openlineage.io/spec/facets/1-0-1/DocumentationJobFacet.json",
                "description": summary or transform_kind,
            },
        },
    }

    run: dict[str, Any] = {
        "runId": run_id,
        "facets": {
            "aqp": {
                "_producer": _AQP_FACET_NS,
                "_schemaURL": f"{_AQP_FACET_NS}#aqp-run-facet",
                "transform_kind": transform_kind,
                "actor": actor,
                "actor_kind": actor_kind,
                "manifest_id": str(manifest_id) if manifest_id else None,
                "mcp_tool_name": str(mcp_tool_name) if mcp_tool_name else None,
                "service_name": str(service_name) if service_name else None,
                "rows_written": int(rows_written) if rows_written else None,
                "medallion_layer": medallion_layer,
                "iceberg_snapshot_id": details.get("iceberg_snapshot_id"),
                "iceberg_manifest_list": details.get("iceberg_manifest_list"),
            }
        },
    }

    inputs: list[dict[str, Any]] = []
    if source_table_id:
        inputs.append(_dataset_dict(ns, source_table_id, medallion_layer))

    outputs: list[dict[str, Any]] = []
    if target_table_id:
        outputs.append(_dataset_dict(ns, target_table_id, medallion_layer))

    return {
        "eventType": event_type,
        "eventTime": _now_iso(),
        "producer": _AQP_FACET_NS,
        "schemaURL": "https://openlineage.io/spec/2-0-2/OpenLineage.json",
        "job": job,
        "run": run,
        "inputs": inputs,
        "outputs": outputs,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dataset_dict(namespace: str, table_id: str, layer: str | None) -> dict[str, Any]:
    """Return the OL Dataset shape for one Iceberg / Parquet identifier.

    ``namespace`` is the OpenLineage namespace (not the Iceberg
    namespace) — we use the AQP-wide ``"aqp"`` namespace and pack the
    Iceberg ``ns.table`` identifier into the OL ``name`` field. This
    matches the convention Marquez uses for typed identifiers.
    """
    facets: dict[str, Any] = {}
    if layer:
        facets["aqp.medallion"] = {
            "_producer": _AQP_FACET_NS,
            "_schemaURL": f"{_AQP_FACET_NS}#aqp-medallion-facet",
            "layer": layer,
        }
    return {
        "namespace": namespace,
        "name": table_id,
        "facets": facets,
    }


__all__ = ["aqp_event_to_openlineage"]
