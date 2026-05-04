"""Tests for the ProducerSupervisor lifecycle ops (no real cluster).

The supervisor's kubernetes path goes through
:class:`aqp.services.cluster_mgmt_client.ClusterMgmtClient`, which is
trivial to monkey-patch. The local-subprocess path uses ``subprocess.Popen``;
we stub it with a fake that records arguments.
"""
from __future__ import annotations

from typing import Any


def _ensure_models() -> None:
    # Force ORM registration before the in_memory_db fixture creates tables.
    from aqp.persistence import MarketDataProducerRow  # noqa: F401


def test_seed_catalog_idempotent(in_memory_db, monkeypatch) -> None:
    _ensure_models()
    from aqp.persistence import MarketDataProducerRow
    from aqp.persistence.db import get_session
    from aqp.streaming.producers import ProducerSupervisor

    supervisor = ProducerSupervisor()
    with get_session() as session:
        added = supervisor.seed_catalog(session)
        assert added > 0
    supervisor._catalog_seeded = False  # force re-run
    with get_session() as session:
        added2 = supervisor.seed_catalog(session)
        assert added2 == 0
        assert session.query(MarketDataProducerRow).count() >= 5


def test_scale_alphavantage_via_proxy(in_memory_db, monkeypatch) -> None:
    _ensure_models()
    from aqp.persistence.db import get_session
    from aqp.streaming.producers import ProducerSupervisor

    captured: dict[str, Any] = {}

    class _FakeClient:
        def alphavantage_stream(self, *, enable: bool, replicas: int = 1) -> dict[str, Any]:
            captured["enable"] = enable
            captured["replicas"] = replicas
            return {"desired_replicas": replicas if enable else 0, "ready": True}

        def k8s_scale_deployment(self, **kwargs: Any) -> dict[str, Any]:
            captured["k8s"] = kwargs
            return {"desired_replicas": kwargs.get("replicas", 0)}

        def alphavantage_health(self) -> dict[str, Any]:
            return {"ok": True}

    import aqp.streaming.producers.supervisor as sup_mod

    monkeypatch.setattr(sup_mod, "get_cluster_mgmt_client", lambda: _FakeClient())

    supervisor = ProducerSupervisor()
    with get_session() as session:
        supervisor.seed_catalog(session)
    with get_session() as session:
        result = supervisor.start(session, "alphavantage", replicas=2)
        assert captured["enable"] is True
        assert captured["replicas"] == 2
        assert result["last_status"] in {"running", "stopped"}


def test_local_runtime_subprocess(in_memory_db, monkeypatch) -> None:
    _ensure_models()
    from aqp.persistence import MarketDataProducerRow
    from aqp.persistence.db import get_session
    from aqp.streaming.producers import ProducerSupervisor

    class _FakeProc:
        pid = 4242
        returncode = None

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            pass

    import aqp.streaming.producers.supervisor as sup_mod

    monkeypatch.setattr(sup_mod.subprocess, "Popen", lambda *a, **kw: _FakeProc())

    supervisor = ProducerSupervisor()
    with get_session() as session:
        row = MarketDataProducerRow(
            name="local-ibkr",
            kind="ibkr",
            runtime="local",
            display_name="Local IBKR",
            topics=["market.bar.v1"],
            desired_replicas=1,
        )
        session.add(row)
        session.commit()
    with get_session() as session:
        out = supervisor.start(session, "local-ibkr")
        assert out["last_status"] == "running"
    with get_session() as session:
        out = supervisor.stop(session, "local-ibkr")
        assert out["last_status"] == "stopped"
