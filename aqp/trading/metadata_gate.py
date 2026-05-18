"""Paper-trading metadata gate (strict-only).

BREAKING CHANGE (OOS-4): paper sessions now always fail startup when
``model_urn`` or ``pipeline_urn`` is missing, malformed, unresolved, or
points at an ML model aspect whose status is not ``Production`` or
``Staging``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import desc, select

from aqp.metadata import MetadataValidationError, parse_urn
from aqp.persistence.db import get_session
from aqp.persistence.models_aspects import EntityAspect
from aqp.tasks._progress import emit

logger = logging.getLogger(__name__)

_ALLOWED_MODEL_STATUSES = {"Production", "Staging"}

try:  # CP-2 helper module (optional while rolling out)
    from aqp.metadata.aspect_lookup import (  # type: ignore[attr-defined]
        load_ml_model as _load_ml_model,
        load_pipeline as _load_pipeline,
    )
except Exception:  # pragma: no cover - CP-2 is optional in this branch
    _load_ml_model = None
    _load_pipeline = None


@dataclass(frozen=True, slots=True)
class GateOutcome:
    ok: bool
    model_urn: str | None
    pipeline_urn: str | None
    model_status: str | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    enforced: bool


def _normalise_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _latest_aspect_payload(*, urn: str, aspect_name: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = (
            session.execute(
                select(EntityAspect)
                .where(EntityAspect.urn == urn)
                .where(EntityAspect.aspect_name == aspect_name)
                .order_by(desc(EntityAspect.version), desc(EntityAspect.created_at))
            )
            .scalars()
            .first()
        )
        if row is None or not isinstance(row.payload, dict):
            return None
        return dict(row.payload)


def _payload_from_lookup(
    loader: Callable[[str], Any] | None,
    urn: str,
) -> dict[str, Any] | None:
    if loader is None:
        return None
    try:
        loaded = loader(urn)
    except Exception:  # pragma: no cover - defensive around optional CP-2 helpers
        logger.debug("metadata lookup helper failed for %s", urn, exc_info=True)
        return None
    if loaded is None:
        return None
    if isinstance(loaded, dict):
        return dict(loaded)
    payload = getattr(loaded, "payload", None)
    if isinstance(payload, dict):
        return dict(payload)
    model_dump = getattr(loaded, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, dict):
            return dict(dumped)
    status = getattr(loaded, "status", None)
    if status is not None:
        return {"status": str(status)}
    return None


def _resolve_ml_model(urn: str) -> dict[str, Any] | None:
    payload = _payload_from_lookup(_load_ml_model, urn)
    if payload is not None:
        return payload
    return _latest_aspect_payload(urn=urn, aspect_name="mlModelMetadata")


def _resolve_pipeline(urn: str) -> dict[str, Any] | None:
    payload = _payload_from_lookup(_load_pipeline, urn)
    if payload is not None:
        return payload
    return _latest_aspect_payload(urn=urn, aspect_name="pipelineMetadata")


def run_metadata_gate(
    *,
    model_urn: str | None,
    pipeline_urn: str | None,
    task_id: str | None = None,
    run_name: str | None = None,
) -> GateOutcome:
    clean_model_urn = _normalise_optional_text(model_urn)
    clean_pipeline_urn = _normalise_optional_text(pipeline_urn)

    warnings: list[str] = []
    errors: list[str] = []
    error_fields: list[str] = []
    model_status: str | None = None

    def _add_error(field: str, message: str) -> None:
        errors.append(message)
        if field not in error_fields:
            error_fields.append(field)

    if clean_model_urn is None:
        _add_error(
            "model_urn",
            "model_urn is required for paper sessions",
        )
    else:
        try:
            parse_urn(clean_model_urn)
        except ValueError as exc:
            _add_error("model_urn", f"invalid model_urn '{clean_model_urn}': {exc}")
        else:
            model_payload = _resolve_ml_model(clean_model_urn)
            if model_payload is None:
                _add_error(
                    "model_urn",
                    (
                        f"model_urn '{clean_model_urn}' was not found in entity_aspects "
                        "(aspect=mlModelMetadata)"
                    ),
                )
            else:
                raw_status = model_payload.get("status")
                model_status = str(raw_status) if raw_status is not None else None
                if model_status not in _ALLOWED_MODEL_STATUSES:
                    _add_error(
                        "model_urn",
                        (
                            f"model status='{model_status}' is not Production/Staging "
                            f"for model_urn '{clean_model_urn}'"
                        ),
                    )

    if clean_pipeline_urn is None:
        _add_error(
            "pipeline_urn",
            "pipeline_urn is required for paper sessions",
        )
    else:
        try:
            parse_urn(clean_pipeline_urn)
        except ValueError as exc:
            _add_error("pipeline_urn", f"invalid pipeline_urn '{clean_pipeline_urn}': {exc}")
        else:
            pipeline_payload = _resolve_pipeline(clean_pipeline_urn)
            if pipeline_payload is None:
                _add_error(
                    "pipeline_urn",
                    (
                        f"pipeline_urn '{clean_pipeline_urn}' was not found in entity_aspects "
                        "(aspect=pipelineMetadata)"
                    ),
                )

    status: str
    if errors:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "ok"

    run_label = _normalise_optional_text(run_name)
    prefix = f"{run_label}: " if run_label else ""
    if errors:
        summary = (
            f"{prefix}metadata gate failed with {len(errors)} error(s); "
            "strict mode blocked startup"
        )
    elif warnings:
        summary = f"{prefix}metadata gate warning: {warnings[0]}"
    else:
        summary = f"{prefix}metadata gate checks passed"

    if task_id is not None:
        emit(
            task_id,
            "metadata_gate",
            summary,
            status=status,
            run_name=run_label,
            strict_mode=True,
            model_urn=clean_model_urn,
            pipeline_urn=clean_pipeline_urn,
            model_status=model_status,
            warnings=list(warnings),
            errors=list(errors),
            enforced=True,
        )

    outcome = GateOutcome(
        ok=not errors,
        model_urn=clean_model_urn,
        pipeline_urn=clean_pipeline_urn,
        model_status=model_status,
        warnings=tuple(warnings),
        errors=tuple(errors),
        enforced=True,
    )
    if errors:
        logger.error(
            "metadata gate blocked startup run_name=%s model_urn=%s pipeline_urn=%s errors=%s",
            run_label,
            clean_model_urn,
            clean_pipeline_urn,
            errors,
        )
        raise MetadataValidationError(
            fields=error_fields,
            guidance=(
                "Set valid model_urn/pipeline_urn values and ensure model status is "
                "Production or Staging before starting paper sessions."
            ),
        )
    return outcome


def assert_metadata_gate(
    *,
    model_urn: str | None,
    pipeline_urn: str | None,
    task_id: str | None = None,
    run_name: str | None = None,
) -> GateOutcome:
    """Run strict metadata validation and raise on any gate failure."""
    outcome = run_metadata_gate(
        model_urn=model_urn,
        pipeline_urn=pipeline_urn,
        task_id=task_id,
        run_name=run_name,
    )
    if not outcome.ok:
        raise MetadataValidationError(
            fields=["model_urn", "pipeline_urn"],
            guidance=(
                "Set valid model_urn/pipeline_urn values and ensure model status is "
                "Production or Staging before starting paper sessions."
            ),
        )
    return outcome


def gate_session_config(
    session_cfg: dict[str, Any],
    *,
    task_id: str | None = None,
) -> GateOutcome:
    run_name = _normalise_optional_text(session_cfg.get("run_name"))
    model_urn = _normalise_optional_text(session_cfg.get("model_urn"))
    pipeline_urn = _normalise_optional_text(session_cfg.get("pipeline_urn"))
    return run_metadata_gate(
        model_urn=model_urn,
        pipeline_urn=pipeline_urn,
        task_id=task_id,
        run_name=run_name,
    )


__all__ = [
    "GateOutcome",
    "assert_metadata_gate",
    "gate_session_config",
    "run_metadata_gate",
]
