"""Brokers route detection logic — venue inventory + status diagnostic ladder.

Exercises the four states an IBKR-style venue can be in:

1. SDK present, gateway listening    -> reachable=True,  available=True
2. SDK present, gateway closed       -> reachable=False, available=False
3. SDK missing, gateway listening    -> available=False, missing_extras=['ib-async']
4. SDK missing, gateway closed       -> available=False, both signals reported

Each state also has a corresponding ``venue_status()`` rung that returns
``ok=False`` with a distinct ``stage`` value the UI can render.
"""
from __future__ import annotations

import socket
from contextlib import closing
from typing import Iterator

import pytest


@pytest.fixture
def fastapi_test_client():
    fastapi = pytest.importorskip("fastapi.testclient")
    from aqp.api.main import app

    return fastapi.TestClient(app)


@pytest.fixture
def open_tcp_port() -> Iterator[int]:
    """Yield a port we hold open for the duration of the test."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        yield port
    finally:
        with closing(sock):
            pass


def test_tcp_probe_succeeds_on_open_port(open_tcp_port: int) -> None:
    from aqp.api.routes.brokers import _tcp_probe

    assert _tcp_probe("127.0.0.1", open_tcp_port) is True


def test_tcp_probe_fails_fast_on_closed_port() -> None:
    from aqp.api.routes.brokers import _tcp_probe

    # Bind+close a socket so we can hand back a port we know is closed
    # right now (and won't be reused before the assertion).
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    assert _tcp_probe("127.0.0.1", port, timeout=0.25) is False


def test_ibkr_descriptor_reports_gateway_when_sdk_and_port_ok(
    monkeypatch: pytest.MonkeyPatch, open_tcp_port: int
) -> None:
    from aqp.api.routes import brokers as br
    from aqp.config import settings

    monkeypatch.setattr(br, "_sdk_version", lambda name: "9.9.9" if name == "ib_async" else None)
    monkeypatch.setattr(settings, "ibkr_host", "127.0.0.1")
    monkeypatch.setattr(settings, "ibkr_port", open_tcp_port)

    info = br._ibkr_descriptor()
    assert info.available is True
    assert info.reachable is True
    assert info.sdk_version == "9.9.9"
    assert info.endpoint == f"127.0.0.1:{open_tcp_port}"
    assert info.missing_extras == []
    assert "Both SDK and gateway are healthy" in info.description


def test_ibkr_descriptor_flags_gateway_down_when_port_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aqp.api.routes import brokers as br
    from aqp.config import settings

    monkeypatch.setattr(br, "_sdk_version", lambda name: "9.9.9")
    monkeypatch.setattr(settings, "ibkr_host", "127.0.0.1")
    # Bind+immediately close to obtain a free (closed) port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(settings, "ibkr_port", closed_port)

    info = br._ibkr_descriptor()
    assert info.reachable is False
    assert info.available is False
    assert "Gateway not listening" in info.description


def test_ibkr_descriptor_flags_sdk_missing_even_when_port_open(
    monkeypatch: pytest.MonkeyPatch, open_tcp_port: int
) -> None:
    from aqp.api.routes import brokers as br
    from aqp.config import settings

    monkeypatch.setattr(br, "_sdk_version", lambda name: None)
    monkeypatch.setattr(settings, "ibkr_host", "127.0.0.1")
    monkeypatch.setattr(settings, "ibkr_port", open_tcp_port)

    info = br._ibkr_descriptor()
    assert info.available is False
    assert info.reachable is True  # gateway is up
    assert info.missing_extras == ["ib-async"]
    assert "Install the SDK" in info.description


def test_sdk_version_does_not_import_target_module() -> None:
    """Critical regression guard: ``_sdk_version`` must NOT import the SDK.

    Importing ``ib_async`` transitively pulls in ``aeventkit``, which on
    Python 3.14 has been observed to break ``sniffio``'s asyncio backend
    detection — every sync FastAPI route then starts 500'ing with
    ``anyio.NoEventLoopError``. Use ``importlib.util.find_spec`` plus
    ``importlib.metadata.version`` instead.
    """
    import sys

    from aqp.api.routes.brokers import _sdk_version

    sys.modules.pop("ib_async", None)
    sys.modules.pop("aeventkit", None)
    sys.modules.pop("alpaca", None)
    # Deliberately call the helper with names whose modules are NOT yet imported.
    for name in ("ib_async", "alpaca"):
        _sdk_version(name)
    assert "ib_async" not in sys.modules, (
        "_sdk_version imported ib_async — that triggers aeventkit's asyncio "
        "patching and breaks sync route handlers."
    )
    assert "aeventkit" not in sys.modules
    assert "alpaca" not in sys.modules


def test_sdk_version_returns_real_version_for_installed_pkg() -> None:
    """If the dist is installed we should get a meaningful semver back."""
    from aqp.api.routes.brokers import _sdk_version

    fastapi_ver = _sdk_version("fastapi")
    assert fastapi_ver is not None and fastapi_ver != "?"
    assert fastapi_ver[0].isdigit()


def test_sync_route_returns_200_under_uvicorn_event_loop(fastapi_test_client) -> None:
    """End-to-end guard for the asyncio + threadpool path that broke.

    The ``/brokers/`` route handler is sync (``def``), which Starlette
    runs via ``anyio.to_thread.run_sync``. If anything in the descriptor
    pipeline trashes ``sniffio``'s backend detection, this returns 500.
    """
    response = fastapi_test_client.get("/brokers/")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 4
    response = fastapi_test_client.get("/brokers/schema")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "module_name",
    [
        "aqp.trading.brokerages.ibkr",
        "aqp.trading.feeds.ibkr_feed",
    ],
)
def test_ibkr_modules_never_call_patch_asyncio(module_name: str) -> None:
    """Regression guard for the ``patchAsyncio`` / ``nest_asyncio`` trap.

    ``ib_async.util.patchAsyncio()`` monkey-patches asyncio (via
    ``nest_asyncio.apply()``) so nested ``asyncio.run`` calls work
    inside Jupyter. Calling it inside a FastAPI/uvicorn worker on
    Python 3.14 breaks ``anyio.to_thread.run_sync`` — every sync
    FastAPI route 500s with ``anyio.NoEventLoopError`` afterwards.

    Neither the IBKR brokerage adapter nor the IBKR live-bars feed
    should call it or even import ``ib_async.util``. We verify via AST
    traversal so docstrings mentioning ``patchAsyncio`` (like the one
    explaining *why* we avoid it) don't false-alarm.
    """
    import ast
    import importlib
    import inspect

    mod = importlib.import_module(module_name)
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            assert name != "patchAsyncio", (
                f"ib_async.util.patchAsyncio() is called at line "
                f"{node.lineno} of {module_name}. It must not be — it "
                "breaks anyio's backend detection on Python 3.14."
            )
        if isinstance(node, ast.ImportFrom) and node.module == "ib_async":
            names = [a.name for a in node.names]
            assert "util" not in names and "ib_util" not in names, (
                f"{module_name} imports ib_async.util — the only reason "
                "to import it was patchAsyncio, which must not be called "
                "on the server. Remove the import."
            )


def test_brokers_root_lists_four_venues(fastapi_test_client) -> None:
    response = fastapi_test_client.get("/brokers/")
    assert response.status_code == 200
    payload = response.json()
    names = [v["name"] for v in payload]
    assert names == ["alpaca", "ibkr", "tradier", "simulated"]
    # The new fields must be present on every entry.
    for v in payload:
        assert "endpoint" in v
        assert "reachable" in v
        assert "sdk_version" in v


def test_status_ladder_returns_sdk_missing_diagnostic(
    fastapi_test_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aqp.api.routes import brokers as br

    monkeypatch.setattr(br, "_sdk_version", lambda name: None)
    response = fastapi_test_client.get("/brokers/ibkr/status")
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["stage"] == "sdk-missing"
    assert "ib-async" in body["error"]


def test_status_ladder_returns_gateway_down_diagnostic(
    fastapi_test_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aqp.api.routes import brokers as br
    from aqp.config import settings

    monkeypatch.setattr(br, "_sdk_version", lambda name: "9.9.9")
    monkeypatch.setattr(settings, "ibkr_host", "127.0.0.1")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    closed_port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setattr(settings, "ibkr_port", closed_port)

    response = fastapi_test_client.get("/brokers/ibkr/status")
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["stage"] == "gateway-down"
    assert "No process listening" in body["error"]
    assert body["reachable"] is False
    assert body["sdk_version"] == "9.9.9"
