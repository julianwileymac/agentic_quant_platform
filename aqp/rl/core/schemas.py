"""Schema introspection helpers — power the API + UI builder dropdowns.

For each registered RL component (env, reward, observation, action,
termination, policy, agent, data, ensembler, experiment) we surface a
JSON-friendly schema describing the constructor kwargs so the RL Lab
can render a form dynamically.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

from aqp.core.registry import _kind_index, list_by_kind
from aqp.rl.core.base import RL_KINDS, RLComponent

logger = logging.getLogger(__name__)


_PRIMITIVE_TYPES: dict[Any, str] = {
    int: "integer",
    float: "number",
    bool: "boolean",
    str: "string",
}


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    """Best-effort mapping of a Python type annotation to a JSON schema fragment."""
    if annotation is inspect.Parameter.empty:
        return {"type": "any"}
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if annotation in _PRIMITIVE_TYPES:
        return {"type": _PRIMITIVE_TYPES[annotation]}
    if origin in (list, tuple, set):
        item_schema: dict[str, Any] = {"type": "any"}
        if args:
            item_schema = _annotation_to_schema(args[0])
        return {"type": "array", "items": item_schema}
    if origin is dict:
        return {"type": "object"}
    if origin is None and args == ():
        return {"type": getattr(annotation, "__name__", "any")}
    # ``X | None`` / ``Union[X, None]``
    if origin is None and getattr(annotation, "__class__", None).__name__ == "UnionType":
        non_none = [a for a in annotation.__args__ if a is not type(None)]
        if len(non_none) == 1:
            schema = _annotation_to_schema(non_none[0])
            schema["nullable"] = True
            return schema
    return {"type": "any"}


def component_schema(cls: type) -> dict[str, Any]:
    """Return a JSON schema fragment describing ``cls``'s constructor kwargs."""
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return {"properties": {}, "required": []}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        schema = _annotation_to_schema(param.annotation)
        if param.default is not inspect.Parameter.empty:
            try:
                schema["default"] = param.default
            except Exception:  # noqa: BLE001
                schema["default"] = str(param.default)
        else:
            required.append(name)
        properties[name] = schema
    return {
        "alias": getattr(cls, "rl_alias", None) or cls.__name__,
        "kind": getattr(cls, "rl_kind", None),
        "module": cls.__module__,
        "class": cls.__name__,
        "doc": (cls.__doc__ or "").strip(),
        "properties": properties,
        "required": required,
        "tags": list(getattr(cls, "rl_tags", ()) or ()),
        "source": getattr(cls, "rl_source", None),
        "category": getattr(cls, "rl_category", None),
    }


def list_component_schemas(kind: str | None = None) -> dict[str, dict[str, Any]]:
    """Return ``{alias: schema}`` for every registered RL component (or one kind)."""
    out: dict[str, dict[str, Any]] = {}
    if kind is not None:
        kinds = (kind,) if isinstance(kind, str) else tuple(kind)
    else:
        kinds = RL_KINDS
    for k in kinds:
        for alias, cls in list_by_kind(k).items():
            try:
                out[alias] = component_schema(cls)
            except Exception:  # noqa: BLE001
                logger.debug("schema introspection failed for %s", alias, exc_info=True)
    return out


def list_kinds_with_counts() -> dict[str, int]:
    """Return ``{kind: number_of_registered_components}`` for the API."""
    return {k: len(_kind_index.get(k, {})) for k in RL_KINDS}


__all__ = [
    "component_schema",
    "list_component_schemas",
    "list_kinds_with_counts",
]
