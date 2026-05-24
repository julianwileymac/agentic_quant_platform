"""Secret-broker server + client smoke tests (uses TCP-emulated socket)."""
from __future__ import annotations

import os
import platform
import tempfile

import pytest

skip_on_windows = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Unix-domain-socket tests run on Linux + macOS only.",
)


@skip_on_windows
def test_server_starts_and_stops_cleanly():
    from aqp_kernels.secret_broker.server import SecretBrokerServer

    with tempfile.TemporaryDirectory() as tmp:
        sock_path = os.path.join(tmp, "broker.sock")
        server = SecretBrokerServer(socket_path=sock_path)
        server.start()
        assert os.path.exists(sock_path)
        server.stop()
        assert not os.path.exists(sock_path)


@skip_on_windows
def test_client_returns_none_on_missing_credential():
    from aqp_kernels.secret_broker.client import SecretBrokerClient
    from aqp_kernels.secret_broker.server import SecretBrokerServer

    with tempfile.TemporaryDirectory() as tmp:
        sock_path = os.path.join(tmp, "broker.sock")
        server = SecretBrokerServer(socket_path=sock_path)
        server.start()
        try:
            client = SecretBrokerClient(socket_path=sock_path)
            assert client.resolve(service="no_such_provider") is None
        finally:
            server.stop()
