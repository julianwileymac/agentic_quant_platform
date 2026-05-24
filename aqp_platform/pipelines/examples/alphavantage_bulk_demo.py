"""Standalone demo: bulk-load AV fundamentals + daily bars into MinIO.

Run locally once the alphavantage-client and boto3 packages are installed and
``PIPELINE_MINIO_*`` env vars point at a running MinIO:

    export ALPHAVANTAGE_API_KEY_FILE='C:\\Users\\Julian Wiley\\Documents\\alphavantage_api_token.txt'
    export PIPELINE_MINIO_ENDPOINT='http://localhost:9000'
    export PIPELINE_MINIO_ACCESS_KEY='minioadmin'
    export PIPELINE_MINIO_SECRET_KEY='minioadmin'
    python -m pipelines.examples.alphavantage_bulk_demo
"""

from __future__ import annotations

import logging
from pprint import pprint

from pipelines.alphavantage_io import run_bulk_load
from pipelines.config import PipelineConfig


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = PipelineConfig()

    timeseries_result = run_bulk_load(
        config=config,
        category="timeseries",
        symbols=["IBM", "AAPL"],
        extra_params={"function": "daily", "outputsize": "compact"},
        target_bucket="av-raw",
    )
    print("Timeseries:")
    pprint(timeseries_result.__dict__)

    fundamentals_result = run_bulk_load(
        config=config,
        category="fundamentals",
        symbols=["IBM", "AAPL"],
        extra_params={"kinds": "overview,earnings"},
        target_bucket="av-raw",
    )
    print("Fundamentals:")
    pprint(fundamentals_result.__dict__)


if __name__ == "__main__":
    main()
