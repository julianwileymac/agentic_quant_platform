"""Typer subcommands wired into the monolith ``aqp`` CLI."""
from __future__ import annotations

from aqp_kernels.cli.kernel_cmd import app as kernel_app

__all__ = ["kernel_app"]
