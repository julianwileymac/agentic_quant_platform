"""Top-level Typer app for the ``aqp`` CLI."""
from __future__ import annotations

import typer

from aqp.cli.config_cmd import app as config_app
from aqp.cli.cp_cmd import app as cp_app
from aqp.cli.deploy_cmd import app as deploy_app
from aqp.cli.viz_cmd import app as viz_app

app = typer.Typer(
    name="aqp",
    help="Agentic Quant Platform CLI",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config", help="Layered config inspection / mutation")
app.add_typer(cp_app, name="cp", help="AQP control-plane day-2 operations")
app.add_typer(viz_app, name="viz", help="Visualization layer (Superset + Bokeh) operations")
app.add_typer(deploy_app, name="deploy", help="Local stack lifecycle (Terraform + k3d)")


@app.callback()
def _main() -> None:
    """Entry point — subcommands handle the actual work."""


if __name__ == "__main__":
    app()
