"""Synchronously run the research crew (no Celery) — useful for debugging."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from aqp.agents.crew import DEFAULT_CREW_CONFIG, run_research_crew


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", type=str, help="Research prompt for the crew.")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CREW_CONFIG))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_research_crew(args.prompt, config_path=Path(args.config))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
