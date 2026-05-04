"""ProducerSupervisor — uniform start/stop/scale/status surface.

Backs the ``/streaming/producers`` API. The supervisor mediates
between the persisted :class:`MarketDataProducerRow` catalog and
either the rpi_kubernetes management proxy (for cluster-deployed
producers) or local subprocess execution of ``aqp-stream-ingest``
(for development on a workstation).
"""
from __future__ import annotations

import logging
import shlex
import subprocess
import threading
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from aqp.persistence import MarketDataProducerRow
from aqp.services.cluster_mgmt_client import (
    ClusterMgmtError,
    get_cluster_mgmt_client,
)
from aqp.streaming.producers.catalog import (
    PRODUCER_CATALOG,
    list_producer_specs,
)

logger = logging.getLogger(__name__)


class ProducerError(RuntimeError):
    """Raised when a producer operation fails."""


def _producer_summary(row: MarketDataProducerRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "runtime": row.runtime,
        "display_name": row.display_name,
        "description": row.description,
        "deployment_namespace": row.deployment_namespace,
        "deployment_name": row.deployment_name,
        "image": row.image,
        "topics": list(row.topics or []),
        "config": dict(row.config_json or {}),
        "desired_replicas": int(row.desired_replicas or 0),
        "current_replicas": int(row.current_replicas or 0),
        "last_status": row.last_status,
        "last_status_at": row.last_status_at.isoformat() if row.last_status_at else None,
        "last_error": row.last_error,
        "enabled": bool(row.enabled),
        "tags": list(row.tags or []),
    }


