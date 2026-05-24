"""`aqp-cli setup` — bootstrap a fresh local AQP environment.

Stubs only. Real logic will resolve through the control plane's
``/manage/bootstrap/*`` surface once it exists.
"""
from __future__ import annotations

import typer

from aqp_cli.config import get_settings
from aqp_cli.ui.output import console, info, warn

app = typer.Typer(no_args_is_help=True, help="Bootstrap local AQP environment.")


@app.command("init")
def init(
    env_file: str = typer.Option(".env", "--env-file", help="Path to write derived .env."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing env file."),
) -> None:
    """Bootstrap a local AQP environment (derived .env, volumes, networks)."""
    settings = get_settings()
    info(f"Would derive {env_file} from topology at {settings.api_url} (stub)")
    if overwrite:
        warn("--overwrite specified; existing file would be replaced.")
    console.print("[green]setup init: stub — wire to /manage/bootstrap once implemented.[/green]")


@app.command("verify")
def verify() -> None:
    """Verify local prerequisites (Docker, kubectl, Python, ports)."""
    console.print("[yellow]setup verify: stub — will probe local toolchain.[/yellow]")


@app.command("render-config")
def render_config(
    output: str = typer.Option("configs/local.generated.yaml", "--output", "-o"),
) -> None:
    """Render derived local configuration from the topology service."""
    settings = get_settings()
    info(f"Would render {output} from topology at {settings.api_url} (stub)")
