"""Convenience helpers that auto-wrap a model in the right interface.

Used by the ``data.ml.*`` MCP tools, the FastAPI ML routes, and the
agentic skill layer so call-sites don't manually pick the interface
class.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp_models.interfaces.analyzer import Analyzer
from aqp_models.interfaces.base import InterfaceKind, PolymorphicInterface
from aqp_models.interfaces.classifier import Classifier
from aqp_models.interfaces.forecaster import Forecaster
from aqp_models.interfaces.predictor import Predictor
from aqp_models.interfaces.segmenter import Segmenter

logger = logging.getLogger(__name__)


_INTERFACE_BY_KIND: dict[InterfaceKind, type[PolymorphicInterface]] = {
    "predictor": Predictor,
    "forecaster": Forecaster,
    "classifier": Classifier,
    "segmenter": Segmenter,
    "analyzer": Analyzer,
}


def wrap_model(
    model: Any,
    *,
    kind: InterfaceKind,
    alias: str | None = None,
    **kwargs: Any,
) -> PolymorphicInterface:
    """Wrap ``model`` in the interface implied by ``kind``.

    Raises :class:`KeyError` when ``kind`` is unknown and
    :class:`TypeError` when the wrapper rejects the model via
    :meth:`PolymorphicInterface.supports`.
    """
    if kind not in _INTERFACE_BY_KIND:
        raise KeyError(
            f"unknown interface kind {kind!r}; known: {sorted(_INTERFACE_BY_KIND)}"
        )
    iface_cls = _INTERFACE_BY_KIND[kind]
    wrapper = iface_cls(model=model, alias=alias, **kwargs)  # type: ignore[arg-type]
    if not wrapper.supports(model):
        raise TypeError(
            f"{iface_cls.__name__} does not support model {model.__class__.__name__!r}"
        )
    return wrapper


def list_interface_kinds() -> list[str]:
    """Return the five canonical kinds the registry knows about."""
    return list(_INTERFACE_BY_KIND.keys())


__all__ = ["list_interface_kinds", "wrap_model"]
