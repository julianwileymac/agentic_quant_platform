from __future__ import annotations

import subprocess
import sys


def test_source_alias_lookup_bootstraps_default_nodes() -> None:
    """Fresh interpreter lookup resolves ``source.*`` aliases.

    Dagster workers don't always import ``aqp.data.fetchers`` on boot.
    The registry must lazily import default nodes when a source alias is
    first resolved.
    """

    script = (
        "from aqp.data.engine.registry import get_node_class; "
        "cls = get_node_class('source.sec_filings'); "
        "print(cls.__module__ + ':' + cls.__name__)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "aqp.data.fetchers.api.sec:SecFilingsFetcher" in completed.stdout
