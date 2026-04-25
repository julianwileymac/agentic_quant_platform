"""``aqp-stream-ingest`` console script entry point."""
from __future__ import annotations

import argparse
import asyncio
import logging

from aqp.config import settings
from aqp.streaming.runtime import run_ingester


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aqp-stream-ingest",
        description="Run the AQP streaming ingester (IBKR/Alpaca -> Kafka).",
    )
    parser.add_argument(
        "--venue",
        choices=["ibkr", "alpaca", "all"],
        default="all",
        help="Which upstream venue(s) to run. Default: all.",
    )
    parser.add_argument(
        "--universe",
        default=None,
        help="Override AQP_STREAM_UNIVERSE with a comma-separated ticker list.",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=None,
        help="Override AQP_STREAM_METRICS_PORT for the Prometheus endpoint.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Override AQP_LOG_LEVEL (DEBUG/INFO/WARNING/ERROR).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    level = (args.log_level or settings.log_level).upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    universe = (
        [s.strip() for s in args.universe.split(",") if s.strip()]
        if args.universe
        else None
    )
    asyncio.run(run_ingester(venue=args.venue, universe=universe, metrics_port=args.metrics_port))


if __name__ == "__main__":  # pragma: no cover
    main()
