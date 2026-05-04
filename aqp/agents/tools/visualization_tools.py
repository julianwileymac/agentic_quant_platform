"""Visualization tools surfaced to AQP's spec-driven agents.

The two tools wrap the existing Bokeh renderer and Superset client so an
:class:`aqp.agents.runtime.AgentRuntime` agent can produce a chart spec or
mint a guest-token embed URL without ever calling
``router_complete``/``OllamaClient`` itself (per AGENTS rule #2). All
heavy lifting still flows through the canonical singletons:

* :func:`aqp.visualization.bokeh_renderer.render_bokeh_item` for charts;
* :class:`aqp.services.superset_client.SupersetClient` for dashboards.
"""
from __future__ import annotations

import json
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BokehChartInput(BaseModel):
    """Args accepted by :class:`BokehChartTool`."""

    dataset_identifier: str = Field(
        ..., description="Iceberg identifier shaped 'namespace.table' (e.g. aqp_equity.sp500_daily)."
    )
    kind: str = Field(default="line", description="One of: line, scatter, histogram, candlestick, table.")
    x: str = Field(default="timestamp", description="X-axis column name.")
    y: str = Field(default="close", description="Y-axis column name (ignored for table).")
    groupby: str | None = Field(default="vt_symbol", description="Optional groupby column.")
    limit: int = Field(default=1000, ge=1, le=50_000, description="Row cap on the underlying scan.")
    title: str | None = Field(default=None, description="Optional chart title override.")


class BokehChartTool(BaseTool):
    name: str = "bokeh_chart"
    description: str = (
        "Render an Iceberg dataset as a Bokeh json_item chart. Returns a JSON "
        "string holding the embeddable spec plus a cache_key. Kinds: line, "
        "scatter, histogram, candlestick, table."
    )
    args_schema: type[BaseModel] = BokehChartInput

    def _run(  # type: ignore[override]
        self,
        dataset_identifier: str,
        kind: str = "line",
        x: str = "timestamp",
        y: str = "close",
        groupby: str | None = "vt_symbol",
        limit: int = 1000,
        title: str | None = None,
    ) -> str:
        from aqp.visualization.bokeh_renderer import BokehChartSpec, render_bokeh_item

        try:
            spec = BokehChartSpec(
                kind=kind,  # type: ignore[arg-type]
                dataset_identifier=dataset_identifier,
                x=x,
                y=y,
                groupby=groupby,
                limit=limit,
                title=title,
            )
            item = render_bokeh_item(spec)
        except Exception as exc:  # noqa: BLE001
            logger.exception("BokehChartTool render failed")
            return json.dumps({"error": str(exc)})
        # Drop the doc body so we keep the response token-budget friendly;
        # the cache_key + spec is enough for any downstream agent step that
        # wants to re-fetch the rendered item.
        compact = {
            "cache_key": item.get("cache_key"),
            "doc_id": item.get("doc"),
            "target_id": item.get("target_id"),
            "version": item.get("version"),
            "kind": kind,
            "dataset_identifier": dataset_identifier,
        }
        return json.dumps(compact, default=str)


class SupersetDashboardInput(BaseModel):
    """Args accepted by :class:`SupersetDashboardTool`."""

    action: str = Field(
        default="list",
        description="One of: list (return dashboards/datasets) | embed (mint a guest token).",
    )
    dashboard_uuid: str | None = Field(
        default=None,
        description="Required when action='embed'; falls back to AQP_SUPERSET_DEFAULT_DASHBOARD_UUID.",
    )


class SupersetDashboardTool(BaseTool):
    name: str = "superset_dashboard"
    description: str = (
        "List Superset dashboards/datasets, or mint a short-lived guest token + "
        "embed URL for a given dashboard UUID. Returns a JSON string."
    )
    args_schema: type[BaseModel] = SupersetDashboardInput

    def _run(  # type: ignore[override]
        self,
        action: str = "list",
        dashboard_uuid: str | None = None,
    ) -> str:
        from aqp.config import settings
        from aqp.services.superset_client import SupersetClient

        try:
            with SupersetClient() as client:
                if action == "list":
                    return json.dumps(
                        {
                            "dashboards": [
                                {"id": d.get("id"), "title": d.get("dashboard_title"), "slug": d.get("slug")}
                                for d in client.list_dashboards()
                            ],
                            "datasets": [
                                {
                                    "id": d.get("id"),
                                    "table_name": d.get("table_name"),
                                    "schema": d.get("schema"),
                                }
                                for d in client.list_datasets()
                            ],
                        },
                        default=str,
                    )

                if action == "embed":
                    uuid = (dashboard_uuid or settings.superset_default_dashboard_uuid).strip()
                    if not uuid:
                        return json.dumps(
                            {
                                "error": (
                                    "no dashboard_uuid; set AQP_SUPERSET_DEFAULT_DASHBOARD_UUID "
                                    "or pass dashboard_uuid"
                                )
                            }
                        )
                    token = client.create_guest_token(
                        resources=[{"type": "dashboard", "id": uuid}]
                    )
                    return json.dumps(
                        {
                            "dashboard_uuid": uuid,
                            "token": token,
                            "embed_url": f"{settings.superset_public_url or settings.superset_base_url}"
                            f"/superset/dashboard/{uuid}/?standalone=3",
                        },
                        default=str,
                    )

                return json.dumps({"error": f"unknown action: {action!r} (expected list|embed)"})

        except Exception as exc:  # noqa: BLE001
            logger.exception("SupersetDashboardTool failed")
            return json.dumps({"error": str(exc)})


__all__ = [
    "BokehChartInput",
    "BokehChartTool",
    "SupersetDashboardInput",
    "SupersetDashboardTool",
]
