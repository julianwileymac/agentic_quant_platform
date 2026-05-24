"""GraphSpec compilers — one per mode.

Each compiler takes a :class:`GraphSpec` plus a :class:`CompileContext`
and returns a :class:`CompileResult` describing how the runtime should
dispatch (Celery task signature, Dagster job kwargs, inline call,
sweep group, ...).

Selecting the compiler is done by :func:`select_compiler` which
matches on ``GraphSpec.mode``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from aqp.lab.schema import GraphSpec


@dataclass
class CompileContext:
    """Per-compile envelope passed from :class:`LabRuntime`."""

    run_id: str
    task_id: str | None = None
    session_id: str | None = None
    lab_id: str | None = None
    request_context: Any | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompileResult:
    """What :class:`LabRuntime` should dispatch to."""

    mode: str
    target: str  # "celery_canvas" | "celery_group" | "dagster_job" | "inline"
    payload: dict[str, Any]
    breadcrumbs: list[dict[str, Any]] = field(default_factory=list)


def select_compiler(mode: str) -> Callable[[GraphSpec, CompileContext], CompileResult]:
    """Return the compile function for a mode string."""
    if mode == "eda":
        from aqp.lab.compiler.eda import compile_eda

        return compile_eda
    if mode == "testing":
        from aqp.lab.compiler.testing import compile_testing

        return compile_testing
    if mode == "evaluation":
        from aqp.lab.compiler.evaluation import compile_evaluation

        return compile_evaluation
    if mode == "simulation":
        from aqp.lab.compiler.simulation import compile_simulation

        return compile_simulation
    raise ValueError(f"Unknown Data Lab mode: {mode!r}")


__all__ = ["CompileContext", "CompileResult", "select_compiler"]
