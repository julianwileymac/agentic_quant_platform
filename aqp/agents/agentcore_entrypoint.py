"""Bedrock AgentCore Runtime HTTP entrypoint.

This module is the ``CMD`` in ``aqp_platform/build/docker/aqp-agent/Dockerfile``.
AgentCore Runtime invokes containers over HTTP (not stdin) on two
contract endpoints:

- ``GET /ping`` — must return 200 within the runtime's liveness budget.
  AgentCore polls this on cold-start + during long-lived sessions to
  decide whether to keep the container warm.
- ``POST /invocations`` — receives the agent payload as a JSON body
  (the same shape the stdin shim used to read). The response body MUST
  be JSON (or NDJSON for streaming responses).

The body schema matches the AgentCore Runtime invocation envelope:

.. code-block:: json

    {
      "spec_name": "alpha_research_agent",
      "inputs":    {"prompt": "Summarise the latest 10-K..."},
      "session_id": "AGENTCORE-..." (optional),
      "run_id":     "AGENTCORE-...-run-..." (optional)
    }

The response:

.. code-block:: json

    {
      "run_id":     "uuid",
      "spec_name":  "alpha_research_agent",
      "status":     "completed" | "error" | "rejected",
      "output":     {...},
      "cost_usd":   0.012,
      "error":      null
    }

The server binds to ``0.0.0.0:8080`` by default (AgentCore Runtime's
documented port). Override via ``AQP_AGENTCORE_PORT`` for local dev.

Per AGENTS rule 12 every agent invocation routes through
:class:`AgentRuntime`; no direct ``router_complete`` shortcuts. Per
AGENTS rule 22 every tool read goes through DataMCP (the agent's
spec already declares its allowed tools).

The management-engine credential-safety rule applies here too: no
request / response payload is logged at INFO. Only summary metadata
(run_id, spec_name, status, duration_ms, cost_usd) is structured-logged.
"""
from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App factory — built lazily so test imports don't require FastAPI.
# ---------------------------------------------------------------------------


def create_app():  # type: ignore[no-untyped-def]
    """Build the FastAPI app that AgentCore Runtime invokes.

    Imports FastAPI lazily so unit tests that only want to exercise
    the invocation handler can skip the dependency.
    """
    from fastapi import FastAPI, HTTPException, Request

    app = FastAPI(
        title="AQP AgentCore Runtime",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/ping", include_in_schema=False)
    async def ping() -> dict[str, str]:
        """AgentCore Runtime liveness probe."""
        return {"status": "ok"}

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        """Alias for ``/ping`` — some operator dashboards hit /health."""
        return {"status": "ok"}

    @app.post("/invocations")
    async def invocations(request: Request) -> dict[str, Any]:
        try:
            envelope = await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="envelope must be JSON")
        if not isinstance(envelope, dict):
            raise HTTPException(status_code=400, detail="envelope must be a JSON object")
        return _handle_envelope(envelope)

    return app


# ---------------------------------------------------------------------------
# Invocation handler — the actual AgentRuntime dispatch.
# ---------------------------------------------------------------------------


def _handle_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one AgentCore envelope through :class:`AgentRuntime`.

    Returns the wire-format response dict; never raises (errors are
    captured into ``status='error'`` + ``error`` fields so the
    AgentCore Runtime still gets a 200 with diagnostics).
    """
    spec_name = str(envelope.get("spec_name") or "").strip()
    inputs = envelope.get("inputs") or {}
    session_id = envelope.get("session_id")
    run_id = envelope.get("run_id") or str(uuid.uuid4())

    started_at = time.monotonic()

    if not spec_name:
        return _error_response(
            run_id=run_id,
            spec_name="",
            error="envelope.spec_name missing",
            started_at=started_at,
        )

    try:
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime
    except Exception as exc:  # noqa: BLE001
        return _error_response(
            run_id=run_id,
            spec_name=spec_name,
            error=f"AgentRuntime unavailable: {exc}",
            started_at=started_at,
        )

    try:
        spec = get_agent_spec(spec_name)
    except Exception as exc:  # noqa: BLE001
        return _error_response(
            run_id=run_id,
            spec_name=spec_name,
            error=f"unknown AgentSpec: {exc}",
            started_at=started_at,
        )

    runtime = AgentRuntime(
        spec=spec,
        run_id=run_id,
        session_id=session_id,
    )
    try:
        result = runtime.run(inputs)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "AgentRuntime crashed run_id=%s spec=%s", run_id, spec_name
        )
        return _error_response(
            run_id=run_id,
            spec_name=spec_name,
            error=f"runtime crash: {exc}",
            started_at=started_at,
        )

    duration_ms = (time.monotonic() - started_at) * 1000.0
    logger.info(
        "agentcore.invocation run_id=%s spec=%s status=%s duration_ms=%.0f cost_usd=%.4f",
        result.run_id,
        result.spec_name,
        result.status,
        duration_ms,
        float(result.cost_usd or 0.0),
    )
    return {
        "run_id": result.run_id,
        "spec_name": result.spec_name,
        "status": result.status,
        "output": result.output,
        "cost_usd": float(result.cost_usd or 0.0),
        "n_calls": int(result.n_calls or 0),
        "n_tool_calls": int(result.n_tool_calls or 0),
        "n_rag_hits": int(result.n_rag_hits or 0),
        "duration_ms": duration_ms,
        "error": result.error,
    }


def _error_response(
    *,
    run_id: str,
    spec_name: str,
    error: str,
    started_at: float,
) -> dict[str, Any]:
    duration_ms = (time.monotonic() - started_at) * 1000.0
    return {
        "run_id": run_id,
        "spec_name": spec_name,
        "status": "error",
        "output": {},
        "cost_usd": 0.0,
        "n_calls": 0,
        "n_tool_calls": 0,
        "n_rag_hits": 0,
        "duration_ms": duration_ms,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:  # pragma: no cover - container entrypoint
    """Boot the uvicorn server bound to AgentCore Runtime's contract port."""
    port_raw = os.environ.get("AQP_AGENTCORE_PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError:
        port = 8080

    logging.basicConfig(
        level=os.environ.get("AQP_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        import uvicorn
    except ImportError:
        logger.error(
            "uvicorn not installed; install aqp[auth,otel,cli] in the agent image"
        )
        return 3

    app = create_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=os.environ.get("AQP_AGENTCORE_LOG_LEVEL", "info"),
        access_log=os.environ.get("AQP_AGENTCORE_ACCESS_LOG", "false").lower()
        in ("1", "true", "yes"),
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - container entrypoint
    sys.exit(main())


__all__ = ["create_app", "main"]
