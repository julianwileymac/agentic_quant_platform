"""Bedrock AgentCore Runtime entrypoint shim.

This module is the ``CMD`` in ``aqp_platform/build/docker/aqp-agent/Dockerfile``.
AgentCore Runtime invokes the container with the agent payload as a
JSON envelope on stdin (or as an HTTP body when run in HTTP mode); we
parse the envelope, look up the matching :class:`aqp.agents.spec.AgentSpec`
by name, run :meth:`AgentRuntime.run`, and write the result back to
stdout as JSON.

The runtime is deliberately tiny — every interesting line of code
lives in :class:`AgentRuntime`. The shim is just the glue between
AgentCore's invocation contract and the existing spec runtime.

Envelope schema (from AgentCore Runtime):

.. code-block:: json

    {
      "spec_name": "alpha_research_agent",
      "inputs":    {"prompt": "Summarise the latest 10-K..."},
      "session_id": "AGENTCORE-..." (optional)
    }

The shim writes:

.. code-block:: json

    {
      "run_id":  "uuid",
      "status":  "completed" | "error" | "rejected",
      "output":  {...},
      "cost_usd": 0.012,
      "error":   null
    }

Per AGENTS rule 12 every agent invocation routes through
:class:`AgentRuntime`; no direct ``router_complete`` shortcuts. Per
AGENTS rule 22 every tool read goes through DataMCP (the agent's
spec already declares its allowed tools).
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _read_envelope() -> dict[str, Any]:
    """Read the AgentCore invocation envelope from stdin."""
    blob = sys.stdin.read()
    if not blob.strip():
        return {}
    try:
        return json.loads(blob)
    except Exception:  # noqa: BLE001
        logger.warning("AgentCore envelope is not valid JSON; treating as empty")
        return {}


def _write_result(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, default=str))
    sys.stdout.flush()


def main() -> int:
    envelope = _read_envelope()
    spec_name = str(envelope.get("spec_name") or "").strip()
    if not spec_name:
        _write_result(
            {
                "status": "error",
                "error": "envelope.spec_name missing",
                "output": {},
                "cost_usd": 0.0,
            }
        )
        return 2

    inputs = envelope.get("inputs") or {}
    session_id = envelope.get("session_id")
    run_id = envelope.get("run_id")

    try:
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime
    except Exception as exc:  # noqa: BLE001
        _write_result(
            {
                "status": "error",
                "error": f"AgentRuntime unavailable: {exc}",
                "output": {},
                "cost_usd": 0.0,
            }
        )
        return 3

    try:
        spec = get_agent_spec(spec_name)
    except Exception as exc:  # noqa: BLE001
        _write_result(
            {
                "status": "error",
                "error": f"unknown AgentSpec {spec_name!r}: {exc}",
                "output": {},
                "cost_usd": 0.0,
            }
        )
        return 4

    runtime = AgentRuntime(
        spec=spec,
        run_id=run_id,
        session_id=session_id,
    )
    result = runtime.run(inputs)
    _write_result(
        {
            "run_id": result.run_id,
            "spec_name": result.spec_name,
            "status": result.status,
            "output": result.output,
            "cost_usd": float(result.cost_usd or 0.0),
            "error": result.error,
        }
    )
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":  # pragma: no cover - container entrypoint
    sys.exit(main())
