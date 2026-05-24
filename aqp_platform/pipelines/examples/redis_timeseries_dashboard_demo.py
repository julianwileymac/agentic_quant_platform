#!/usr/bin/env python3
"""Populate ``stats:ingest:*`` and ``stats:semcache:*`` time series.

Generates synthetic data that the Redis Document Store Grafana
dashboard plots via the redis-datasource plugin.  Useful for verifying
that the dashboard wiring works after first deploy.

Usage::

    python -m pipelines.examples.redis_timeseries_dashboard_demo --duration 60

Set ``--duration 0`` to seed a single batch and exit.
"""

from __future__ import annotations

import argparse
import math
import random
import time

from pipelines.redis_io import get_redis, ping, record_timeseries, require_modules


SERIES = [
    ("stats:ingest:count", lambda t: max(0, int(50 + 30 * math.sin(t / 5)))),
    ("stats:ingest:bytes", lambda t: max(0, int(2_000_000 + 500_000 * math.sin(t / 7)))),
    ("stats:semcache:hits", lambda t: max(0, int(20 + 10 * math.cos(t / 3)))),
    ("stats:semcache:latency", lambda t: 5 + 5 * random.random()),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=120, help="Run for N seconds (0=once)")
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()

    if not ping():
        raise SystemExit("Cannot reach Redis. Check REDIS_URL / REDIS_PASSWORD.")
    require_modules(("timeseries",))

    client = get_redis()
    print(f"Seeding {len(SERIES)} time series; duration={args.duration}s")

    started = time.time()
    iteration = 0
    while True:
        elapsed = time.time() - started
        for name, fn in SERIES:
            value = float(fn(elapsed))
            record_timeseries(name, value, client=client)
        iteration += 1
        if args.duration <= 0:
            break
        if elapsed >= args.duration:
            break
        time.sleep(args.interval)

    print(f"Done. Wrote {iteration * len(SERIES)} samples across {len(SERIES)} series.")


if __name__ == "__main__":
    main()
