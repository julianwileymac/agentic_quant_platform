"""HTTP audit sink — pushes ``WorkloadRun`` rows back to the monolith ledger.

Phase 0.4 of the control-plane maturation. The CP-native runtimes
(WorkloadRuntime, TerraformRuntime) need an audit trail in the
monolith's Postgres ``workload_runs`` + ``terraform_runs`` tables so
the existing `aqp_client` operator pages keep working without
shadow-state. This sink:

- Sits behind the :class:`aqp_platform_core.runtime.workload.AuditSink`
  protocol so it plugs into :class:`WorkloadRuntime.set_audit_sink`.
- POSTs every row to the configured monolith URL with a fresh M2M
  bearer minted via :class:`M2MTokenBroker` (Entra-primary).
- Degrades to JSONL-only on transport / credential failure (the
  runtime contract forbids audit-side raises).

The matching monolith ingest endpoint (``/_internal/audit/workload-runs``)
mirrors the shape ``aqp.persistence.models_workloads.WorkloadRun``
ORM expects. The first AQP-side PR after this one wires the
ingest route to ``PostgresWorkloadAuditSink``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import httpx

from aqp_platform_core.auth.m2m import M2MTokenBroker
from aqp_platform_core.credentials.protocol import (
    Credential,
    CredentialKey,
    PRIORITY_ENV,
    SecretStore,
)
from aqp_platform_core.models.workloads import WorkloadRun
from aqp_platform_core.runtime.workload import LoggingAuditSink

logger = logging.getLogger(__name__)


class HttpAuditSink(LoggingAuditSink):
    """Posts ``WorkloadRun`` rows to the monolith via authenticated HTTP.

    Inherits from :class:`LoggingAuditSink` so the structured log
    line still goes out even when the HTTP transport is down.
    """

    def __init__(
        self,
        *,
        url: str,
        broker: M2MTokenBroker,
        audience: str,
        timeout_seconds: float = 5.0,
        scopes: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._url = url
        self._broker = broker
        self._audience = audience
        self._scopes = scopes
        self._timeout = timeout_seconds
        self._client = httpx.Client(timeout=timeout_seconds)
        self._lock = threading.Lock()

    def start_run(self, run: WorkloadRun) -> None:  # noqa: D401
        super().start_run(run)
        self._post(run, phase="start")

    def finish_run(self, run: WorkloadRun) -> None:  # noqa: D401
        super().finish_run(run)
        self._post(run, phase="finish")

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass

    def _bearer(self) -> str | None:
        try:
            grant = _run_in_loop(
                self._broker.acquire(
                    audience=self._audience,
                    scopes=self._scopes,
                )
            )
            return grant.access_token
        except Exception:  # noqa: BLE001
            logger.warning(
                "HttpAuditSink could not mint bearer for %s; row will not be posted",
                self._audience,
                exc_info=True,
            )
            return None

    def _post(self, run: WorkloadRun, *, phase: str) -> None:
        body = run.model_dump(mode="json")
        body["phase"] = phase
        bearer = self._bearer()
        headers = {"Content-Type": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            with self._lock:
                response = self._client.post(self._url, json=body, headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "HttpAuditSink POST %s phase=%s -> HTTP %s body=%s",
                    self._url,
                    phase,
                    response.status_code,
                    response.text[:512],
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "HttpAuditSink POST %s phase=%s failed: %s",
                self._url,
                phase,
                exc,
            )


def _run_in_loop(coro: Any) -> Any:
    """Run ``coro`` either in a fresh loop or by scheduling on the active loop.

    Audit-sink calls are synchronous (the protocol does not return
    awaitables) but the broker is async. We must respect both modes.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # Submit to the loop and wait for the result without blocking.
        # Audit calls happen on the runtime worker thread; the loop
        # belongs to the FastAPI app. We use run_coroutine_threadsafe.
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=10.0)
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# CredentialResolver helpers — load M2M creds from env at boot.
# ---------------------------------------------------------------------------


class EnvSecretStore(SecretStore):
    """Minimal env-var SecretStore used by the CP M2M broker bootstrap.

    Reads ``AQP_CP_M2M_<SERVICE>_<PURPOSE>_<FIELD>`` env vars. For
    example, with ``service='aqp-cp-to-monolith'`` and
    ``purpose='client_credentials'``:

    - ``AQP_CP_M2M_AQP_CP_TO_MONOLITH_CLIENT_CREDENTIALS_CLIENT_ID``
    - ``AQP_CP_M2M_AQP_CP_TO_MONOLITH_CLIENT_CREDENTIALS_CLIENT_SECRET``

    Hyphens in the service / purpose are normalised to underscores
    before the env var lookup. The AQP-side credential resolver
    chain wires richer stores (Vault, AWS SM, etc.) ahead of this one.
    """

    store_kind = "cp_env"
    store_priority = PRIORITY_ENV

    def __init__(self, env: dict[str, str]) -> None:
        self._env = dict(env)

    def get(self, key: CredentialKey) -> Credential | None:
        prefix = self._key_prefix(key)
        client_id = self._env.get(f"{prefix}_CLIENT_ID")
        client_secret = self._env.get(f"{prefix}_CLIENT_SECRET")
        if not client_id and not client_secret:
            return None
        fields: dict[str, str] = {}
        if client_id:
            fields["client_id"] = client_id
        if client_secret:
            fields["client_secret"] = client_secret
        if not fields:
            return None
        return Credential(fields=fields, source=self.store_kind)

    @staticmethod
    def _key_prefix(key: CredentialKey) -> str:
        service = key.service.replace("-", "_").upper()
        purpose = key.purpose.replace("-", "_").upper()
        return f"AQP_CP_M2M_{service}_{purpose}"


__all__ = [
    "EnvSecretStore",
    "HttpAuditSink",
]
