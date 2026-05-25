"""MLRule ABC + metaclass-driven registry + rule packs.

Mirrors the RL :class:`RLComponent` metaclass pattern: every concrete
:class:`MLRule` subclass auto-registers under its ``rule_name`` and
``rule_tags`` so authoring a new safety check is one class definition.

Rule packs are named bundles loaded from YAML at
``aqp_models/configs/rules/<name>.yaml`` or constructed in code via
:meth:`RuleRegistry.pack`.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuleVerdict:
    """Outcome of one :meth:`MLRule.evaluate` call."""

    allowed: bool
    reason: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


_RULE_REGISTRY: dict[str, type["MLRule"]] = {}
_RULE_PACKS: dict[str, list[str]] = {}
_REGISTRY_LOCK = threading.RLock()


class MLRuleMeta(type(ABC)):
    """Auto-register concrete ``MLRule`` subclasses by ``rule_name``."""

    def __init__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        rule_name = namespace.get("rule_name") or getattr(cls, "rule_name", "")
        if rule_name and not _is_abstract(cls):
            with _REGISTRY_LOCK:
                _RULE_REGISTRY[rule_name] = cls


def _is_abstract(cls: Any) -> bool:
    return bool(getattr(cls, "__abstractmethods__", set()))


class MLRule(ABC, metaclass=MLRuleMeta):
    """Abstract base for every inference-time OOD / safety rule."""

    rule_name: ClassVar[str] = ""
    rule_tags: ClassVar[tuple[str, ...]] = ()
    severity: ClassVar[str] = "info"  # info | warn | block

    @property
    def name(self) -> str:
        return self.rule_name

    @abstractmethod
    def evaluate(
        self,
        *,
        payload: dict[str, Any],
        step: Any | None = None,
        ctx: Any | None = None,
    ) -> RuleVerdict:
        """Return a :class:`RuleVerdict` describing the rule's decision."""


class RuleRegistry:
    """Registry + pack loader for :class:`MLRule` subclasses."""

    @staticmethod
    def pack(name: str, rule_names: list[str]) -> None:
        with _REGISTRY_LOCK:
            _RULE_PACKS[name] = list(rule_names)

    @staticmethod
    def list_rules() -> list[str]:
        with _REGISTRY_LOCK:
            return sorted(_RULE_REGISTRY.keys())

    @staticmethod
    def list_packs() -> dict[str, list[str]]:
        with _REGISTRY_LOCK:
            return {k: list(v) for k, v in _RULE_PACKS.items()}

    @staticmethod
    def load_pack(name: str) -> list[MLRule]:
        # Try YAML first (lets operators ship packs without code changes).
        from_yaml = _load_pack_from_yaml(name)
        if from_yaml:
            return [_resolve_rule(entry) for entry in from_yaml]

        with _REGISTRY_LOCK:
            members = _RULE_PACKS.get(name)
        if members is None:
            # Fall back to built-in defaults.
            members = _BUILTIN_PACKS.get(name, [])
        return [_resolve_rule(entry) for entry in members]


def _resolve_rule(entry: Any) -> MLRule:
    if isinstance(entry, MLRule):
        return entry
    if isinstance(entry, str):
        with _REGISTRY_LOCK:
            cls = _RULE_REGISTRY.get(entry)
        if cls is None:
            raise KeyError(
                f"Unknown ML rule {entry!r}; registered: {sorted(_RULE_REGISTRY)}"
            )
        return cls()
    if isinstance(entry, dict):
        rule_name = entry.get("rule_name") or entry.get("name")
        if not rule_name:
            raise ValueError("rule pack entry missing ``rule_name``")
        with _REGISTRY_LOCK:
            cls = _RULE_REGISTRY.get(rule_name)
        if cls is None:
            raise KeyError(
                f"Unknown ML rule {rule_name!r}; registered: {sorted(_RULE_REGISTRY)}"
            )
        kwargs = {k: v for k, v in entry.items() if k not in {"rule_name", "name"}}
        return cls(**kwargs)
    raise TypeError(f"unsupported rule pack entry {entry!r}")


def _load_pack_from_yaml(name: str) -> list[Any] | None:
    base = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "rules"
    candidate = base / f"{name}.yaml"
    if not candidate.exists():
        return None
    try:
        import yaml

        data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        logger.debug("failed to load rule pack %s", candidate, exc_info=True)
        return None
    rules = data.get("rules") or []
    return list(rules)


# ---------------------------------------------------------------------------
# Built-in packs — used when no YAML / code pack is registered.
# ---------------------------------------------------------------------------


_BUILTIN_PACKS: dict[str, list[Any]] = {
    "ood_default": [
        {"rule_name": "ood.zscore", "threshold": None},
        {"rule_name": "ood.range", "min_value": None, "max_value": None},
        {"rule_name": "ood.tensor_shape"},
    ],
    "strict": [
        {"rule_name": "ood.zscore", "threshold": 2.5},
        {"rule_name": "ood.range"},
        {"rule_name": "ood.tensor_shape"},
        {"rule_name": "circuit_breaker", "max_failures": 3, "window_seconds": 60},
    ],
    "permissive": [],
}


__all__ = [
    "MLRule",
    "MLRuleMeta",
    "RuleRegistry",
    "RuleVerdict",
]
