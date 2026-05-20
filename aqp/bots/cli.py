"""Compatibility entrypoint for ``python -m aqp.bots.cli``."""
from __future__ import annotations

from aqp_bots.cli import *  # noqa: F401,F403
from aqp_bots.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
