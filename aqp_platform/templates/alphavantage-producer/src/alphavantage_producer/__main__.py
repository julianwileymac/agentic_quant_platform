"""Entrypoint: ``python -m alphavantage_producer``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .app import run_app
from .config import ProducerSettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alphavantage-producer", description=__doc__)
    parser.add_argument("--config", dest="config_file", default=None)
    parser.add_argument(
        "--log-level", default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings_kwargs: dict = {}
    if args.config_file:
        settings_kwargs["config_file"] = args.config_file
    settings = ProducerSettings(**settings_kwargs)
    try:
        asyncio.run(run_app(settings))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
