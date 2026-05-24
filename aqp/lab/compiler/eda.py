"""EDA-mode compiler: GraphSpec → reactive cell DAG.

Phase 0 supports per-cell ``LabRuntime.preview_cell`` execution; the
full reactive DAG (marimo-style static analysis of cell references)
ships in Phase 1.
"""
from __future__ import annotations

from typing import Any

from aqp.lab.compiler import CompileContext, CompileResult
from aqp.lab.schema import GraphSpec


def compile_eda(spec: GraphSpec, ctx: CompileContext) -> CompileResult:
    if spec.mode != "eda":
        raise ValueError(f"compile_eda requires mode='eda', got {spec.mode!r}")
    eda_cfg = spec.mode_config.eda
    cells = list(eda_cfg.cells) if eda_cfg else []
    payload: dict[str, Any] = {
        "run_id": ctx.run_id,
        "task_id": ctx.task_id,
        "session_id": ctx.session_id,
        "lab_id": ctx.lab_id,
        "cells": [c.model_dump(mode="json") for c in cells],
    }
    return CompileResult(
        mode="eda",
        target="inline",
        payload=payload,
        breadcrumbs=[{"compiler": "eda", "n_cells": len(cells)}],
    )


__all__ = ["compile_eda"]
