"""Wrapper commands that unify external CLI binaries under `aqp-cli`."""

from __future__ import annotations

import shutil
import subprocess
import sys

import typer

from aqp_cli.ui.output import error, info

app = typer.Typer(no_args_is_help=True, help="Compatibility wrappers for package/helper CLIs.")
helpers_app = typer.Typer(no_args_is_help=True, help="Helper-script wrappers.")

app.add_typer(helpers_app, name="helpers")


def _run(binary: str, args: list[str]) -> None:
    executable = shutil.which(binary)
    if not executable:
        error(f"{binary} not found on PATH")
        raise typer.Exit(code=127)
    info("running: " + " ".join([binary, *args]))
    rc = subprocess.run([executable, *args], check=False).returncode  # noqa: S603
    raise typer.Exit(code=int(rc))


@app.command(
    "bots",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def bots_passthrough(ctx: typer.Context) -> None:
    """Pass through to `aqp-bots`."""
    _run("aqp-bots", list(ctx.args))


@app.command(
    "control-plane",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def control_plane_passthrough(ctx: typer.Context) -> None:
    """Pass through to `aqp-control-plane`."""
    _run("aqp-control-plane", list(ctx.args))


@app.command(
    "admin-api",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def admin_api_passthrough(ctx: typer.Context) -> None:
    """Pass through to `aqp-admin-api`."""
    _run("aqp-admin-api", list(ctx.args))


@helpers_app.command(
    "bootstrap", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def helper_bootstrap(ctx: typer.Context) -> None:
    _run("aqp-bootstrap", list(ctx.args))


@helpers_app.command(
    "download", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def helper_download(ctx: typer.Context) -> None:
    _run("aqp-download", list(ctx.args))


@helpers_app.command(
    "index", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def helper_index(ctx: typer.Context) -> None:
    _run("aqp-index", list(ctx.args))


@helpers_app.command(
    "train", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def helper_train(ctx: typer.Context) -> None:
    _run("aqp-train", list(ctx.args))


@helpers_app.command(
    "backtest", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def helper_backtest(ctx: typer.Context) -> None:
    _run("aqp-backtest", list(ctx.args))


@helpers_app.command(
    "stream-ingest",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def helper_stream_ingest(ctx: typer.Context) -> None:
    _run("aqp-stream-ingest", list(ctx.args))


@helpers_app.command(
    "export-schemas",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def helper_export_schemas(ctx: typer.Context) -> None:
    _run("aqp-export-schemas", list(ctx.args))


@helpers_app.command(
    "serve",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def helper_serve(ctx: typer.Context) -> None:
    """Pass through to `python -m aqp.mlops.serving.cli`."""
    info("running: python -m aqp.mlops.serving.cli " + " ".join(ctx.args))
    rc = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "aqp.mlops.serving.cli", *list(ctx.args)],
        check=False,
    ).returncode
    raise typer.Exit(code=int(rc))
