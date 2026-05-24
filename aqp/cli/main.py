"""Top-level Typer app for the ``aqp`` CLI."""

from __future__ import annotations

import sys

import typer

from aqp.cli._shim import run_aqp_cli
from aqp.cli.config_cmd import app as config_app
from aqp.cli.cp_cmd import app as cp_app
from aqp.cli.deploy_cmd import app as deploy_app
from aqp.cli.viz_cmd import app as viz_app

app = typer.Typer(
    name="aqp",
    help="Legacy compatibility shim. Prefer `aqp-cli`.",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
app.add_typer(config_app, name="config", help="Layered config inspection / mutation")
app.add_typer(cp_app, name="cp", help="AQP control-plane day-2 operations")
app.add_typer(viz_app, name="viz", help="Visualization layer (Superset + Bokeh) operations")
app.add_typer(deploy_app, name="deploy", help="Local stack lifecycle (Terraform + k3d)")


@app.callback()
def _main(ctx: typer.Context) -> None:
    """Forward unknown invocations to `aqp-cli` with a deprecation notice."""
    typer.echo("`aqp` is deprecated; forwarding to `aqp-cli`.", err=True)
    if ctx.invoked_subcommand:
        return
    raise typer.Exit(code=run_aqp_cli(list(ctx.args)))


def main() -> int:
    """Console-script entrypoint used by root pyproject."""
    return run_aqp_cli(sys.argv[1:])


if __name__ == "__main__":
    app()
