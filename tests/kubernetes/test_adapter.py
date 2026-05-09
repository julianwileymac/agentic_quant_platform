"""Tests for :mod:`aqp.kubernetes`.

Covers:

- :class:`NoneAdapter` raises :class:`KubernetesAdapterUnavailable` for
  every operation and reports ``is_available() is False``.
- :class:`RpiClusterAdapter` forwards every method to the wrapped
  ``ClusterMgmtClient`` and is unavailable when the URL is empty.
- :class:`InClusterAdapter` reports unavailable when the kubernetes
  package is missing or unconfigured (CI default).
- The active-adapter selector reads ``settings.kubernetes_adapter`` and
  honours the legacy ``cluster_mgmt_url`` auto-promote.
- The metaclass registers every concrete adapter under
  ``"k8s_adapter"``.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aqp.kubernetes import (
    InClusterAdapter,
    KubernetesAdapter,
    KubernetesAdapterUnavailable,
    NoneAdapter,
    RpiClusterAdapter,
    get_kubernetes_adapter,
    list_adapter_classes,
    register_adapter,
    reset_kubernetes_adapter,
)


@pytest.fixture(autouse=True)
def _reset_adapter():
    reset_kubernetes_adapter()
    yield
    reset_kubernetes_adapter()


def test_metaclass_registers_concrete_adapters():
    classes = list_adapter_classes()
    aliases = set(classes.keys())
    assert {"NoneAdapter", "RpiClusterAdapter", "InClusterAdapter", "LocalComposeAdapter"} <= aliases


def test_metaclass_skips_abstract_base():
    # The abstract :class:`KubernetesAdapter` itself must not register.
    assert "KubernetesAdapter" not in list_adapter_classes()


def test_none_adapter_is_unavailable():
    adapter = NoneAdapter()
    assert adapter.is_available() is False
    info = adapter.describe()
    assert info["available"] is False
    assert info["kind"] == "none"


def test_none_adapter_raises_unavailable_for_every_op():
    adapter = NoneAdapter()
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.scale_deployment(namespace="ns", name="dep", replicas=1)
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.kafka_topics()
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.flink_session_jobs()


def test_rpi_adapter_forwards_to_client():
    fake_client = MagicMock()
    fake_client.configured = True
    fake_client.kafka_topics.return_value = [{"name": "t"}]
    fake_client.alphavantage_stream.return_value = {"desired_replicas": 2}

    adapter = RpiClusterAdapter(client=fake_client)
    assert adapter.is_available() is True
    assert adapter.kafka_topics() == [{"name": "t"}]
    assert adapter.alphavantage_stream(enable=True, replicas=2) == {"desired_replicas": 2}
    fake_client.kafka_topics.assert_called_once_with()
    fake_client.alphavantage_stream.assert_called_once_with(enable=True, replicas=2)


def test_rpi_adapter_unavailable_when_client_not_configured():
    fake_client = MagicMock()
    fake_client.configured = False
    adapter = RpiClusterAdapter(client=fake_client)
    assert adapter.is_available() is False
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.kafka_topics()


def test_rpi_adapter_translates_cluster_mgmt_error():
    from aqp.kubernetes.protocol import KubernetesAdapterError
    from aqp.services.cluster_mgmt_client import ClusterMgmtError

    fake_client = MagicMock()
    fake_client.configured = True
    fake_client.kafka_topics.side_effect = ClusterMgmtError("boom")
    adapter = RpiClusterAdapter(client=fake_client)
    with pytest.raises(KubernetesAdapterError, match="boom"):
        adapter.kafka_topics()


def test_in_cluster_adapter_is_unavailable_without_kubeconfig():
    adapter = InClusterAdapter()
    assert adapter.is_available() is False
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.scale_deployment(namespace="ns", name="dep", replicas=1)


def test_register_adapter_overrides_active():
    class _Spy(KubernetesAdapter):
        adapter_kind = "spy-test"
        adapter_alias = "SpyAdapter"

        def is_available(self) -> bool:
            return True

    spy = _Spy()
    register_adapter(spy)
    assert get_kubernetes_adapter() is spy


def test_get_active_adapter_uses_settings(monkeypatch):
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "kubernetes_adapter", "none", raising=False)
    monkeypatch.setattr(_settings, "cluster_mgmt_url", "", raising=False)
    adapter = get_kubernetes_adapter()
    assert isinstance(adapter, NoneAdapter)


def test_get_active_adapter_auto_promotes_rpi_when_url_set(monkeypatch):
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "kubernetes_adapter", "", raising=False)
    monkeypatch.setattr(_settings, "cluster_mgmt_url", "http://rpi-mgmt:8080", raising=False)
    adapter = get_kubernetes_adapter()
    assert isinstance(adapter, RpiClusterAdapter)


def test_get_active_adapter_falls_back_to_none_for_unknown_kind(monkeypatch):
    from aqp.config import settings as _settings

    monkeypatch.setattr(_settings, "kubernetes_adapter", "definitely-not-a-real-adapter", raising=False)
    monkeypatch.setattr(_settings, "cluster_mgmt_url", "", raising=False)
    adapter = get_kubernetes_adapter()
    assert isinstance(adapter, NoneAdapter)


def test_describe_omits_secrets():
    adapter = NoneAdapter()
    info = adapter.describe()
    keys = set(info.keys())
    assert keys == {"kind", "alias", "available"}
