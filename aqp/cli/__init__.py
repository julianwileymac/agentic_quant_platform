"""Unified ``aqp`` command-line interface.

Entrypoint::

    aqp --help

All subcommands delegate to existing Python APIs (FastAPI/Celery/Solara/Dash)
so the CLI itself has zero runtime obligations beyond parsing arguments.
"""
from __future__ import annotations

from aqp.cli.main import app

__all__ = ["app"]