class ProducerSupervisor:
    """Mediates lifecycle ops on a :class:`MarketDataProducerRow`."""

    def __init__(self) -> None:
        self._local_processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()
        self._catalog_seeded = False

    # ------------------------------------------------------------------ helpers
    def _stamp_status(
        self,
        session: Session,
        row: MarketDataProducerRow,
        *,
        status: str,
        replicas: int | None = None,
        error: str | None = None,
    ) -> None:
        row.last_status = status
        row.last_status_at = datetime.utcnow()
        if replicas is not None:
            row.current_replicas = int(replicas)
        if error is not None:
            row.last_error = error
        elif status not in {"error", "failed"}:
            row.last_error = None
        session.add(row)
        session.commit()

    def _is_kubernetes(self, row: MarketDataProducerRow) -> bool:
        return (row.runtime or "").lower() in {"kubernetes", "cluster_proxy"}

    # ------------------------------------------------------------------ catalog
    def seed_catalog(self, session: Session) -> int:
        """Idempotently seed `PRODUCER_CATALOG` rows on first start."""
        if self._catalog_seeded:
            return 0
        added = 0
        for spec in list_producer_specs():
            existing = (
                session.query(MarketDataProducerRow)
                .filter(MarketDataProducerRow.name == spec.name)
                .first()
            )
            if existing is not None:
                continue
            row = MarketDataProducerRow(
                name=spec.name,
                kind=spec.kind,
                runtime=spec.runtime,
                display_name=spec.display_name,
                description=spec.description,
                deployment_namespace=spec.deployment_namespace,
                deployment_name=spec.deployment_name,
                image=spec.image,
                topics=list(spec.topics),
                config_json=dict(spec.config),
                desired_replicas=int(spec.desired_replicas),
                current_replicas=0,
                last_status="seeded",
                last_status_at=datetime.utcnow(),
                enabled=True,
                tags=list(spec.tags),
            )
            session.add(row)
            added += 1
        if added:
            session.commit()
        self._catalog_seeded = True
        return added

    # ------------------------------------------------------------------ CRUD
    def list(self, session: Session) -> list[MarketDataProducerRow]:
        return list(
            session.query(MarketDataProducerRow)
            .order_by(MarketDataProducerRow.name.asc())
            .all()
        )

    def get(self, session: Session, name: str) -> MarketDataProducerRow:
        row = (
            session.query(MarketDataProducerRow)
            .filter(MarketDataProducerRow.name == name)
            .first()
        )
        if row is None:
            raise ProducerError(f"producer {name!r} not found")
        return row

    def create(self, session: Session, **kwargs: Any) -> MarketDataProducerRow:
        existing = (
            session.query(MarketDataProducerRow)
            .filter(MarketDataProducerRow.name == kwargs.get("name"))
            .first()
        )
        if existing is not None:
            raise ProducerError(f"producer {kwargs.get('name')!r} already exists")
        row = MarketDataProducerRow(
            name=kwargs["name"],
            kind=kwargs.get("kind", "custom"),
            runtime=kwargs.get("runtime", "kubernetes"),
            display_name=kwargs.get("display_name") or kwargs["name"],
            description=kwargs.get("description"),
            deployment_namespace=kwargs.get("deployment_namespace"),
            deployment_name=kwargs.get("deployment_name"),
            image=kwargs.get("image"),
            topics=list(kwargs.get("topics") or []),
            config_json=dict(kwargs.get("config") or {}),
            env_overrides=dict(kwargs.get("env_overrides") or {}),
            desired_replicas=int(kwargs.get("desired_replicas", 0)),
            current_replicas=0,
            last_status="created",
            last_status_at=datetime.utcnow(),
            enabled=bool(kwargs.get("enabled", True)),
            tags=list(kwargs.get("tags") or []),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row

    def patch(self, session: Session, name: str, **kwargs: Any) -> MarketDataProducerRow:
        row = self.get(session, name)
        for attr in (
            "display_name",
            "description",
            "deployment_namespace",
            "deployment_name",
            "image",
            "runtime",
            "kind",
        ):
            if attr in kwargs and kwargs[attr] is not None:
                setattr(row, attr, kwargs[attr])
        if "topics" in kwargs and kwargs["topics"] is not None:
            row.topics = list(kwargs["topics"])
        if "config" in kwargs and kwargs["config"] is not None:
            row.config_json = dict(kwargs["config"])
        if "env_overrides" in kwargs and kwargs["env_overrides"] is not None:
            row.env_overrides = dict(kwargs["env_overrides"])
        if "tags" in kwargs and kwargs["tags"] is not None:
            row.tags = list(kwargs["tags"])
        if "enabled" in kwargs and kwargs["enabled"] is not None:
            row.enabled = bool(kwargs["enabled"])
        if "desired_replicas" in kwargs and kwargs["desired_replicas"] is not None:
            row.desired_replicas = int(kwargs["desired_replicas"])
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.commit()
        return row

    def delete(self, session: Session, name: str) -> None:
        row = self.get(session, name)
        session.delete(row)
        session.commit()

    # ------------------------------------------------------------------ lifecycle
    def start(self, session: Session, name: str, *, replicas: int | None = None) -> dict[str, Any]:
        row = self.get(session, name)
        target = int(replicas if replicas is not None else (row.desired_replicas or 1) or 1)
        row.desired_replicas = target
        if self._is_kubernetes(row):
            return self._scale_kubernetes(session, row, target)
        return self._start_local(session, row)

    def stop(self, session: Session, name: str) -> dict[str, Any]:
        row = self.get(session, name)
        row.desired_replicas = 0
        if self._is_kubernetes(row):
            return self._scale_kubernetes(session, row, 0)
        return self._stop_local(session, row)

    def scale(self, session: Session, name: str, replicas: int) -> dict[str, Any]:
        return self.start(session, name, replicas=replicas)

    def restart(self, session: Session, name: str) -> dict[str, Any]:
        row = self.get(session, name)
        target = int(row.desired_replicas or 1) or 1
        if self._is_kubernetes(row):
            self._scale_kubernetes(session, row, 0)
            return self._scale_kubernetes(session, row, target)
        self._stop_local(session, row)
        return self._start_local(session, row)

    def status(self, session: Session, name: str) -> dict[str, Any]:
        row = self.get(session, name)
        details: dict[str, Any] = {}
        if self._is_kubernetes(row):
            try:
                client = get_cluster_mgmt_client()
                if row.kind == "alphavantage":
                    snap = client.alphavantage_health()
                    details = snap or {}
                else:
                    details = {
                        "deployment": f"{row.deployment_namespace}/{row.deployment_name}",
                        "managed_via": "k8s_scale_deployment",
                    }
            except Exception as exc:  # noqa: BLE001
                details = {"error": str(exc)}
        else:
            with self._lock:
                proc = self._local_processes.get(row.name)
                if proc is None or proc.poll() is not None:
                    details = {"running": False}
                else:
                    details = {"running": True, "pid": proc.pid}
        return {
            "name": row.name,
            "current_replicas": int(row.current_replicas or 0),
            "desired_replicas": int(row.desired_replicas or 0),
            "ready": (row.current_replicas or 0) == (row.desired_replicas or 0),
            "message": row.last_status,
            "last_status": row.last_status,
            "last_status_at": row.last_status_at.isoformat() if row.last_status_at else None,
            "details": details,
        }

    def logs(self, session: Session, name: str, *, tail: int = 200) -> dict[str, Any]:
        row = self.get(session, name)
        if self._is_kubernetes(row):
            try:
                client = get_cluster_mgmt_client()
                # Best-effort: the management API exposes /api/deployments/{ns}/{name}/logs in newer revisions.
                response = client._request(  # type: ignore[attr-defined]
                    "GET",
                    f"/deployments/{row.deployment_namespace}/{row.deployment_name}/logs",
                    params={"tail": tail},
                )
                lines: list[str]
                if isinstance(response, dict) and isinstance(response.get("lines"), list):
                    lines = [str(x) for x in response["lines"]][-tail:]
                elif isinstance(response, str):
                    lines = response.splitlines()[-tail:]
                else:
                    lines = []
                return {"name": name, "pod": None, "lines": lines}
            except Exception as exc:  # noqa: BLE001
                return {"name": name, "pod": None, "lines": [f"<unavailable: {exc}>"]}
        # Local: stream tail from subprocess (best-effort)
        with self._lock:
            proc = self._local_processes.get(row.name)
        if proc is None:
            return {"name": name, "pod": None, "lines": ["<no local process>"]}
        return {"name": name, "pod": None, "lines": [f"<local pid {proc.pid}; stream from /proc/.../fd/1>"]}

    # ------------------------------------------------------------------ kubernetes ops
    def _scale_kubernetes(
        self, session: Session, row: MarketDataProducerRow, replicas: int
    ) -> dict[str, Any]:
        client = get_cluster_mgmt_client()
        try:
            if row.kind == "alphavantage":
                snap = client.alphavantage_stream(enable=replicas > 0, replicas=max(1, replicas) if replicas > 0 else 0)
            elif row.deployment_namespace and row.deployment_name:
                snap = client.k8s_scale_deployment(
                    namespace=row.deployment_namespace,
                    name=row.deployment_name,
                    replicas=replicas,
                )
            else:
                raise ProducerError(
                    "kubernetes producer missing deployment_namespace/name"
                )
            current = int(snap.get("desired_replicas", replicas))
            self._stamp_status(session, row, status="running" if replicas > 0 else "stopped", replicas=current)
            return {**self._sanitised_status(row), "details": snap}
        except ClusterMgmtError as exc:
            self._stamp_status(session, row, status="error", error=str(exc))
            raise ProducerError(f"scale failed: {exc}") from exc

    # ------------------------------------------------------------------ local subprocess
    def _start_local(self, session: Session, row: MarketDataProducerRow) -> dict[str, Any]:
        with self._lock:
            existing = self._local_processes.get(row.name)
            if existing and existing.poll() is None:
                self._stamp_status(session, row, status="running", replicas=1)
                return self._sanitised_status(row)
            cmd = "aqp-stream-ingest"
            args = list((row.config_json or {}).get("cli_args") or [])
            full = [cmd, *args]
            try:
                proc = subprocess.Popen(  # noqa: S603 - controlled command
                    full,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            except FileNotFoundError as exc:
                self._stamp_status(session, row, status="error", error=str(exc))
                raise ProducerError(f"failed to launch {shlex.join(full)}: {exc}") from exc
            self._local_processes[row.name] = proc
            self._stamp_status(session, row, status="running", replicas=1)
        return self._sanitised_status(row)

    def _stop_local(self, session: Session, row: MarketDataProducerRow) -> dict[str, Any]:
        with self._lock:
            proc = self._local_processes.pop(row.name, None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                proc.kill()
        self._stamp_status(session, row, status="stopped", replicas=0)
        return self._sanitised_status(row)

    def _sanitised_status(self, row: MarketDataProducerRow) -> dict[str, Any]:
        return {
            "name": row.name,
            "current_replicas": int(row.current_replicas or 0),
            "desired_replicas": int(row.desired_replicas or 0),
            "ready": (row.current_replicas or 0) == (row.desired_replicas or 0),
            "message": row.last_status or "",
            "last_status": row.last_status,
            "last_status_at": row.last_status_at.isoformat() if row.last_status_at else None,
            "details": {},
        }


_singleton: ProducerSupervisor | None = None


def get_supervisor() -> ProducerSupervisor:
    global _singleton
    if _singleton is None:
        _singleton = ProducerSupervisor()
    return _singleton


__all__ = ["ProducerError", "ProducerSupervisor", "get_supervisor", "_producer_summary"]
