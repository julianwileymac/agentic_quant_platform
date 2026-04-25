"""ParameterEditor — data-driven controls for strategy model kwargs.

The strategy builder keeps a catalog like::

    ALPHA_MODELS = {
        "MeanReversionAlpha": {
            "module_path": "aqp.strategies.mean_reversion",
            "kwargs": {"lookback": 20, "z_threshold": 2.0},
        },
        ...
    }

This component renders that catalog into a ``Select(model)`` + an auto-
generated form for the chosen model's ``kwargs``. Callers get a reactive
dict of overrides and the fully-resolved ``(module_path, kwargs)`` tuple
ready to drop into the YAML recipe.

Implementation note: we keep a **single** reactive dict for all kwargs so
the number of ``use_reactive`` calls per render is constant even when the
user switches models. This keeps Solara's rules-of-hooks happy and avoids
hook-count mismatches across re-renders.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import solara


@dataclass
class ModelCatalog:
    """Catalog shape used across Alpha / Portfolio / Risk / Execution menus."""

    label: str
    entries: dict[str, dict[str, Any]]
    help: str = ""

    def module_path(self, name: str) -> str | None:
        return (self.entries.get(name) or {}).get("module_path")

    def defaults(self, name: str) -> dict[str, Any]:
        return dict((self.entries.get(name) or {}).get("kwargs") or {})


@dataclass
class _EditorHandle:
    model: solara.Reactive[str]
    overrides: solara.Reactive[dict[str, Any]]
    catalog: ModelCatalog

    def kwargs(self) -> dict[str, Any]:
        """Resolve the currently selected kwargs (defaults + overrides)."""
        base = self.catalog.defaults(self.model.value)
        for key, value in (self.overrides.value or {}).items():
            if key in base:
                base[key] = _coerce(value, type(base[key]))
            else:
                base[key] = value
        return base

    def as_block(self) -> dict[str, Any]:
        return {
            "class": self.model.value,
            "module_path": self.catalog.module_path(self.model.value),
            "kwargs": self.kwargs(),
        }


def ParameterEditor(
    catalog: ModelCatalog,
    *,
    initial_model: str | None = None,
    initial_overrides: dict[str, Any] | None = None,
    on_change: Callable[[dict[str, Any]], None] | None = None,
) -> _EditorHandle:
    """Plain helper (not a component): renders the Select + kwargs form
    and returns an :class:`_EditorHandle` the parent page can query for
    the resolved kwargs + module path block.

    Not decorated with ``@solara.component`` because the return value is
    a state handle, not a rendered Element.
    """
    names = list(catalog.entries.keys())

    model = solara.use_reactive(initial_model or (names[0] if names else ""))
    overrides: solara.Reactive[dict[str, Any]] = solara.use_reactive(
        dict(initial_overrides or {})
    )
    last_synced_model = solara.use_reactive("")

    # When the selected model changes, reset the overrides to its defaults so
    # widgets always reflect the chosen catalog entry.
    def _sync_on_model_change() -> None:
        if model.value != last_synced_model.value:
            last_synced_model.set(model.value)
            overrides.set(catalog.defaults(model.value))

    solara.use_effect(_sync_on_model_change, [model.value])

    if not names:
        with solara.Column(gap="8px"):
            solara.Markdown(f"_No {catalog.label} registered._")
        return _EditorHandle(model=model, overrides=overrides, catalog=catalog)

    combined = {**catalog.defaults(model.value), **(overrides.value or {})}

    def _update(key: str, value: Any) -> None:
        new_map = dict(overrides.value or {})
        new_map[key] = value
        overrides.set(new_map)
        if on_change is not None:
            on_change(
                {
                    "class": model.value,
                    "module_path": catalog.module_path(model.value),
                    "kwargs": new_map,
                }
            )

    with solara.Column(gap="8px"):
        if catalog.help:
            solara.Markdown(f"<div style='font-size:12px;opacity:0.7'>{catalog.help}</div>")
        solara.Select(label=catalog.label, value=model, values=names)
        if not combined:
            solara.Markdown("_This class has no tunable kwargs._")
        else:
            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                for key, value in combined.items():
                    _render_field(key, value, _update)

    return _EditorHandle(model=model, overrides=overrides, catalog=catalog)


def _render_field(
    key: str,
    value: Any,
    update: Callable[[str, Any], None],
) -> None:
    """Render one kwarg as either a checkbox or a text input.

    We avoid per-field ``use_reactive`` so the number of hooks stays constant
    across re-renders — Solara enforces rules-of-hooks like React.
    """
    if isinstance(value, bool):
        with solara.Div(style={"min-width": "160px"}):
            solara.Checkbox(
                label=key,
                value=bool(value),
                on_value=lambda v: update(key, bool(v)),
            )
        return
    with solara.Div(style={"min-width": "200px"}):
        solara.InputText(
            label=key,
            value=_to_str(value),
            on_value=lambda v, k=key: update(k, v),
        )


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _to_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def _coerce(value: Any, target: type) -> Any:
    if target is bool or isinstance(value, bool):
        return _to_bool(value)
    if target is int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
    if target is float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    if target is list:
        if isinstance(value, list):
            return value
        return [s.strip() for s in str(value).split(",") if s.strip()]
    return value
