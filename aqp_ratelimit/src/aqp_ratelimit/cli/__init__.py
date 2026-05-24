"""Typer subcommands wired into the top-level ``aqp`` CLI.

The monolith's [aqp/cli/main.py](../../../aqp/cli/main.py) imports
:func:`ratelimit_app` and :func:`keys_app` and registers them as
``aqp ratelimit`` and ``aqp keys`` so the operator UX matches the
blueprint section 4.1.
"""
from __future__ import annotations

from aqp_ratelimit.cli.keys_cmd import app as keys_app
from aqp_ratelimit.cli.ratelimit_cmd import app as ratelimit_app

__all__ = ["keys_app", "ratelimit_app"]
