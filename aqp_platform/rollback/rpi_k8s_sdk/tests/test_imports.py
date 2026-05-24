"""Smoke test confirming the package layout is importable."""

from __future__ import annotations


def test_configure_tracing_callable():
    from rpi_k8s_sdk import configure_tracing
    assert callable(configure_tracing)


def test_flink_client_init():
    from rpi_k8s_sdk.flink import ManagementFlinkClient
    client = ManagementFlinkClient(base_url="http://localhost:8080/api")
    try:
        assert client.base_url == "http://localhost:8080/api"
    finally:
        client.close()


def test_kafka_package_structure():
    import importlib

    mod = importlib.import_module("rpi_k8s_sdk.kafka")
    assert hasattr(mod, "AvroProducer")
    assert hasattr(mod, "AvroConsumer")
    assert hasattr(mod, "KafkaAdmin")
    assert hasattr(mod, "ApicurioClient")


def test_local_access_settings_defaults():
    from rpi_k8s_sdk import LocalAccessSettings

    settings = LocalAccessSettings()

    assert settings.minio_endpoint == "http://s3.local"
    assert settings.datahub_gms.local_url == "http://127.0.0.1:8080"
    assert settings.otel_collector.local_url == "http://127.0.0.1:4317"


def test_tunnel_command_includes_context_and_namespace():
    from rpi_k8s_sdk import LocalAccessSettings, LocalTunnelManager

    settings = LocalAccessSettings(kube_context="lab")
    tunnel = LocalTunnelManager(settings).datahub_gms()

    assert tunnel.command() == [
        "kubectl",
        "port-forward",
        "svc/datahub-datahub-gms",
        "8080:8080",
        "-n",
        "data-services",
        "--context",
        "lab",
    ]


def test_manifest_helpers():
    from rpi_k8s_sdk import kserve_inferenceservice_manifest, vllm_deployment_manifest

    vllm = vllm_deployment_manifest(name="tiny-llm", model_uri="s3://model-registry/tiny/")
    kserve = kserve_inferenceservice_manifest(name="tiny-llm", model_uri="s3://model-registry/tiny/")

    assert vllm["kind"] == "Deployment"
    assert vllm["spec"]["template"]["spec"]["containers"][0]["name"] == "vllm"
    assert kserve["kind"] == "InferenceService"


def test_aqp_helpers_importable():
    """Phase-4 additions should be importable from the top-level package."""

    from rpi_k8s_sdk import (
        aqp_session,
        duckdb_engine,
        get_tracer,
        iceberg_table,
        latest_mlflow_run,
        register_model,
        shutdown_tracing,
        submit_backtest,
    )

    assert callable(aqp_session)
    assert callable(submit_backtest)
    assert callable(register_model)
    assert callable(latest_mlflow_run)
    assert callable(iceberg_table)
    assert callable(duckdb_engine)
    assert callable(get_tracer)
    assert callable(shutdown_tracing)


def test_devloop_tunnel_helper_present():
    """`bring_up_aqp_devloop` should be reachable on LocalTunnelManager."""

    from rpi_k8s_sdk import LocalTunnelManager

    assert hasattr(LocalTunnelManager, "bring_up_aqp_devloop")


def test_management_auth_helper_present():
    """Phase 8 — ``ManagementAuth`` should be importable from the SDK."""

    from rpi_k8s_sdk import ManagementAuth

    auth = ManagementAuth(base_url="http://localhost:8080", token="test-token")
    assert auth.headers() == {"Authorization": "Bearer test-token"}
    auth_no_token = ManagementAuth(base_url="http://localhost:8080")
    assert auth_no_token.headers() == {}


def test_management_auth_from_env(monkeypatch):
    import os

    from rpi_k8s_sdk import ManagementAuth

    monkeypatch.setenv("RPI_MGMT_BASE_URL", "https://mgmt.example.com")
    monkeypatch.setenv("RPI_MGMT_AUTH_TOKEN", "env-token")
    auth = ManagementAuth.from_env()
    assert auth.base_url == "https://mgmt.example.com"
    assert auth.token == "env-token"
    assert auth.headers()["Authorization"] == "Bearer env-token"
