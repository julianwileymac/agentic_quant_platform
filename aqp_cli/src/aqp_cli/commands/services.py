"""`aqp-cli services` — inspect the live state of the AQP stack.

Combines topology-from-control-plane with local probes (Docker socket,
kubernetes context) to highlight discrepancies between configured and
actually-running services.
"""
from __future__ import annotations

import typer

from aqp_cli.clients.control_plane import ControlPlaneClient
from aqp_cli.clients.direct import DirectProbe
from aqp_cli.config import get_settings
from aqp_cli.ui.output import console, info, render_table

app = typer.Typer(no_args_is_help=True, help="Detect and inspect AQP services.")


@app.command("list")
def list_services(
    direct: bool = typer.Option(
        False, "--direct", help="Skip control plane; probe Docker + k8s directly."
    ),
) -> None:
    """List every AQP service the CLI can see."""
    settings = get_settings()
    rows: list[dict[str, str]] = []

    if not direct:
        try:
            cp = ControlPlaneClient(settings.control_plane_url, settings.http_timeout_seconds)
            for svc in cp.list_topology_services():
                rows.append(svc)
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
        [[r.get("name", ""), r.get("cluster", ""), r.get("namespace", ""), r.get("state", "")]
         for r in rows],
    )


@app.command("status")
def status(service: str = typer.Argument(..., help="Service name to inspect.")) -> None:
    """Show detailed status for one service."""
    settings = get_settings()
    cp = ControlPlaneClient(settings.control_plane_url, settings.http_timeout_seconds)
    info(f"Resolving {service} via control plane at {cp.base_url} (stub)")
    console.print(f"[cyan]services status {service}: stub — will call /manage/deployments/{service}.[/cyan]")
