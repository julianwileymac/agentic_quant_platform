"""Helpers for validating and applying ML preprocessing recipes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from aqp.core.registry import build_from_config
from aqp.ml.processors import Processor


@dataclass
class RecipeValidationResult:
    valid: bool
    processors: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "processors": self.processors,
            "errors": self.errors,
            "summary": self.summary,
        }


def build_processors(specs: list[dict[str, Any]] | None) -> list[Processor]:
    processors: list[Processor] = []
    for spec in specs or []:
        built = build_from_config(spec)
        if not isinstance(built, Processor):
            raise TypeError(f"{spec.get('class')!r} did not build a Processor")
        processors.append(built)
    return processors


def validate_processor_specs(specs: list[dict[str, Any]] | None) -> RecipeValidationResult:
    errors: list[str] = []
    built_specs: list[dict[str, Any]] = []
    classes: list[str] = []
    fit_required = 0
    for idx, spec in enumerate(specs or []):
        try:
            proc = build_from_config(spec)
            if not isinstance(proc, Processor):
                raise TypeError(f"resolved to {type(proc).__name__}, expected Processor")
            built_specs.append(proc.to_spec())
            classes.append(type(proc).__name__)
            if getattr(proc, "fit_required", False):
                fit_required += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"processor[{idx}] {spec.get('class', '?')}: {exc}")
    return RecipeValidationResult(
        valid=not errors,
        processors=built_specs,
        errors=errors,
        summary={
            "n_processors": len(specs or []),
            "processor_classes": classes,
            "fit_required": fit_required,
        },
    )


def validate_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    shared = validate_processor_specs(recipe.get("shared_processors") or [])
    infer = validate_processor_specs(recipe.get("infer_processors") or [])
    learn = validate_processor_specs(recipe.get("learn_processors") or [])
    errors = [*shared.errors, *infer.errors, *learn.errors]
    return {
        "valid": not errors,
        "errors": errors,
        "shared": shared.to_dict(),
        "infer": infer.to_dict(),
        "learn": learn.to_dict(),
        "fit_window": dict(recipe.get("fit_window") or {}),
    }


def apply_processor_specs(
    df: pd.DataFrame,
    specs: list[dict[str, Any]] | None,
    *,
    fit: bool = True,
) -> pd.DataFrame:
    out = df
    for proc in build_processors(specs):
        if fit and getattr(proc, "fit_required", False):
            proc.fit(out)
        out = proc(out)
    return out


def summarize_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    validation = validate_recipe(recipe)
    return {
        "valid": validation["valid"],
        "errors": validation["errors"],
        "n_shared": validation["shared"]["summary"]["n_processors"],
        "n_infer": validation["infer"]["summary"]["n_processors"],
        "n_learn": validation["learn"]["summary"]["n_processors"],
        "processor_classes": [
            *validation["shared"]["summary"]["processor_classes"],
            *validation["infer"]["summary"]["processor_classes"],
            *validation["learn"]["summary"]["processor_classes"],
        ],
        "fit_window": validation.get("fit_window") or {},
    }


def materialise_node_spec(
    recipe_id: str,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a saved ``PipelineRecipe`` into a manifest ``NodeSpec`` fragment.

    Mirrors the pattern used by sinks
    (:func:`aqp.data.sinks.service.materialise_node_spec`) so the Manifest
    Builder UI can drop a saved recipe directly onto a pipeline canvas.
    """
    from aqp.persistence.db import get_session
    from aqp.persistence.models import PipelineRecipe

    overrides = dict(overrides or {})
    with get_session() as session:
        row = session.get(PipelineRecipe, recipe_id)
        if row is None:
            raise ValueError(f"pipeline recipe {recipe_id!r} not found")
        return {
            "name": "transform.ml_preprocessing",
            "label": row.name,
            "enabled": True,
            "kwargs": {
                "recipe_id": str(row.id),
                "fit": True,
                **overrides,
            },
        }


__all__ = [
    "RecipeValidationResult",
    "apply_processor_specs",
    "build_processors",
    "materialise_node_spec",
    "summarize_recipe",
    "validate_processor_specs",
    "validate_recipe",
]
