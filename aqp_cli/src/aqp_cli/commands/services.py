"""`aqp-cli services` — inspect the live state of the AQP stack."""

from __future__ import annotations

import httpx
import typer

from aqp_cli.clients import ControlPlaneClient, DirectProbe
from aqp_cli.commands._common import exit_for_http_error
from aqp_cli.config import get_settings, load_auth_state, resolve_access_token
from aqp_cli.ui.output import console, info, render_json, render_table

app = typer.Typer(no_args_is_help=True, help="Detect and inspect AQP services.")


@app.command("list")
def list_services(
    direct: bool = typer.Option(
        False, "--direct", help="Skip control plane; probe Docker + k8s directly."
    ),
) -> None:
    """List every AQP service the CLI can see."""
    settings = get_settings()
    token = resolve_access_token(settings)
    rows: list[dict[str, str]] = []

    if not direct:
        try:
            cp = ControlPlaneClient(
                settings.control_plane_url, settings.http_timeout_seconds, token
            )
            for svc in cp.list_topology_services():
                rows.append(svc)
            cp.close()
        except Exception as exc:
            info(f"control-plane probe failed: {exc}; falling back to direct probe")
            direct = True

    if direct:
        probe = DirectProbe()
        for svc in probe.discover():
            rows.append(svc)

    if not rows:
        console.print("[yellow]No services discovered.[/yellow]")
        return
    render_table(
        "AQP services",
        ["name", "cluster", "namespace", "state"],
        [
            [r.get("name", ""), r.get("cluster", ""), r.get("namespace", ""), r.get("state", "")]
            for r in rows
        ],
    )


@app.command("status")
def status(service: str = typer.Argument(..., help="Service name to inspect.")) -> None:
    """Show detailed status for one service."""
    settings = get_settings()
    token = resolve_access_token(settings)
    cp = ControlPlaneClient(settings.control_plane_url, settings.http_timeout_seconds, token)
    try:
        payload = cp.service_status(service)
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        cp.close()
    render_json(payload)


@app.command("auth-state")
def auth_state() -> None:
    """Inspect local auth cache metadata (token is redacted)."""
    settings = get_settings()
    state = load_auth_state(settings)
    if "access_token" in state and isinstance(state["access_token"], str):
        token = state["access_token"]
        state["access_token"] = f"{token[:4]}..." if len(token) > 4 else "<redacted>"
    render_json(state)
