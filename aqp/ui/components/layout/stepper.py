"""Multi-step wizard ("stepper") component for Solara.

The platform's strategy builder and ML training pages already use
``TabPanel`` for free-form tab navigation. The Quickstart Agentic
Wizard instead needs a linear, validated flow where each step must
pass before the user can advance. This component provides exactly
that: a numbered header, a content panel, and Next/Back/Finish
controls.

Usage::

    from aqp.ui.components.layout.stepper import Stepper, StepSpec

    def render_step_1():
        solara.Text("Hello")

    step = solara.use_reactive(0)

    Stepper(
        steps=[
            StepSpec(key="intro", label="Intro", render=render_step_1, validate=lambda: None),
            ...
        ],
        step_index=step,
        on_finish=lambda: ...,
    )

Design notes
------------

- ``validate`` returns ``None`` on pass, or a string error message.
- ``step_index`` is the reactive so the parent can drive the flow.
- ``allow_back_after_finish`` is handy when a wizard needs to let the
  user tweak a previous step after seeing the results.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import solara


@dataclass
class StepSpec:
    """Declarative description of one wizard step."""

    key: str
    label: str
    render: Callable[[], None]
    validate: Callable[[], str | None] = lambda: None
    description: str | None = None
    is_optional: bool = False


@solara.component
def Stepper(
    steps: list[StepSpec],
    *,
    step_index: solara.Reactive[int] | None = None,
    on_finish: Callable[[], None] | None = None,
    finish_label: str = "Finish",
    next_label: str = "Next",
    back_label: str = "Back",
    allow_back_after_finish: bool = True,
) -> None:
    """Render a linear wizard over ``steps``.

    Parameters
    ----------
    steps:
        Ordered :class:`StepSpec` list. Must contain at least one entry.
    step_index:
        Reactive index driven by the parent. When omitted a local
        reactive is created.
    on_finish:
        Callback fired when the user clicks the ``finish_label`` button
        on the last step.
    """
    local_idx = solara.use_reactive(0)
    idx = step_index if step_index is not None else local_idx
    error = solara.use_reactive("")

    if not steps:
        solara.Warning("Stepper received no steps.")
        return

    current = max(0, min(idx.value, len(steps) - 1))
    at_last = current == len(steps) - 1
    at_first = current == 0

    def _advance() -> None:
        spec = steps[current]
        err = spec.validate() if spec.validate else None
        if err:
            error.set(err)
            return
        error.set("")
        if at_last:
            if on_finish:
                on_finish()
            return
        idx.set(current + 1)

    def _back() -> None:
        if at_first and not allow_back_after_finish:
            return
        error.set("")
        idx.set(max(0, current - 1))

    with solara.Column(
        gap="16px",
        style={
            "flex": "1",
            "min-width": "0",
            "padding": "4px 2px 2px 2px",
        },
    ):
        _render_header(steps, current)

        spec = steps[current]
        if spec.description:
            solara.Markdown(
                spec.description,
                style={"color": "rgba(148,163,184,0.9)", "font-size": "0.92em"},
            )

        with solara.Div(
            style={
                "padding": "14px 0",
                "border-top": "1px solid rgba(148,163,184,0.2)",
                "border-bottom": "1px solid rgba(148,163,184,0.2)",
                "flex": "1",
                "min-width": "0",
            }
        ):
            spec.render()

        if error.value:
            solara.Error(error.value, dense=True)

        with solara.Row(justify="end", gap="8px"):
            solara.Button(
                label=back_label,
                on_click=_back,
                text=True,
                disabled=at_first,
            )
            solara.Button(
                label=finish_label if at_last else next_label,
                on_click=_advance,
                color="primary",
            )


def _render_header(steps: list[StepSpec], current: int) -> None:
    with solara.Row(gap="12px", style={"flex-wrap": "wrap"}):
        for i, spec in enumerate(steps):
            is_done = i < current
            is_active = i == current
            glyph = "✓" if is_done else str(i + 1)
            color = (
                "#22c55e" if is_done
                else "#38bdf8" if is_active
                else "rgba(148,163,184,0.5)"
            )
            with solara.Row(
                gap="6px",
                style={"align-items": "center"},
            ):
                solara.Div(
                    children=[solara.Text(glyph, style={"color": "white", "font-weight": "700"})],
                    style={
                        "background": color,
                        "border-radius": "50%",
                        "width": "24px",
                        "height": "24px",
                        "display": "flex",
                        "align-items": "center",
                        "justify-content": "center",
                        "font-size": "0.85em",
                    },
                )
                solara.Text(
                    spec.label + (" (optional)" if spec.is_optional else ""),
                    style={
                        "color": color if is_active else "rgba(226,232,240,0.85)",
                        "font-weight": "600" if is_active else "500",
                    },
                )
