"""Qlib-style ``class`` / ``module_path`` / ``kwargs`` factory.

Every configurable object in the platform can be instantiated by::

    from aqp.core.registry import build_from_config
    obj = build_from_config({
        "class": "MeanReversionAlpha",
        "module_path": "aqp.strategies.mean_reversion",
        "kwargs": {"lookback": 20, "z_threshold": 2.0},
    })

This lets the LLM-driven research loop edit a YAML recipe and re-run the
pipeline by a single function call, matching Qlib's ``init_instance_by_config``.

Typed decorators (``@model``, ``@strategy``, ``@env``, ``@agent``,
``@forecaster``, ``@processor``) tag classes with a component-kind so the
UI and CLI can browse / filter the registry without reflecting on module
paths.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

_registry: dict[str, type] = {}

# Maps component-kind → {alias → class} so UIs can enumerate available
# strategies / models / envs / agents without listing every registered name.
_kind_index: dict[str, dict[str, type]] = {}

# Maps class → set of tags (kind + any user tags).
_class_tags: dict[type, set[str]] = {}


def register(name: str | None = None, *, kind: str | None = None, tags: tuple[str, ...] = ()):
    """Decorator to register a class under a short alias (optional).

    ``kind`` buckets the class into a component-kind index (``model``,
    ``strategy``, ``env``, ``agent``, ``forecaster``, ``processor``, ...).
    ``tags`` are free-form and surface in the Strategy Browser filters.
    """

    def wrap(cls: type) -> type:
        key = name or f"{cls.__module__}.{cls.__name__}"
        _registry[key] = cls
        if kind is not None:
            _kind_index.setdefault(kind, {})[name or cls.__name__] = cls
        class_tags = _class_tags.setdefault(cls, set())
        if kind is not None:
            class_tags.add(f"kind:{kind}")
        for t in tags:
            class_tags.add(t)
        return cls

    return wrap


# ---------------------------------------------------------------------------
# Typed decorators — wrappers around ``register`` that pre-fill ``kind``.
# ---------------------------------------------------------------------------


def _make_kind_decorator(kind: str) -> Callable[..., Callable[[type], type]]:
    def decorator(
        name: str | None = None,
        *,
        tags: tuple[str, ...] = (),
    ) -> Callable[[type], type]:
        return register(name=name, kind=kind, tags=tags)

    decorator.__name__ = kind
    decorator.__doc__ = f"Register a class as a ``{kind}`` component."
    return decorator


model = _make_kind_decorator("model")
strategy = _make_kind_decorator("strategy")
env = _make_kind_decorator("env")
agent = _make_kind_decorator("agent")
forecaster = _make_kind_decorator("forecaster")
processor = _make_kind_decorator("processor")
portfolio = _make_kind_decorator("portfolio")
risk = _make_kind_decorator("risk")
execution = _make_kind_decorator("execution")
universe = _make_kind_decorator("universe")
labeling = _make_kind_decorator("labeling")
serving = _make_kind_decorator("serving")

# Domain-model expansion: richer component kinds for the new
# :mod:`aqp.core.domain` + :mod:`aqp.providers` hierarchies. Typed
# decorators let the UI catalog (Strategy Browser, Data Catalog, Crew
# Trace) browse / filter registered classes by kind without reflecting
# on module paths.
instrument = _make_kind_decorator("instrument")
issuer = _make_kind_decorator("issuer")
event = _make_kind_decorator("event")
fundamental_statement = _make_kind_decorator("fundamental_statement")
ownership_record = _make_kind_decorator("ownership_record")
calendar_event = _make_kind_decorator("calendar_event")
economic_series = _make_kind_decorator("economic_series")
news_source = _make_kind_decorator("news_source")
standard_model = _make_kind_decorator("standard_model")
fetcher = _make_kind_decorator("fetcher")
taxonomy = _make_kind_decorator("taxonomy")


def list_by_kind(kind: str) -> dict[str, type]:
    """Return the ``{alias: class}`` mapping for a given component-kind."""
    return dict(_kind_index.get(kind, {}))


def list_kinds() -> list[str]:
    """Return all known component kinds."""
    return sorted(_kind_index)


def get_tags(cls: type) -> set[str]:
    """Return every tag registered for ``cls`` (kind:* + user tags)."""
    return set(_class_tags.get(cls, set()))


def list_by_tag(tag: str) -> list[type]:
    """Return every class whose tag set contains ``tag``.

    Used by UI filters to answer questions like "every strategy tagged
    ``mean_reversion``", "every standard_model tagged ``macro``", or
    "every instrument kind under ``crypto``".
    """
    return [cls for cls, tags in _class_tags.items() if tag in tags]


def tag_class(cls: type, *tags: str) -> type:
    """Annotate an already-registered class with additional tags.

    Useful when a class is registered by a kind-decorator but needs to be
    additionally labelled (``tag_class(MyAlpha, "mean_reversion",
    "low_vol")``).
    """
    bucket = _class_tags.setdefault(cls, set())
    bucket.update(tags)
    return cls


def resolve(cls_ref: str, module_path: str | None = None) -> type:
    """Resolve a class from a string reference.

    Accepts either:
    - a short registered alias (``"MeanReversionAlpha"``),
    - a fully-qualified path (``"aqp.strategies.mean_reversion.MeanReversionAlpha"``),
    - or a ``(class_name, module_path)`` pair.
    """
    if module_path:
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_ref)

    if cls_ref in _registry:
        return _registry[cls_ref]

    if "." in cls_ref:
        module_path, cls_name = cls_ref.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name)

    raise KeyError(f"Cannot resolve class reference: {cls_ref!r}")


def build_from_config(config: dict[str, Any] | None) -> Any:
    """Instantiate an object from a ``{class, module_path, kwargs}`` dict.

    Also recursively instantiates nested configs that themselves look like
    build-specs, allowing composition like::

        alpha:
            class: MyAlpha
            module_path: aqp.strategies.my
            kwargs:
                feature_store:
                    class: DuckDBFeatureStore
                    module_path: aqp.data.features
                    kwargs: {path: ./data/parquet}
    """
    if config is None:
        return None
    if not isinstance(config, dict) or "class" not in config:
        return config

    cls_ref = config["class"]
    module_path = config.get("module_path")
    raw_kwargs = config.get("kwargs", {}) or {}

    kwargs = {k: _maybe_build(v) for k, v in raw_kwargs.items()}

    cls = resolve(cls_ref, module_path)
    return cls(**kwargs)


def _maybe_build(value: Any) -> Any:
    if isinstance(value, dict) and "class" in value:
        return build_from_config(value)
    if isinstance(value, list):
        return [_maybe_build(v) for v in value]
    return value


def list_registered() -> list[str]:
    return sorted(_registry.keys())
