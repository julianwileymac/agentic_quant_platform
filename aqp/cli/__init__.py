"""``aqp`` CLI entry point.

The Typer app is exposed at :data:`aqp.cli.main.app` (matches the
``pyproject.toml`` ``[project.scripts]`` entry). New subcommands live as
their own modules and are added with ``app.add_typer(...)`` from
:mod:`aqp.cli.main`.
"""

from aqp.cli.main import app

__all__ = ["app"]
