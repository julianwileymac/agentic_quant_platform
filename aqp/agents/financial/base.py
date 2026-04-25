"""Shared plumbing for FinRobot-style role packs."""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from aqp.config import settings
from aqp.llm.ollama_client import complete

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extractor — strips fences, falls back to first brace."""
    if not text:
        return {}
    s = text.strip()
    m = _JSON_FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        try:
            return json.loads(s.replace("'", '"'))
        except json.JSONDecodeError:
            return {}


@dataclass
class FinancialReport:
    """Structured output every role pack returns."""

    title: str
    as_of: str
    payload: dict[str, Any] = field(default_factory=dict)
    sections: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "title": self.title,
                "as_of": self.as_of,
                "payload": self.payload,
                "sections": self.sections,
                "usage": self.usage,
            },
            default=str,
            indent=2,
        )


class BaseFinancialCrew(ABC):
    """Common kwargs + LLM call helper shared by every role pack."""

    name: str = "financial-crew"

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        tier: str | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.tier = tier or settings.finrobot_default_tier

    def _call(
        self,
        system: str,
        user: str,
        *,
        tier: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        result = complete(
            tier=tier or self.tier,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            provider=self.provider,
            model=self.model,
            temperature=temperature,
        )
        return {
            "content": result.content,
            "model": result.model,
            "provider": result.provider,
            "cost_usd": float(result.cost_usd),
            "prompt_tokens": int(result.prompt_tokens),
            "completion_tokens": int(result.completion_tokens),
            "payload": extract_json(result.content),
        }

    def _usage(self, calls: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "calls": len(calls),
            "prompt_tokens": sum(c.get("prompt_tokens", 0) for c in calls),
            "completion_tokens": sum(c.get("completion_tokens", 0) for c in calls),
            "cost_usd": sum(c.get("cost_usd", 0.0) for c in calls),
            "providers": sorted({c.get("provider", "") for c in calls}),
            "models": sorted({c.get("model", "") for c in calls}),
        }

    @abstractmethod
    def run(self, **kwargs: Any) -> FinancialReport:
        """Execute the crew and return a :class:`FinancialReport`."""


__all__ = ["BaseFinancialCrew", "FinancialReport", "extract_json"]
