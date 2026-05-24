"""Opt-in live cluster smoke tests.

Run with RPI_K8S_RUN_INTEGRATION=1 after local hosts/tunnels are configured.
"""

from __future__ import annotations

import os
from urllib.request import Request, urlopen

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RPI_K8S_RUN_INTEGRATION") != "1",
    reason="live cluster smoke tests are opt-in",
)


def test_live_minio_bucket_listing():
    from rpi_k8s_sdk import MinioClient

    assert "bucket_count" in MinioClient().health()


def test_live_mlflow_experiment_round_trip():
    from rpi_k8s_sdk import MLflowClient

    experiment_id = MLflowClient().ensure_experiment("rpi-k8s-local-smoke")

    assert experiment_id


def test_live_datahub_gms_health():
    from rpi_k8s_sdk import load_settings

    settings = load_settings()
    request = Request(f"{settings.datahub_gms_url.rstrip('/')}/config", method="GET")

    with urlopen(request, timeout=10) as response:
        assert response.status < 500


def test_live_otel_endpoint_accepts_tcp():
    import socket
    from urllib.parse import urlparse

    from rpi_k8s_sdk import load_settings

    parsed = urlparse(load_settings().otlp_endpoint)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 4317

    with socket.create_connection((host, port), timeout=5):
        pass
