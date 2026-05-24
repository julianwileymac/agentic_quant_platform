"""`aqp-cli update` — pull repository + image updates."""
from __future__ import annotations

import typer

from aqp_cli.config import get_settings
from aqp_cli.ui.output import console, info

app = typer.Typer(no_args_is_help=True, help="Check + apply updates to the AQP stack.")


@app.command("check")
def check() -> None:
    """Compare local image / git versions against the control plane's latest."""
    settings = get_settings()
    info(f"Would compare versions against {settings.control_plane_url}/manage/versions (stub)")
    console.print("[cyan]update check: stub.[/cyan]")


@app.command("apply")
def apply(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without applying."),
) -> None:
    """Apply available updates (pull images, run migrations, restart in order)."""
    info(f"dry_run={dry_run}; would request control plane to coordinate rolling update (stub)")
    console.print("[cyan]update apply: stub — wire to /manage/updates once implemented.[/cyan]")
