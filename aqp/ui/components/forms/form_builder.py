"""Schema-driven form component.

Every API-backed page in AQP hand-rolls the same :func:`solara.InputText` /
:func:`solara.Select` / :func:`solara.Checkbox` layout. :class:`FieldSpec`
makes this declarative::

    spec = [
        FieldSpec("symbol", "Symbol", type="text", default="AAPL"),
        FieldSpec("side", "Side", type="enum", choices=["buy", "sell"]),
        FieldSpec("quantity", "Qty", type="float", default=1.0, min=0.0),
    ]
    form = FormBuilder(spec)
    form.values  # {"symbol": "AAPL", ...}

The resulting reactive dict plays well with :mod:`aqp.ui.api_client`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import solara


@dataclass
class FieldSpec:
    name: str
    label: str = ""
    type: str = "text"  # text | int | float | bool | enum | textarea
    default: Any = None
    choices: list[Any] = field(default_factory=list)
    hint: str = ""
    required: bool = False
    min: float | None = None
    max: float | None = None
    rows: int = 3
    group: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.name.replace("_", " ").title()


@dataclass
class _FormHandle:
    reactives: dict[str, solara.Reactive]

    @property
    def values(self) -> dict[str, Any]:
        return {k: r.value for k, r in self.reactives.items()}

    def reset(self, defaults: dict[str, Any] | None = None) -> None:
        for k, r in self.reactives.items():
            r.set((defaults or {}).get(k))


def FormBuilder(
    fields: list[FieldSpec] | list[dict[str, Any]],
    *,
    values: dict[str, Any] | None = None,
    on_change: Callable[[str, Any], None] | None = None,
    columns: int = 2,
    disabled: bool = False,
) -> _FormHandle:
    """Plain helper (not a component): builds UI into the current render
    context and returns a :class:`_FormHandle` the parent component can
    query after every render.

    Kept off ``@solara.component`` because the return value is a state
    handle, not an Element — Solara would try to render the handle as a
    child.
    """
    specs = [_normalize(f) for f in fields]
    handle = _use_reactives(specs, values)

    groups = _group_fields(specs)

    with solara.Column(gap="10px"):
        for group_name, group_fields in groups.items():
            if group_name:
                solara.Markdown(f"**{group_name}**")
            _render_group(group_fields, handle, on_change, columns, disabled)

    return handle


def _normalize(spec: FieldSpec | dict[str, Any]) -> FieldSpec:
    if isinstance(spec, FieldSpec):
        return spec
    return FieldSpec(**spec)


def _use_reactives(specs: list[FieldSpec], values: dict[str, Any] | None) -> _FormHandle:
    values = values or {}
    reactives: dict[str, solara.Reactive] = {}
    for spec in specs:
        initial = values.get(spec.name, spec.default)
        if initial is None:
            initial = _blank(spec)
        reactives[spec.name] = solara.use_reactive(initial)
    return _FormHandle(reactives=reactives)


def _blank(spec: FieldSpec) -> Any:
    if spec.type == "bool":
        return False
    if spec.type in {"int", "float"}:
        return ""
    if spec.type == "enum" and spec.choices:
        return spec.choices[0]
    return ""


def _group_fields(specs: list[FieldSpec]) -> dict[str, list[FieldSpec]]:
    groups: dict[str, list[FieldSpec]] = {}
    for spec in specs:
        groups.setdefault(spec.group, []).append(spec)
    return groups


def _render_group(
    specs: list[FieldSpec],
    handle: _FormHandle,
    on_change: Callable[[str, Any], None] | None,
    columns: int,
    disabled: bool,
) -> None:
    row_bucket: list[FieldSpec] = []
    for spec in specs:
        if spec.type == "textarea":
            _flush_row(row_bucket, handle, on_change, columns, disabled)
            row_bucket = []
            _render_field(spec, handle, on_change, disabled, full_width=True)
            continue
        row_bucket.append(spec)
        if len(row_bucket) >= columns:
            _flush_row(row_bucket, handle, on_change, columns, disabled)
            row_bucket = []
    _flush_row(row_bucket, handle, on_change, columns, disabled)


def _flush_row(
    bucket: list[FieldSpec],
    handle: _FormHandle,
    on_change: Callable[[str, Any], None] | None,
    columns: int,
    disabled: bool,
) -> None:
    if not bucket:
        return
    with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
        for spec in bucket:
            _render_field(spec, handle, on_change, disabled, full_width=False)


def _render_field(
    spec: FieldSpec,
    handle: _FormHandle,
    on_change: Callable[[str, Any], None] | None,
    disabled: bool,
    *,
    full_width: bool,
) -> None:
    reactive = handle.reactives[spec.name]
    label = spec.label + ("*" if spec.required else "")
    style = {"min-width": "100%"} if full_width else {"min-width": "220px", "flex": "1"}

    def _hook(value: Any) -> None:
        reactive.set(value)
        if on_change is not None:
            on_change(spec.name, value)

    if spec.type == "bool":
        with solara.Div(style=style):
            solara.Checkbox(label=label, value=reactive, disabled=disabled)
            if spec.hint:
                _hint(spec.hint)
        return
    if spec.type == "enum" and spec.choices:
        with solara.Div(style=style):
            solara.Select(
                label=label,
                value=reactive,
                values=[str(c) for c in spec.choices],
                on_value=_hook,
                disabled=disabled,
            )
            if spec.hint:
                _hint(spec.hint)
        return
    if spec.type == "textarea":
        with solara.Div(style=style):
            solara.InputTextArea(
                label=label,
                value=reactive,
                on_value=_hook,
                rows=spec.rows,
                disabled=disabled,
            )
            if spec.hint:
                _hint(spec.hint)
        return
    with solara.Div(style=style):
        solara.InputText(
            label=label,
            value=reactive,
            on_value=_hook,
            disabled=disabled,
        )
        if spec.hint:
            _hint(spec.hint)


def _hint(text: str) -> None:
    solara.Markdown(f"<div style='font-size:11px;opacity:0.6;margin-top:-4px'>{text}</div>")
