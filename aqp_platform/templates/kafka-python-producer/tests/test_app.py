"""Minimal smoke tests for the producer template."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from producer.config import ProducerSettings


def test_settings_defaults():
    settings = ProducerSettings()
    assert settings.topic.startswith("market.")
    assert settings.sasl_mechanism == "SCRAM-SHA-512"
    assert settings.schema_registry_url.endswith("/apis/registry/v2")


@patch("producer.app.build_producer")
@patch("producer.app.configure_tracing")
def test_producer_app_constructs(configure, build):
    from producer.app import ProducerApp

    build.return_value = MagicMock()
    configure.return_value = MagicMock()
    app = ProducerApp(settings=ProducerSettings(), codec=MagicMock())
    assert app.producer is build.return_value
