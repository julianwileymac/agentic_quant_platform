"""Dagster assets that orchestrate AQP Alpha Vantage intraday loads via API."""

from __future__ import annotations

import os
from typing import Any

import requests
from dagster import Field, MetadataValue, asset


_AQP_API_CONFIG = {
    "aqp_api_url": Field(str, default_value=os.getenv("PIPELINE_AQP_API_URL", "http://api.aqp.svc.cluster.local:8000")),
    "timeout_seconds": Field(int, default_value=30),
}


def _post(context, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    base = str(context.op_config["aqp_api_url"]).rstrip("/")
    headers = {"Content-Type": "application/json"}
    token = os.getenv("PIPELINE_AQP_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.post(
        f"{base}{path}",
        json=payload,
        headers=headers,
        timeout=int(context.op_config["timeout_seconds"]),
    )
    response.raise_for_status()
    data = response.json()
    context.add_output_metadata(
        {
            "endpoint": MetadataValue.url(f"{base}{path}"),
            "task_id": MetadataValue.text(str(data.get("task_id", ""))),
            "stream_url": MetadataValue.text(str(data.get("stream_url", ""))),
        }
    )
    return data


@asset(
    config_schema={
        **_AQP_API_CONFIG,
        "limit": Field(int, default_value=0),
        "lookback_months": Field(int, default_value=36),
    },
    description="Queue AQP generation of 1-minute Alpha Vantage intraday request components.",
)
def aqp_alphavantage_intraday_plan(context):
    payload: dict[str, Any] = {
        "symbols": "all_active",
        "interval": "1min",
        "lookback_months": int(context.op_config["lookback_months"]),
    }
    if int(context.op_config["limit"]) > 0:
        payload["limit"] = int(context.op_config["limit"])
    return _post(context, "/pipelines/alpha-vantage/intraday/plan", payload)


@asset(
    config_schema={
        **_AQP_API_CONFIG,
        "batch_size": Field(int, default_value=25),
        "limit": Field(int, default_value=0),
        "lookback_months": Field(int, default_value=36),
    },
    description="Queue an AQP Alpha Vantage intraday delta cycle.",
)
def aqp_alphavantage_intraday_delta(context):
    plan: dict[str, Any] = {
        "symbols": "all_active",
        "interval": "1min",
        "lookback_months": int(context.op_config["lookback_months"]),
    }
    if int(context.op_config["limit"]) > 0:
        plan["limit"] = int(context.op_config["limit"])
    payload = {
        "plan": plan,
        "load": {"batch_size": int(context.op_config["batch_size"])},
    }
    return _post(context, "/pipelines/alpha-vantage/intraday/delta", payload)

