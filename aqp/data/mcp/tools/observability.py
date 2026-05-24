"""Observability DataMCP tools — Prometheus + Grafana.

Phase 2c of the AQP infra-expansion plan exposes the observability
plane to agents:

- ``data.observability.prometheus.query`` — instant PromQL.
- ``data.observability.prometheus.query_range`` — range PromQL.
- ``data.observability.prometheus.list_alerts`` — active alerts.
- ``data.observability.grafana.list_dashboards`` — dashboard catalog.
- ``data.observability.grafana.export_dashboard`` — dashboard JSON.

Endpoints resolve through ``settings.prometheus_url`` and
``settings.grafana_url`` (topology fallback in Phase 0). Read-only;
no mutation surfaces here. Mutation goes through ``aqp_control_plane``
``/manage/observability/*`` (Phase 3).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.config import settings
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


def _http_get(url: str, *, params: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any]:
    import httpx

    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


# ----------- Prometheus ------------------------------------------------------


class PromInstantQueryInput(BaseModel):
    query: str = Field(..., description="PromQL expression (instant).")
    time_unix: float | None = Field(
        default=None, description="Optional evaluation timestamp."
    )


@register_data_mcp_tool
class PrometheusInstantQueryTool(DataMCPTool):
    name = "data.observability.prometheus.query"
    description = "Run an instant PromQL query against the AQP-owned Prometheus."
    args_schema = PromInstantQueryInput
    category = "observability"
    tags = ("prometheus", "metrics")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        query: str,
        time_unix: float | None = None,
    ) -> MCPToolResult:
        url = settings.prometheus_url
        if not url:
            return MCPToolResult(ok=False, error="prometheus_url unset")
        params: dict[str, Any] = {"query": query}
        if time_unix is not None:
            params["time"] = float(time_unix)
        try:
            payload = _http_get(f"{url.rstrip('/')}/api/v1/query", params=params)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"prometheus query failed: {exc}")
        result = payload.get("data", {}).get("result", [])
        return MCPToolResult(
            ok=payload.get("status") == "success",
            data=result,
            rows_returned=len(result),
            summary=f"PromQL instant: {len(result)} series",
        )


class PromRangeQueryInput(BaseModel):
    query: str
    start_unix: float
    end_unix: float
    step_seconds: float = Field(default=15.0, gt=0.0)


@register_data_mcp_tool
class PrometheusRangeQueryTool(DataMCPTool):
    name = "data.observability.prometheus.query_range"
    description = "Run a range PromQL query (used by Grafana panels + agents)."
    args_schema = PromRangeQueryInput
    category = "observability"
    tags = ("prometheus", "metrics")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        query: str,
        start_unix: float,
        end_unix: float,
        step_seconds: float = 15.0,
    ) -> MCPToolResult:
        url = settings.prometheus_url
        if not url:
            return MCPToolResult(ok=False, error="prometheus_url unset")
        params = {
            "query": query,
            "start": float(start_unix),
            "end": float(end_unix),
            "step": f"{float(step_seconds)}s",
        }
        try:
            payload = _http_get(
                f"{url.rstrip('/')}/api/v1/query_range", params=params
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"prometheus query_range: {exc}")
        result = payload.get("data", {}).get("result", [])
        return MCPToolResult(
            ok=payload.get("status") == "success",
            data=result,
            rows_returned=len(result),
            summary=f"PromQL range: {len(result)} series, step={step_seconds}s",
        )


class PromAlertsInput(BaseModel):
    state: str | None = Field(
        default=None, description="Filter: 'firing' | 'pending' | 'inactive' | None."
    )


@register_data_mcp_tool
class PrometheusListAlertsTool(DataMCPTool):
    name = "data.observability.prometheus.list_alerts"
    description = "List currently registered alerts and their state."
    args_schema = PromAlertsInput
    category = "observability"
    tags = ("prometheus", "alerting")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        state: str | None = None,
    ) -> MCPToolResult:
        url = settings.prometheus_url
        if not url:
            return MCPToolResult(ok=False, error="prometheus_url unset")
        try:
            payload = _http_get(f"{url.rstrip('/')}/api/v1/alerts")
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"prometheus alerts: {exc}")
        alerts = payload.get("data", {}).get("alerts", [])
        if state:
            alerts = [a for a in alerts if a.get("state") == state]
        return MCPToolResult(
            ok=payload.get("status") == "success",
            data=alerts,
            rows_returned=len(alerts),
            summary=f"alerts: {len(alerts)} ({state or 'all'})",
        )


# ----------- Grafana --------------------------------------------------------


class GrafanaListDashboardsInput(BaseModel):
    query: str | None = None


@register_data_mcp_tool
class GrafanaListDashboardsTool(DataMCPTool):
    name = "data.observability.grafana.list_dashboards"
    description = "List Grafana dashboards (search). Read-only."
    args_schema = GrafanaListDashboardsInput
    category = "observability"
    tags = ("grafana", "dashboards")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        query: str | None = None,
    ) -> MCPToolResult:
        url = settings.grafana_url
        if not url:
            return MCPToolResult(ok=False, error="grafana_url unset")
        params: dict[str, Any] = {"type": "dash-db"}
        if query:
            params["query"] = query
        try:
            payload = _http_get(f"{url.rstrip('/')}/api/search", params=params)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"grafana search: {exc}")
        return MCPToolResult(
            ok=True,
            data=payload,
            rows_returned=len(payload) if isinstance(payload, list) else 0,
            summary=(
                f"grafana dashboards: {len(payload)}"
                if isinstance(payload, list)
                else "grafana dashboards"
            ),
        )


class GrafanaExportDashboardInput(BaseModel):
    dashboard_uid: str


@register_data_mcp_tool
class GrafanaExportDashboardTool(DataMCPTool):
    name = "data.observability.grafana.export_dashboard"
    description = "Export a Grafana dashboard JSON model by UID. Read-only."
    args_schema = GrafanaExportDashboardInput
    category = "observability"
    tags = ("grafana", "dashboards")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        dashboard_uid: str,
    ) -> MCPToolResult:
        url = settings.grafana_url
        if not url:
            return MCPToolResult(ok=False, error="grafana_url unset")
        try:
            payload = _http_get(
                f"{url.rstrip('/')}/api/dashboards/uid/{dashboard_uid}"
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"grafana export: {exc}")
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"exported grafana dashboard uid={dashboard_uid}",
        )


__all__ = [
    "GrafanaExportDashboardTool",
    "GrafanaListDashboardsTool",
    "PrometheusInstantQueryTool",
    "PrometheusListAlertsTool",
    "PrometheusRangeQueryTool",
]
