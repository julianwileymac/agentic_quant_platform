"""Compatibility shim for `aqp config` -> `aqp-cli config`."""

from __future__ import annotations

import typer

from aqp.cli._shim import run_aqp_cli

app = typer.Typer(
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@app.callback()
def callback(ctx: typer.Context) -> None:
    raise typer.Exit(code=run_aqp_cli(["config", *list(ctx.args)]))


__all__ = ["app", "callback"]
