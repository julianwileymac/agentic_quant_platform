"""High-level :class:`SandboxRuntime` that ties the pieces together.

Routes / Celery tasks construct one :class:`SandboxRuntime` per
session. The runtime owns the temp folder, the Redis namespace, and
the env resolver. Teardown is idempotent.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from aqp.dagster.sandbox.airbyte_bridge import airbyte_connection_to_component
from aqp.dagster.sandbox.env_resolver import (
    SandboxEnvResolver,
    enter_sandbox_env,
    with_sandbox_overrides,
)
from aqp.dagster.sandbox.executor import SandboxEvent, SandboxExecutor
from aqp.dagster.sandbox.redis_isolation import SandboxRedisNamespace, make_namespace

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SandboxSession:
    """In-memory session record."""

    id: str
    folder: Path
    owner: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    components: dict[str, str] = field(default_factory=dict)
    asset_keys: list[list[str]] = field(default_factory=list)
    last_run_id: str | None = None
    log_summary: list[dict[str, Any]] = field(default_factory=list)
    status: str = "open"

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner": self.owner,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "components": list(self.components),
            "asset_keys": list(self.asset_keys),
            "last_run_id": self.last_run_id,
            "log_summary": list(self.log_summary[-50:]),
            "status": self.status,
        }


class SandboxRuntime:
    """Single sanctioned executor for sandbox sessions."""

    _registry: dict[str, "SandboxRuntime"] = {}

    def __init__(
        self,
        *,
        owner: str | None = None,
        workspace_id: str | None = None,
        project_id: str | None = None,
        ttl_minutes: int = 60,
    ) -> None:
        session_id = str(uuid.uuid4())
        folder = Path(tempfile.mkdtemp(prefix=f"aqp_sandbox_{session_id}_"))
        self.session = SandboxSession(
            id=session_id,
            folder=folder,
            owner=owner,
            workspace_id=workspace_id,
            project_id=project_id,
            expires_at=datetime.utcnow() + timedelta(minutes=int(ttl_minutes)),
        )
        self.namespace: SandboxRedisNamespace = make_namespace(session_id)
        self.env: SandboxEnvResolver = with_sandbox_overrides(session_id)
        self.executor = SandboxExecutor(folder)
        SandboxRuntime._registry[session_id] = self

    # ----------------------------------------------------------- factories
    @classmethod
    def create_session(
        cls,
        *,
        owner: str | None = None,
        workspace_id: str | None = None,
        project_id: str | None = None,
        ttl_minutes: int = 60,
    ) -> "SandboxRuntime":
        return cls(
            owner=owner,
            workspace_id=workspace_id,
            project_id=project_id,
            ttl_minutes=ttl_minutes,
        )

    @classmethod
    def get(cls, session_id: str) -> "SandboxRuntime | None":
        return cls._registry.get(session_id)

    @classmethod
    def list_sessions(cls) -> list[SandboxSession]:
        return [r.session for r in cls._registry.values()]

    @classmethod
    def janitor(cls) -> list[str]:
        """Tear down expired sessions; return the ids dropped."""
        now = datetime.utcnow()
        dropped: list[str] = []
        for session_id, runtime in list(cls._registry.items()):
            expires = runtime.session.expires_at
            if expires and now > expires:
                runtime.teardown()
                dropped.append(session_id)
        return dropped

    # ----------------------------------------------------------- session ops
    def write_component(self, name: str, body: str) -> Path:
        if not name.endswith((".yaml", ".yml")):
            name = f"{name}.yaml"
        target = self.session.folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        self.session.components[name] = body
        return target

    def write_airbyte_connection(self, connection: dict[str, Any]) -> Path:
        rendered = airbyte_connection_to_component(connection)
        slug = str(connection.get("name") or "airbyte_connection").replace(" ", "_").lower()
        return self.write_component(f"{slug}.yaml", rendered)

    def load(self) -> dict[str, Any]:
        with enter_sandbox_env(self.env):
            result = self.executor.load()
        keys = result.get("asset_keys") or []
        self.session.asset_keys = [list(k) for k in keys if isinstance(k, (list, tuple))]
        return result

    def stream_execute(self) -> Iterable[SandboxEvent]:
        run_id = str(uuid.uuid4())
        self.session.last_run_id = run_id
        self.session.status = "running"
        try:
            with enter_sandbox_env(self.env):
                for event in self.executor.stream_execute():
                    payload = event.to_json()
                    payload["run_id"] = run_id
                    payload["session_id"] = self.session.id
                    self.session.log_summary.append(payload)
                    yield event
        finally:
            self.session.status = "open"

    def teardown(self) -> dict[str, Any]:
        keys_dropped = 0
        try:
            keys_dropped = self.namespace.teardown()
        except Exception:  # noqa: BLE001
            logger.warning("sandbox %s redis teardown failed", self.session.id, exc_info=True)
        try:
            shutil.rmtree(self.session.folder, ignore_errors=True)
        except Exception:  # noqa: BLE001
            logger.warning("sandbox %s folder cleanup failed", self.session.id, exc_info=True)
        SandboxRuntime._registry.pop(self.session.id, None)
        self.session.status = "closed"
        return {
            "session_id": self.session.id,
            "redis_keys_dropped": keys_dropped,
            "folder_removed": True,
        }


__all__ = ["SandboxRuntime", "SandboxSession"]
