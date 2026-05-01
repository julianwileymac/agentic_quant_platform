from __future__ import annotations

from types import SimpleNamespace

from aqp.tasks import finops_tasks


def _pod(name: str, labels: dict[str, str] | None = None):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            namespace="default",
            name=name,
            labels=labels or {},
        )
    )


def test_finops_scan_pods_reports_missing_labels() -> None:
    api = SimpleNamespace(
        list_pod_for_all_namespaces=lambda timeout_seconds=30: SimpleNamespace(
            items=[
                _pod(
                    "tagged",
                    {
                        "project": "aqp-default",
                        "cost_center": "quant-research-01",
                        "owner": "system-orchestrator",
                        "data_classification": "proprietary-alpha",
                    },
                ),
                _pod("untagged", {"project": "aqp-default"}),
            ]
        )
    )

    untagged = finops_tasks._scan_pods(api)

    assert len(untagged) == 1
    assert untagged[0]["name"] == "untagged"
    assert set(untagged[0]["missing"]) == {
        "cost_center",
        "owner",
        "data_classification",
    }


def test_finops_audit_skips_without_kubernetes_client(monkeypatch) -> None:
    emitted: list[tuple[str, str]] = []

    monkeypatch.setattr(finops_tasks, "_load_kube_clients", lambda: None)
    monkeypatch.setattr(
        finops_tasks,
        "emit",
        lambda task_id, stage, message, **extra: emitted.append((stage, message)),
    )
    monkeypatch.setattr(
        finops_tasks,
        "emit_done",
        lambda task_id, result, **extra: emitted.append(("done", "Task complete")),
    )
    monkeypatch.setattr(
        finops_tasks,
        "emit_error",
        lambda task_id, error, **extra: emitted.append(("error", error)),
    )

    async_result = finops_tasks.audit.apply(args=("pods",))
    result = async_result.result

    assert async_result.status == "SUCCESS"
    assert result["skipped"] is True
    assert result["untagged_count"] == 0
    assert ("done", "Task complete") in emitted


def test_finops_header_helper_includes_required_keys() -> None:
    from aqp.config import settings

    labels = settings.finops_labels(strategy_id="momentum_v1")

    assert labels["project"]
    assert labels["cost_center"]
    assert labels["owner"]
    assert labels["data_classification"]
    assert labels["strategy_id"] == "momentum_v1"
