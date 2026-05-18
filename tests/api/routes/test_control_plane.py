from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def test_pod_info_dict_handles_slotted_dataclass():
    from aqp.api.routes.control_plane import _pod_info_dict
    from aqp.kubernetes.protocol import PodInfo

    payload = _pod_info_dict(
        PodInfo(
            namespace="aqp-local",
            name="aqp-api-abc",
            phase="Running",
            labels={"app": "aqp-api"},
        )
    )
    assert payload["name"] == "aqp-api-abc"
    assert payload["labels"]["app"] == "aqp-api"


def test_resolve_pod_name_for_logs_prefers_label_match():
    from aqp.api.routes.control_plane import _resolve_pod_name_for_logs

    class _Adapter:
        def list_pods(self, *, namespace: str, label_selector: str | None = None):
            if label_selector:
                return [SimpleNamespace(name="aqp-api-6c55f8c8f6-abcde")]
            return []

    pod_name = _resolve_pod_name_for_logs(
        adapter=_Adapter(),
        namespace="aqp-local",
        service="aqp-api",
    )
    assert pod_name.startswith("aqp-api-")


def test_resolve_pod_name_for_logs_falls_back_to_service_name():
    from aqp.api.routes.control_plane import _resolve_pod_name_for_logs

    class _Adapter:
        def list_pods(self, *, namespace: str, label_selector: str | None = None):
            return []

    pod_name = _resolve_pod_name_for_logs(
        adapter=_Adapter(),
        namespace="aqp-local",
        service="aqp-api",
    )
    assert pod_name == "aqp-api"


def test_adapter_for_target_local_prefers_in_cluster(monkeypatch):
    from aqp.api.routes import control_plane

    class _InCluster:
        def is_available(self) -> bool:
            return True

    class _Compose:
        def is_available(self) -> bool:
            return True

    monkeypatch.setattr("aqp.kubernetes.adapters.in_cluster.InClusterAdapter", _InCluster)
    monkeypatch.setattr(
        "aqp.kubernetes.adapters.local_compose.LocalComposeAdapter", _Compose
    )

    adapter = control_plane._adapter_for_target("local")
    assert isinstance(adapter, _InCluster)


def test_enqueue_target_returns_503_when_broker_unavailable(monkeypatch):
    from aqp.api.routes.control_plane import _enqueue_target
    from aqp.tasks import terraform_tasks as tt

    def _boom(*, kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(tt.run_local_stack, "apply_async", _boom)

    with pytest.raises(HTTPException) as exc_info:
        _enqueue_target(target="local", action="up")
    assert exc_info.value.status_code == 503
    assert "Celery broker and worker" in str(exc_info.value.detail)

