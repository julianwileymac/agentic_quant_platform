"""Top-level Typer app. Subcommands live under ``aqp_cli.commands``."""

from __future__ import annotations

import typer

from aqp_cli import __version__
from aqp_cli.commands import (
    account,
    auth,
    client,
    config,
    cp,
    deploy,
    ide,
    services,
    setup,
    update,
    viz,
    wrappers,
)

app = typer.Typer(
    name="aqp-cli",
    help="Standalone operator CLI for the Agentic Quant Platform.",
    no_args_is_help=True,
    add_completion=True,
)

app.add_typer(setup.app, name="setup", help="Bootstrap local environment + verify prereqs.")
app.add_typer(services.app, name="services", help="Detect and inspect running AQP services.")
app.add_typer(update.app, name="update", help="Check + apply updates to the local stack.")
app.add_typer(auth.app, name="auth", help="Authenticate via the control plane (or --direct).")
app.add_typer(account.app, name="account", help="General account-management commands.")
app.add_typer(config.app, name="config", help="Layered config inspection / mutation.")
app.add_typer(cp.app, name="cp", help="AQP control-plane day-2 operations.")
app.add_typer(deploy.app, name="deploy", help="Local stack lifecycle helpers.")
app.add_typer(viz.app, name="viz", help="Visualization operations (Superset + Bokeh).")
app.add_typer(client.app, name="client", help="Control local aqp_client process/builds.")
app.add_typer(ide.app, name="ide", help="Control local Theia IDE process/builds.")
app.add_typer(wrappers.app, name="tools", help="Wrapper commands for external/helper CLIs.")


@app.command(
    "bots",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def bots_passthrough(ctx: typer.Context) -> None:
    """Compatibility shim: `aqp-cli bots ...` delegates to `aqp-cli tools bots ...`."""
    wrappers.bots_passthrough(ctx)


@app.command(
    "control-plane",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def control_plane_passthrough(ctx: typer.Context) -> None:
    wrappers.control_plane_passthrough(ctx)


@app.command(
    "admin-api",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def admin_api_passthrough(ctx: typer.Context) -> None:
    wrappers.admin_api_passthrough(ctx)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"aqp-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True
    ),
) -> None:
    """Standalone operator CLI for the Agentic Quant Platform."""


if __name__ == "__main__":
    app()
