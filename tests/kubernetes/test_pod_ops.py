"""Tests for the Phase 1 pod-level KubernetesAdapter surface.

Covers:

- :class:`NoneAdapter` raises :class:`KubernetesAdapterUnavailable` for
  every new method (``list_pods``, ``exec_in_pod``, ``stream_pod_logs``,
  ``get_pod_archive``, ``put_pod_archive``).
- :class:`InClusterAdapter` raises ``Unavailable`` when the kubernetes
  package is missing or unconfigured (CI default).
- :class:`RpiClusterAdapter` forwards each method through a mocked
  :class:`ClusterMgmtClient`, honouring the ``data_b64`` envelope on
  archive ops.
- ``data.kubernetes.*`` :class:`DataMCPTool` subclasses are registered
  and produce ``ok=False`` ``MCPToolResult`` instances when the active
  adapter is the :class:`NoneAdapter`.
- :class:`LocalComposeAdapter` integration tests run only when the
  Docker daemon and SDK are available (skipped on CI by default).
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from aqp.kubernetes import (
    InClusterAdapter,
    KubernetesAdapterUnavailable,
    LocalComposeAdapter,
    NoneAdapter,
    PodExecResult,
    PodInfo,
    PodLogEvent,
    RpiClusterAdapter,
    register_adapter,
    reset_kubernetes_adapter,
)


@pytest.fixture(autouse=True)
def _reset_adapter():
    reset_kubernetes_adapter()
    yield
    reset_kubernetes_adapter()


# ---------------------------------------------------------------------------
# NoneAdapter — default 503-style raise on every new method
# ---------------------------------------------------------------------------


def test_none_adapter_pod_ops_raise_unavailable():
    adapter = NoneAdapter()
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.list_pods(namespace="ns")
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.exec_in_pod(namespace="ns", name="p", command=["true"])
    with pytest.raises(KubernetesAdapterUnavailable):
        # Generators raise on first iteration, not construction.
        for _ in adapter.stream_pod_logs(namespace="ns", name="p"):
            pass
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.get_pod_archive(namespace="ns", name="p", path="/etc")
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.put_pod_archive(namespace="ns", name="p", path="/etc", data=b"x")


# ---------------------------------------------------------------------------
# InClusterAdapter — unavailable without kubeconfig
# ---------------------------------------------------------------------------


def test_in_cluster_pod_ops_unavailable_without_kubeconfig():
    """Force the unloaded state regardless of host kubeconfig.

    The host machine that ran ``test_adapter.py`` historically expected
    no kubeconfig; some developer / CI environments now have one
    available so we force the adapter into ``_loaded=False`` to verify
    the unavailable-path branch on each new method.
    """
    adapter = InClusterAdapter()
    adapter._loaded = False
    adapter._k8s_module = None
    assert adapter.is_available() is False
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.list_pods(namespace="ns")
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.exec_in_pod(namespace="ns", name="p", command=["echo", "hi"])
    with pytest.raises(KubernetesAdapterUnavailable):
        for _ in adapter.stream_pod_logs(namespace="ns", name="p"):
            pass
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.get_pod_archive(namespace="ns", name="p", path="/")
    with pytest.raises(KubernetesAdapterUnavailable):
        adapter.put_pod_archive(namespace="ns", name="p", path="/", data=b"x")


# ---------------------------------------------------------------------------
# RpiClusterAdapter — proxies every pod op through ClusterMgmtClient
# ---------------------------------------------------------------------------


def _rpi_client(stub_methods: dict[str, object]) -> MagicMock:
    client = MagicMock()
    client.configured = True
    for k, v in stub_methods.items():
        getattr(client, k).return_value = v
    return client


def test_rpi_adapter_list_pods_forwards():
    client = _rpi_client(
        {
            "list_pods": [
                {
                    "namespace": "ns",
                    "name": "p",
                    "phase": "Running",
                    "node": "n1",
                    "pod_ip": "10.0.0.1",
                    "started_at": "2026-05-01T00:00:00Z",
                    "containers": ["c"],
                    "labels": {"app": "x"},
                }
            ]
        }
    )
    adapter = RpiClusterAdapter(client=client)
    pods = adapter.list_pods(namespace="ns", label_selector="app=x")
    assert len(pods) == 1
    assert isinstance(pods[0], PodInfo)
    assert pods[0].name == "p"
    assert pods[0].phase == "Running"
    assert pods[0].containers == ["c"]
    assert pods[0].labels == {"app": "x"}
    client.list_pods.assert_called_once_with(namespace="ns", label_selector="app=x")


def test_rpi_adapter_exec_forwards():
    client = _rpi_client(
        {
            "pod_exec": {
                "stdout": "hi\n",
                "stderr": "",
                "returncode": 0,
                "elapsed_ms": 12.3,
            }
        }
    )
    adapter = RpiClusterAdapter(client=client)
    res = adapter.exec_in_pod(
        namespace="ns",
        name="p",
        command=["echo", "hi"],
        container="c",
        timeout_seconds=10,
    )
    assert isinstance(res, PodExecResult)
    assert res.stdout == "hi\n"
    assert res.returncode == 0
    assert res.elapsed_ms == pytest.approx(12.3)
    client.pod_exec.assert_called_once_with(
        namespace="ns",
        name="p",
        command=["echo", "hi"],
        container="c",
        timeout_seconds=10,
    )


def test_rpi_adapter_exec_refuses_stdin():
    adapter = RpiClusterAdapter(client=_rpi_client({}))
    with pytest.raises(Exception, match="stdin"):
        adapter.exec_in_pod(
            namespace="ns", name="p", command=["cat"], stdin=b"hello"
        )


def test_rpi_adapter_log_stream_yields_events():
    client = _rpi_client(
        {
            "pod_logs_stream": [
                {
                    "namespace": "ns",
                    "name": "p",
                    "container": "c",
                    "line": "line 1",
                    "timestamp": "2026-05-01T00:00:00Z",
                    "source": "stdout",
                },
                {
                    "namespace": "ns",
                    "name": "p",
                    "container": "c",
                    "line": "line 2",
                    "timestamp": "2026-05-01T00:00:01Z",
                    "source": "stdout",
                },
            ]
        }
    )
    adapter = RpiClusterAdapter(client=client)
    events = list(
        adapter.stream_pod_logs(
            namespace="ns", name="p", container="c", tail_lines=10, follow=False
        )
    )
    assert len(events) == 2
    assert all(isinstance(e, PodLogEvent) for e in events)
    assert events[0].line == "line 1"
    assert events[1].timestamp == "2026-05-01T00:00:01Z"


def test_rpi_adapter_archive_round_trip():
    raw = b"hello world" * 10
    client = _rpi_client(
        {
            "pod_get_archive": {"data": base64.b64encode(raw).decode("ascii")},
            "pod_put_archive": {"bytes_written": len(raw), "ok": True},
        }
    )
    adapter = RpiClusterAdapter(client=client)
    got = adapter.get_pod_archive(
        namespace="ns", name="p", path="/x", container="c"
    )
    assert got == raw
    client.pod_get_archive.assert_called_once_with(
        namespace="ns", name="p", path="/x", container="c"
    )
    put = adapter.put_pod_archive(
        namespace="ns", name="p", path="/x", data=raw, container="c"
    )
    assert put["bytes_written"] == len(raw)
    assert put["ok"] is True
    # The adapter must base64-encode before forwarding.
    args, kwargs = client.pod_put_archive.call_args
    assert kwargs["data_b64"] == base64.b64encode(raw).decode("ascii")


# ---------------------------------------------------------------------------
# data.kubernetes.* MCP tools — registered + behave under the NoneAdapter
# ---------------------------------------------------------------------------


def test_data_kubernetes_tools_are_registered():
    from aqp.data.mcp.registry import DATA_MCP_TOOLS

    expected = {
        "data.kubernetes.list_pods",
        "data.kubernetes.exec_in_pod",
        "data.kubernetes.stream_pod_logs",
        "data.kubernetes.get_pod_archive",
        "data.kubernetes.put_pod_archive",
    }
    assert expected <= set(DATA_MCP_TOOLS)


def test_list_pods_tool_returns_ok_false_under_none_adapter():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    register_adapter(NoneAdapter())
    tool = get_data_mcp_tool("data.kubernetes.list_pods")
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("cluster:read",)),
        namespace="ns",
    )
    assert res.ok is False
    assert "unavailable" in (res.error or "").lower()


def test_exec_tool_requires_scope():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    register_adapter(NoneAdapter())
    tool = get_data_mcp_tool("data.kubernetes.exec_in_pod")
    # Missing scope - the base class rejects before adapter call.
    res = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        namespace="ns",
        name="p",
        command=["true"],
    )
    assert res.ok is False
    assert "policy" in (res.error or "").lower()


# ---------------------------------------------------------------------------
# LocalComposeAdapter — Docker SDK roundtrip (skipped without daemon)
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    try:
        import docker  # type: ignore

        client = docker.from_env(timeout=2)
        client.ping()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(
    not _docker_available(), reason="docker daemon / SDK not available in this env"
)
def test_local_compose_pod_ops_roundtrip(tmp_path):
    """Live integration: start alpine, exec + log + archive round-trip.

    Skipped automatically when the Docker daemon or python SDK is not
    available (CI default). Run locally with ``pytest -k local_compose``
    when validating Phase 1.
    """
    import docker  # type: ignore

    client = docker.from_env(timeout=10)
    container = client.containers.run(
        "alpine:3.20",
        ["sh", "-c", "while true; do echo tick; sleep 1; done"],
        detach=True,
        labels={"com.docker.compose.project": "aqp-test", "com.docker.compose.service": "ticker"},
    )
    try:
        adapter = LocalComposeAdapter()
        # list_pods sees the running container via the compose-service label.
        pods = adapter.list_pods(namespace="aqp-test")
        assert any(p.name == container.name for p in pods)

        # exec_in_pod
        res = adapter.exec_in_pod(
            namespace="aqp-test",
            name="ticker",
            command=["echo", "hello"],
            timeout_seconds=10,
        )
        assert res.returncode == 0
        assert "hello" in res.stdout

        # stream_pod_logs (bounded)
        events = list(
            adapter.stream_pod_logs(
                namespace="aqp-test",
                name="ticker",
                tail_lines=2,
                follow=False,
                max_lines=2,
            )
        )
        assert len(events) >= 1

        # archive round-trip
        archive = adapter.get_pod_archive(
            namespace="aqp-test", name="ticker", path="/etc/hostname"
        )
        assert len(archive) > 0
        # The bytes must be a parseable tar stream.
        import io
        import tarfile

        with tarfile.open(fileobj=io.BytesIO(archive), mode="r|") as tar:
            members = list(tar)
        assert any("hostname" in m.name for m in members)
    finally:
        try:
            container.stop(timeout=2)
        finally:
            container.remove(force=True)
