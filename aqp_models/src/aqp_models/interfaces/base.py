"""Shared base class + metadata for the agent-facing ML interfaces.

Every interface here is a thin, stable wrapper around a concrete
:class:`aqp_models.base.Model` (or any callable with a ``predict``).
The wrapper exposes a domain-specific contract (``predict`` / ``forecast``
/ ``classify`` / ``segment`` / ``analyze``) so agentic code does not
need to know which model framework backs the call.

The interfaces deliberately do NOT mutate ``BaseModel`` or any concrete
model class — they wrap by composition. This keeps the strangler
migration zero-risk: existing call sites that drive ``Model.predict``
directly continue to work, and the wrappers are additive.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal

logger = logging.getLogger(__name__)


InterfaceKind = Literal[
    "predictor",
    "forecaster",
    "classifier",
    "segmenter",
    "analyzer",
]


@dataclass(slots=True)
class InterfaceMetadata:
    """Provenance + execution metadata returned by every interface call.

    Lets agents reason about freshness, latency, and origin without
    parsing free text. Mirrors the shape of
    :class:`aqp.data.mcp.base.MCPToolResult.metadata`.
    """

    interface_kind: InterfaceKind
    alias: str
    model_class: str
    elapsed_ms: float = 0.0
    invoked_at: datetime = field(default_factory=datetime.utcnow)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "interface_kind": str(self.interface_kind),
            "alias": self.alias,
            "model_class": self.model_class,
            "elapsed_ms": float(self.elapsed_ms),
            "invoked_at": self.invoked_at.isoformat(),
            "extras": dict(self.extras),
        }


class PolymorphicInterface(ABC):
    """Root ABC for every agent-facing ML interface wrapper.

    Subclasses declare:

    - :attr:`interface_kind` — one of the five canonical kinds.
    - :attr:`alias` — short name surfaced in the registry / MCP catalog.

    They are instantiated by composition::

        wrapper = Predictor(model=lgb_model, alias="lgb_returns_1d")
        result = wrapper.predict(features)
    """

    interface_kind: ClassVar[InterfaceKind] = "predictor"
    alias: ClassVar[str] = ""

    def __init__(self, *, model: Any, alias: str | None = None) -> None:
        if model is None:
            raise ValueError("PolymorphicInterface requires a non-None model")
        self.model = model
        self._alias = alias or self.alias or model.__class__.__name__
        self._invocations = 0

    # ------------------------------------------------------------------
    # Public — discovery + introspection
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._alias

    @property
    def model_class_name(self) -> str:
        return self.model.__class__.__name__

    def describe(self) -> dict[str, Any]:
        """Return a JSON descriptor for the catalog / MCP discovery."""
        return {
            "interface_kind": str(self.interface_kind),
            "alias": self._alias,
            "model_class": self.model_class_name,
            "supports_finetune": hasattr(self.model, "finetune"),
            "supports_save_load": hasattr(self.model, "to_pickle"),
            "invocations": self._invocations,
        }

    # ------------------------------------------------------------------
    # Internal helpers subclasses use
    # ------------------------------------------------------------------

    def _build_metadata(
        self,
        *,
        started: datetime,
        extras: dict[str, Any] | None = None,
    ) -> InterfaceMetadata:
        self._invocations += 1
        elapsed_ms = (datetime.utcnow() - started).total_seconds() * 1000.0
        return InterfaceMetadata(
            interface_kind=self.interface_kind,
            alias=self._alias,
            model_class=self.model_class_name,
            elapsed_ms=round(elapsed_ms, 3),
            extras=dict(extras or {}),
        )

    def _delegate_predict(self, *args: Any, **kwargs: Any) -> Any:
        """Call the underlying model's ``predict`` / ``__call__``.

        Subclasses use this so a single ``Model`` can power any of the
        five wrappers — the wrapper-specific contract (e.g.
        :meth:`Forecaster.forecast`) is built on top of this primitive.
        """
        if hasattr(self.model, "predict"):
            return self.model.predict(*args, **kwargs)
        if callable(self.model):
            return self.model(*args, **kwargs)
        raise TypeError(
            f"Underlying model {self.model_class_name!r} is not callable"
            " and does not expose ``predict``."
        )

    @abstractmethod
    def supports(self, model: Any) -> bool:
        """Return ``True`` when ``model`` can back this interface.

        Lets the auto-wrap helper in :mod:`aqp_models.interfaces.wrap`
        pick the right interface for an arbitrary model object.
        Subclasses override with their kind-specific introspection.
        """


__all__ = [
    "InterfaceKind",
    "InterfaceMetadata",
    "PolymorphicInterface",
]
