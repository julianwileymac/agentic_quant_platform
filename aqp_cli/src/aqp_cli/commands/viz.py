"""`aqp-cli viz` — visualization layer operations via `/visualizations/*`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import typer

from aqp_cli.commands._common import exit_for_http_error, monolith_client
from aqp_cli.ui.output import render_json

app = typer.Typer(no_args_is_help=True, help="Visualization layer operations.")


@app.command("config")
def config() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", "/visualizations/config"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("datasets")
def datasets() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", "/visualizations/datasets"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("sync")
def sync() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("POST", "/visualizations/superset/sync", json_body={}))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("export")
def export(
    dashboard_id: list[int] = typer.Option([], "--dashboard-id"),  # noqa: B008
    label: str = typer.Option("aqp", "--label"),
) -> None:
    payload: dict[str, Any] = {"dashboard_ids": dashboard_id, "label": label}
    client = monolith_client(require_token=True)
    try:
        render_json(
            client.request("POST", "/visualizations/superset/bundle/export", json_body=payload)
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("import")
def import_bundle(source: Path = typer.Argument(...)) -> None:  # noqa: B008
    if not source.exists():
        raise typer.BadParameter(f"{source} not found")
    client = monolith_client(require_token=True)
    try:
        with source.open("rb") as handle:
            files = {"file": (source.name, handle, "application/zip")}
            render_json(
                client.request("POST", "/visualizations/superset/bundle/import", files=files)
            )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("render")
def render(
    dataset: str = typer.Option(..., "--dataset"),
    kind: str = typer.Option("line", "--kind"),
    x: str = typer.Option("timestamp", "--x"),
    y: str = typer.Option("close", "--y"),
    groupby: str = typer.Option("vt_symbol", "--groupby"),
    limit: int = typer.Option(1000, "--limit"),
    title: str = typer.Option("", "--title"),
) -> None:
    payload: dict[str, Any] = {
        "kind": kind,
        "dataset_identifier": dataset,
        "x": x,
        "y": y,
        "groupby": groupby,
        "limit": limit,
    }
    if title:
        payload["title"] = title
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("POST", "/visualizations/bokeh/render", json_body=payload))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("cache-clear")
def cache_clear(
    older_than_hours: float = typer.Option(0.0, "--older-than-hours"),
) -> None:
    body = {}
    if older_than_hours > 0:
        body = {"older_than_seconds": int(older_than_hours * 3600)}
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("POST", "/visualizations/cache/clear", json_body=body))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("datahub")
def datahub_sync() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("POST", "/visualizations/datahub/sync", json_body={}))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
