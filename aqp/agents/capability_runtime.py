"""Resolve declarative :class:`AgentCapabilities` into runtime objects.

The runtime is intentionally non-stateful — every method accepts the
capability spec and returns the appropriate object. Where third-party
SDKs are optional (the official ``mcp`` Python SDK), we degrade
gracefully and log instead of raising.

Public API
----------

- :class:`CapabilityRuntime` — orchestrates tool resolution + memory +
  guardrail validation + cost tracking.
- :class:`McpClient` — minimal stdio + HTTP wrapper.
- :exc:`GuardrailViolation` — raised when ``validate_output`` rejects.
"""
from __future__ import annotations

import importlib
import logging
import re
import time
from collections import deque
from typing import Any

from aqp.agents.capabilities import (
    AgentCapabilities,
    GuardrailSpec,
    McpServerSpec,
    MemorySpec,
)

logger = logging.getLogger(__name__)


class GuardrailViolation(ValueError):
    """Raised when an agent output fails guardrail validation."""


# ---------------------------------------------------------------------------
# MCP client
# ---------------------------------------------------------------------------


class McpClient:
    """Minimal MCP client wrapper.

    Tries to use the official ``mcp`` Python SDK if installed, then
    falls back to a no-op ``call(...)`` that returns ``None`` and logs.
    The wrapper stays sync — the heavy crew runtime is sync-only too.
    """

    def __init__(self, spec: McpServerSpec) -> None:
        self.spec = spec
        self._session: Any = None
        self._available = False
        self._tried = False

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        try:  # pragma: no cover — optional dep
            import mcp  # type: ignore[import-not-found]  # noqa: F401

            self._available = True
        except Exception:
            self._available = False
            logger.info(
                "MCP SDK not installed; capabilities for server %s will be no-op",
                self.spec.name,
            )

    def list_tools(self) -> list[dict[str, Any]]:
        self._ensure()
        if not self._available:
            return []
        # Conservative: real implementation would issue an MCP RPC; we
        # return the configured allowlist so the wizard can echo it.
        return [{"name": t} for t in (self.spec.tools or [])]

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        self._ensure()
        if not self._available:
            logger.warning("MCP call %s.%s skipped (SDK missing)", self.spec.name, tool)
            return None
        if self.spec.tools and tool not in self.spec.tools:
            raise PermissionError(
                f"tool {tool!r} not in MCP server {self.spec.name!r} allowlist"
            )
        # The actual MCP RPC would happen here; we keep the surface
        # minimal so callers can pin a stub for tests.
        logger.info("MCP %s.call %s args=%s", self.spec.name, tool, arguments)
        return None


# ---------------------------------------------------------------------------
# Schema resolver
# ---------------------------------------------------------------------------


def _resolve_pydantic_model(qualname: str) -> Any | None:
    if not qualname or "." not in qualname:
        return None
    module_path, cls_name = qualname.rsplit(".", 1)
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name, None)
        if cls is None:
            return None
        from pydantic import BaseModel

        if isinstance(cls, type) and issubclass(cls, BaseModel):
            return cls
    except Exception:
        return None
    return None


