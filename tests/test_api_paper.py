"""FastAPI paper route smoke tests."""
from __future__ import annotations


def test_paper_routes_registered() -> None:
    """``/paper/start`` and ``/paper/runs`` should be discoverable on the app."""
    from aqp.api.main import app

    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/paper/start" in paths
    assert "/paper/runs" in paths
    assert "/paper/runs/{run_id}" in paths
    assert "/paper/stop/{task_id}" in paths


def test_data_load_route_registered() -> None:
    from aqp.api.main import app

    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/data/load" in paths


def test_dash_mounted() -> None:
    """The Dash sub-app should be mounted under /dash."""
    from aqp.api.main import app

    mounts = [r for r in app.routes if getattr(r, "path", None) == "/dash"]
    assert mounts, "Dash was not mounted at /dash"
