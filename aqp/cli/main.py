"""Top-level Typer app for the ``aqp`` CLI."""

from __future__ import annotations

import contextlib
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

# Phase 0 — Foundations. The rate-limit subsystem ships as a separate
# top-level boundary (`aqp_ratelimit/`) but extends the monolithic CLI
# so the operator UX matches the blueprint section 4.1.
with contextlib.suppress(ImportError):  # pragma: no cover
    from aqp_ratelimit.cli import keys_app, ratelimit_app

    app.add_typer(
        ratelimit_app,
        name="ratelimit",
        help="Inspect per-(user, service, key_id) rate-limit state",
    )
    app.add_typer(
        keys_app,
        name="keys",
        help="Lifecycle management for per-user vendor API keys",
    )

# Phase 3 — Hybrid local-cloud DX. The kernels subsystem ships as a
# separate top-level boundary (`aqp_kernels/`); the CLI extension is
# the operator-facing entry point.
with contextlib.suppress(ImportError):  # pragma: no cover
    from aqp_kernels.cli import kernel_app

    app.add_typer(
        kernel_app,
        name="kernel",
        help="Provision + attach per-user Jupyter kernel pods",
    )


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
