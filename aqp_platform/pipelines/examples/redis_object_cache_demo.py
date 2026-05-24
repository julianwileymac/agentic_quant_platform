#!/usr/bin/env python3
"""Demonstrate the @cache_aside decorator for Python object caching.

Wraps an "expensive" function with the Redis cache-aside pattern (SHA-256
of args -> cache key) and records hit/miss counters into the
``stats:cache`` hash.  Counters back the Redis Document Store Grafana
dashboard.

Usage::

    python -m pipelines.examples.redis_object_cache_demo --symbols AAPL MSFT NVDA AAPL
"""

from __future__ import annotations

import argparse
import random
import time

from pipelines.redis_cache import cache_aside


@cache_aside(ttl=30, namespace="examples.market")
def fetch_market_snapshot(symbol: str) -> dict:
    time.sleep(0.4)
    return {
        "symbol": symbol,
        "price": round(random.uniform(50, 500), 2),
        "ts": time.time(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "AAPL", "MSFT", "AAPL"])
    args = parser.parse_args()

    for sym in args.symbols:
        started = time.perf_counter()
        snap = fetch_market_snapshot(sym)
        elapsed = (time.perf_counter() - started) * 1000
        print(f"{sym}: ${snap['price']:.2f}  ({elapsed:5.0f} ms)")


if __name__ == "__main__":
    main()
