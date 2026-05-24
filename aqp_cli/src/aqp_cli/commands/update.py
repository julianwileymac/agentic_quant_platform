"""`aqp-cli update` — check stack health + version surfaces."""

from __future__ import annotations

import httpx
import typer

from aqp_cli.commands._common import control_plane_client, exit_for_http_error
from aqp_cli.ui.output import render_json

app = typer.Typer(no_args_is_help=True, help="Check + apply updates to the AQP stack.")


@app.command("check")
def check() -> None:
    """Compare local image / git versions against the control plane's latest."""
    client = control_plane_client(require_token=True)
    try:
        topology = client.request("GET", "/manage/topology")
        health = client.request("GET", "/manage/health")
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json({"topology": topology, "health": health})


@app.command("apply")
def apply(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without applying."
    ),
) -> None:
    """Apply available updates (pull images, run migrations, restart in order)."""
    if dry_run:
        render_json(
            {"status": "dry-run", "message": "No mutating update endpoint is configured yet."}
        )
        return
    typer.echo("No `/manage/updates` endpoint is available yet. Use deploy/cp commands explicitly.")
    raise typer.Exit(code=1)
