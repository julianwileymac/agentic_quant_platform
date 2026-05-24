"""Top-level Typer app. Subcommands live under ``aqp_cli.commands``."""
from __future__ import annotations

import typer

from aqp_cli import __version__
from aqp_cli.commands import auth, services, setup, update

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
