"""Download the default universe from yfinance into the Parquet lake."""
from __future__ import annotations

import argparse
import logging
import sys

from aqp.config import settings
from aqp.data.ingestion import ingest

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download bars via yfinance into Parquet.")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated tickers.")
    parser.add_argument("--start", type=str, default=None)
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--interval", type=str, default="1d")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    symbols = [s.strip() for s in (args.symbols or "").split(",") if s.strip()] or settings.universe_list
    df = ingest(symbols=symbols, start=args.start, end=args.end, interval=args.interval)
    if df.empty:
        logger.error("No data fetched. Check tickers / network.")
        return 1
    logger.info("Wrote %d rows across %d tickers.", len(df), df["vt_symbol"].nunique())
    return 0


if __name__ == "__main__":
    sys.exit(main())
