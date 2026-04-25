"""Run a backtest from a YAML recipe (strategy + backtest blocks)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from aqp.backtest.runner import run_backtest_from_config

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--run-name", type=str, default="cli")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    result = run_backtest_from_config(cfg, run_name=args.run_name, mlflow_log=not args.no_mlflow)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
