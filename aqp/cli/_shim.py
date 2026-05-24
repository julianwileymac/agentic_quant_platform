"""Compatibility shims forwarding legacy `aqp` CLI invocations to `aqp-cli`."""

from __future__ import annotations

import shutil
import subprocess
import sys


def run_aqp_cli(argv: list[str]) -> int:
    """Forward the given argument list to the standalone `aqp-cli` binary."""
    binary = shutil.which("aqp-cli")
    if not binary:
        sys.stderr.write(
            "aqp-cli is not installed or not on PATH. Install with `pip install -e ./aqp_cli`.\n"
        )
        return 127
    completed = subprocess.run([binary, *argv], check=False)  # noqa: S603
    return int(completed.returncode)