def _validate_jsonschema(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    """Light JSON-schema enforcement: ``required`` + ``type`` only.

    We avoid a hard dependency on ``jsonschema``; agents typically need
    "must contain these fields" not full type coercion.
    """
    required = schema.get("required") or []
    for field in required:
        if field not in payload:
            raise GuardrailViolation(f"missing required field: {field!r}")
    properties = schema.get("properties") or {}
    for field, prop in properties.items():
        if field not in payload:
            continue
        wanted = prop.get("type")
        if not wanted:
            continue
        value = payload[field]
        if wanted == "string" and not isinstance(value, str):
            raise GuardrailViolation(f"field {field!r} expected string")
        if wanted == "number" and not isinstance(value, (int, float)):
            raise GuardrailViolation(f"field {field!r} expected number")
        if wanted == "integer" and not isinstance(value, int):
            raise GuardrailViolation(f"field {field!r} expected integer")
        if wanted == "boolean" and not isinstance(value, bool):
            raise GuardrailViolation(f"field {field!r} expected boolean")
        if wanted == "array" and not isinstance(value, list):
            raise GuardrailViolation(f"field {field!r} expected array")
        if wanted == "object" and not isinstance(value, dict):
            raise GuardrailViolation(f"field {field!r} expected object")


def _redact_pii(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]", text)
    text = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "[REDACTED-EMAIL]", text)
    text = re.sub(r"\b\d{16}\b", "[REDACTED-CARD]", text)
    return text


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class CapabilityRuntime:
    """Resolve a :class:`AgentCapabilities` into runtime objects."""

    def __init__(self, capabilities: AgentCapabilities | dict[str, Any] | None) -> None:
        if capabilities is None:
            capabilities = AgentCapabilities()
        elif isinstance(capabilities, dict):
            capabilities = AgentCapabilities(**capabilities)
        self.capabilities: AgentCapabilities = capabilities
        self._tools_cache: list[Any] | None = None
        self._mcp_clients: dict[str, McpClient] | None = None
        self._memory: Any = None
        self._cost_total: float = 0.0
        self._call_count: int = 0
        self._call_log: deque[float] = deque(maxlen=500)

    # ---------------------------------------------------------- Tools --

    def tools(self) -> list[Any]:
        """Return bound CrewAI ``BaseTool`` instances for ``capabilities.tools``."""
        if self._tools_cache is not None:
            return self._tools_cache
        out: list[Any] = []
        if self.capabilities.tools:
            try:
                from aqp.agents.tools import get_tool

                for name in self.capabilities.tools:
                    try:
                        out.append(get_tool(name))
                    except KeyError:
                        logger.warning("CapabilityRuntime: unknown tool %s", name)
            except Exception:
                logger.exception("CapabilityRuntime: tool resolution failed")
        self._tools_cache = out
        return out

    # ---------------------------------------------------------- MCP --

    def mcp_clients(self) -> dict[str, McpClient]:
        if self._mcp_clients is not None:
            return self._mcp_clients
        clients = {spec.name: McpClient(spec) for spec in self.capabilities.mcp_servers}
        self._mcp_clients = clients
        return clients

    # -------------------------------------------------------- Memory --

    def memory(self) -> Any:
        if self._memory is not None:
            return self._memory
        spec: MemorySpec | None = self.capabilities.memory
        if spec is None or spec.disabled():
            return None
        try:
            if spec.kind == "bm25":
                from pathlib import Path

                from aqp.llm.memory import BM25Memory

                self._memory = BM25Memory(
                    role=spec.role,
                    persist_dir=Path(spec.persist_dir) if spec.persist_dir else None,
                )
            elif spec.kind == "hybrid":
                from aqp.llm.memory import HybridMemory

                self._memory = HybridMemory(role=spec.role)
        except Exception:
            logger.exception("CapabilityRuntime: memory bind failed")
            self._memory = None
        return self._memory

    # --------------------------------------------------- Guardrails --

    def validate_output(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate + (optionally) redact a structured agent output.

        Returns the (possibly redacted) payload. Raises
        :class:`GuardrailViolation` when validation fails.
        """
        guards: GuardrailSpec = self.capabilities.effective_guardrails()
        if not isinstance(payload, dict):
            raise GuardrailViolation(
                f"expected dict, got {type(payload).__name__}"
            )
        # Schema validation
        schema = guards.output_schema
        if schema:
            if isinstance(schema, str):
                model_cls = _resolve_pydantic_model(schema)
                if model_cls is not None:
                    try:
                        model_cls(**payload)
                    except Exception as exc:
                        raise GuardrailViolation(
                            f"output failed Pydantic validation against {schema}: {exc}"
                        ) from exc
                else:
                    logger.warning(
                        "CapabilityRuntime: cannot resolve Pydantic schema %s",
                        schema,
                    )
            elif isinstance(schema, dict):
                _validate_jsonschema(payload, schema)
        # Required rationale
        if guards.require_rationale and not str(payload.get("rationale", "")).strip():
            # Some payloads use ``summary`` or ``argument`` — accept those too.
            for fallback in ("summary", "argument", "explanation"):
                if str(payload.get(fallback, "")).strip():
                    break
            else:
                raise GuardrailViolation(
                    "output missing rationale (set require_rationale=False to disable)"
                )
        # Forbidden terms
        if guards.forbidden_terms:
            blob = self._stringify(payload).lower()
            for term in guards.forbidden_terms:
                if term and term in blob:
                    raise GuardrailViolation(f"output contained forbidden term: {term}")
        # PII redaction (in place)
        if guards.pii_redact:
            payload = self._redact(payload)
        # Confidence floor
        if guards.min_confidence is not None:
            conf = float(payload.get("confidence", 0.0) or 0.0)
            if conf < guards.min_confidence:
                raise GuardrailViolation(
                    f"output confidence {conf:.2f} below floor {guards.min_confidence:.2f}"
                )
        return payload

    @staticmethod
    def _stringify(payload: Any) -> str:
        try:
            import json

            return json.dumps(payload, default=str)
        except Exception:
            return str(payload)

    @staticmethod
    def _redact(payload: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, str):
                out[k] = _redact_pii(v)
            elif isinstance(v, dict):
                out[k] = CapabilityRuntime._redact(v)
            elif isinstance(v, list):
                out[k] = [
                    _redact_pii(x) if isinstance(x, str) else x for x in v
                ]
            else:
                out[k] = v
        return out

    # ----------------------------------------------------- Cost / rate --

    def track_call(self, cost_usd: float = 0.0) -> None:
        """Increment counters; raises :class:`GuardrailViolation` over budget / rate."""
        guards: GuardrailSpec = self.capabilities.effective_guardrails()
        self._cost_total += float(cost_usd or 0.0)
        self._call_count += 1
        if self._cost_total > guards.cost_budget_usd:
            raise GuardrailViolation(
                f"cost budget exceeded: {self._cost_total:.4f} > {guards.cost_budget_usd:.4f}"
            )
        now = time.time()
        self._call_log.append(now)
        # Drop calls older than 60 seconds for the rate-limit window.
        cutoff = now - 60.0
        while self._call_log and self._call_log[0] < cutoff:
            self._call_log.popleft()
        if guards.rate_limit_per_minute and len(self._call_log) > guards.rate_limit_per_minute:
            raise GuardrailViolation(
                f"rate limit exceeded: {len(self._call_log)}/min > {guards.rate_limit_per_minute}"
            )
        if self._call_count > self.capabilities.max_calls:
            raise GuardrailViolation(
                f"max_calls exceeded: {self._call_count} > {self.capabilities.max_calls}"
            )

    # ---------------------------------------------------------- Stats --

    def stats(self) -> dict[str, Any]:
        return {
            "cost_usd": round(self._cost_total, 6),
            "n_calls": int(self._call_count),
            "tools": [t.name if hasattr(t, "name") else type(t).__name__ for t in self.tools()],
            "mcp_servers": list(self.mcp_clients().keys()),
            "memory_role": self.capabilities.memory.role
            if (self.capabilities.memory and not self.capabilities.memory.disabled())
            else None,
        }


__all__ = [
    "CapabilityRuntime",
    "GuardrailViolation",
    "McpClient",
]
