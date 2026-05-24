"""Script-entrypoint shims forwarding legacy helper binaries to `aqp-cli`."""

from __future__ import annotations

import sys

from aqp.cli._shim import run_aqp_cli


def _forward(prefix: list[str]) -> int:
    return run_aqp_cli(prefix + sys.argv[1:])


def bootstrap_main() -> int:
    return _forward(["tools", "helpers", "bootstrap"])


def download_main() -> int:
    return _forward(["tools", "helpers", "download"])


def index_main() -> int:
    return _forward(["tools", "helpers", "index"])


def train_main() -> int:
    return _forward(["tools", "helpers", "train"])


def backtest_main() -> int:
    return _forward(["tools", "helpers", "backtest"])


def stream_ingest_main() -> int:
    return _forward(["tools", "helpers", "stream-ingest"])


def export_schemas_main() -> int:
    return _forward(["tools", "helpers", "export-schemas"])


def bots_main() -> int:
    return _forward(["bots"])
