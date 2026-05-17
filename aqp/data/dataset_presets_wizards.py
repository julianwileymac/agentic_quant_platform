"""Per-preset setup wizards.

Each curated :class:`aqp.data.dataset_presets.DatasetPreset` has a
companion :class:`PresetWizard` that builds on
:mod:`aqp.data.sources.setup_wizards` to walk the user from "I clicked
on the preset card" to "I have a project-scoped
:class:`DatasetPipelineConfigRow` and a queued ingestion run".

Wizards are pure data + thin runners — the ``/dataset-presets/{name}/wizard/step``
HTTP route in :mod:`aqp.api.routes.dataset_presets` resolves them
against the layered tenancy context.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from aqp.data.dataset_presets import PRESETS, DatasetPreset, get_preset
from aqp.data.sources.setup_wizards import StepResult, WizardStep, FieldSpec

logger = logging.getLogger(__name__)


@dataclass
class PresetWizard:
    """Setup wizard scoped to one curated dataset preset."""

    preset_name: str
    steps: list[WizardStep] = field(default_factory=list)
    runners: dict[str, Callable[[dict[str, Any]], StepResult]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        preset = get_preset(self.preset_name)
        return {
            "preset_name": self.preset_name,
            "preset_description": preset.description,
            "documentation_url": preset.documentation_url,
            "steps": [s.to_dict() for s in self.steps],
        }

    def step(self, step_id: str) -> WizardStep | None:
        for s in self.steps:
            if s.id == step_id:
                return s
        return None

    def run_step(self, step_id: str, payload: dict[str, Any]) -> StepResult:
        runner = self.runners.get(step_id)
        if runner is None:
            return StepResult(
                ok=True,
                message=f"step {step_id!r} acknowledged",
                details={"payload": dict(payload)},
            )
        try:
            return runner(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "preset wizard failed: preset=%s step=%s err=%s",
                self.preset_name,
                step_id,
                exc,
            )
            return StepResult(ok=False, message=str(exc))


def _credential_runner(env_key: str | None) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        if not env_key:
            return StepResult(ok=True, message="no credential required")
        import os

        value = (payload.get(env_key) or os.environ.get(env_key) or "").strip()
        if not value:
            return StepResult(
                ok=False,
                message=f"missing {env_key}",
                details={"missing": [env_key]},
            )
        os.environ[env_key] = value
        return StepResult(ok=True, message=f"{env_key} configured")

    return runner


def _sink_runner(preset_name: str) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        sinks = payload.get("sink_ids") or []
        return StepResult(
            ok=True,
            message=f"using {len(sinks) or 'default'} sink(s)",
            details={"preset": preset_name, "sink_ids": list(sinks)},
        )

    return runner


def _schedule_runner(preset_name: str) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        cron = payload.get("schedule_cron") or ""
        return StepResult(
            ok=True,
            message="schedule recorded" if cron else "manual ingestion",
            details={"preset": preset_name, "cron": cron},
        )

    return runner


def _persist_config_runner(
    preset_name: str,
) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        try:
            from datetime import datetime

            from aqp.persistence.db import get_session
            from aqp.persistence.models_data_control import DatasetPipelineConfigRow
        except Exception as exc:  # pragma: no cover - DB optional in unit tests
            return StepResult(
                ok=False,
                message=f"persistence layer unavailable: {exc}",
            )
        try:
            with get_session() as session:
                row = DatasetPipelineConfigRow(
                    name=payload.get("name") or preset_name,
                    config_json={
                        "preset": preset_name,
                        "extras": payload.get("extras", {}),
                    },
                    sinks=list(payload.get("sink_ids") or []),
                    automations=[
                        {"kind": "cron", "cron": payload.get("schedule_cron")}
                    ]
                    if payload.get("schedule_cron")
                    else [],
                    tags=list(payload.get("tags") or []),
                    notes=payload.get("notes"),
                    is_active=True,
                    created_by=payload.get("created_by") or "wizard",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    owner_user_id=payload.get("owner_user_id"),
                    workspace_id=payload.get("workspace_id"),
                    project_id=payload.get("project_id"),
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                return StepResult(
                    ok=True,
                    message=f"saved DatasetPipelineConfigRow id={row.id}",
                    details={"id": row.id},
                )
        except Exception as exc:  # noqa: BLE001
            return StepResult(ok=False, message=f"persist failed: {exc}")

    return runner


def _trigger_runner(preset_name: str) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        if not payload.get("trigger", True):
            return StepResult(
                ok=True,
                message="ingestion not triggered (saved config only)",
            )
        try:
            from aqp.tasks.dataset_preset_tasks import dispatch_preset_ingest
        except Exception as exc:  # pragma: no cover - celery optional
            return StepResult(ok=False, message=f"celery unavailable: {exc}")
        try:
            kwargs: dict[str, Any] = {}
            symbols = payload.get("symbols")
            if symbols:
                kwargs["symbols"] = list(symbols)
            extra = payload.get("extras") or {}
            kwargs.update(extra)
            result = dispatch_preset_ingest(preset_name, **kwargs)
            task_id = str(getattr(result, "id", "local"))
            return StepResult(
                ok=True,
                message=f"queued ingestion task_id={task_id}",
                details={"task_id": task_id, "preset": preset_name},
            )
        except Exception as exc:  # noqa: BLE001
            return StepResult(ok=False, message=f"dispatch failed: {exc}")

    return runner


def _make_steps(preset: DatasetPreset) -> list[WizardStep]:
    steps: list[WizardStep] = [
        WizardStep(
            id="review",
            label="Review",
            prompt=(
                f"{preset.description}\n\n"
                f"Source kind: {preset.source_kind}\n"
                f"Iceberg target: {preset.iceberg_identifier}\n"
                f"Default interval: {preset.interval}"
            ),
        )
    ]
    if preset.requires_api_key and preset.api_key_env_var:
        steps.append(
            WizardStep(
                id="credentials",
                label="Credentials",
                prompt=f"Provide {preset.api_key_env_var}.",
                fields=[
                    FieldSpec(
                        name=preset.api_key_env_var,
                        label="API key",
                        secret=True,
                        required=True,
                    )
                ],
            )
        )
    steps.append(
        WizardStep(
            id="sinks",
            label="Sinks",
            prompt=(
                "Select the sinks (by id) to attach to this dataset config. "
                "Leave empty to use the preset default."
            ),
            fields=[
                FieldSpec(
                    name="sink_ids",
                    label="Sink ids (comma separated)",
                    type="tags",
                    required=False,
                )
            ],
            optional=True,
        )
    )
    steps.append(
        WizardStep(
            id="schedule",
            label="Schedule",
            prompt="Choose a cron schedule (leave blank for manual).",
            fields=[
                FieldSpec(
                    name="schedule_cron",
                    label="Cron expression",
                    default=preset.schedule_cron or "",
                    placeholder="0 9 * * 1-5",
                    required=False,
                ),
                FieldSpec(
                    name="tags",
                    label="Tags",
                    type="tags",
                    required=False,
                ),
            ],
            optional=True,
        )
    )
    steps.append(
        WizardStep(
            id="persist",
            label="Save config",
            prompt="Save this configuration to the project.",
            fields=[
                FieldSpec(
                    name="name",
                    label="Config name",
                    default=preset.name,
                    required=True,
                ),
                FieldSpec(name="notes", label="Notes", required=False),
            ],
        )
    )
    steps.append(
        WizardStep(
            id="trigger",
            label="Trigger",
            prompt="Optionally queue an immediate ingestion run.",
            fields=[
                FieldSpec(
                    name="trigger",
                    label="Queue ingestion now",
                    type="boolean",
                    default=True,
                )
            ],
            optional=True,
        )
    )
    return steps


def _build_wizard(preset: DatasetPreset) -> PresetWizard:
    runners = {
        "credentials": _credential_runner(preset.api_key_env_var),
        "sinks": _sink_runner(preset.name),
        "schedule": _schedule_runner(preset.name),
        "persist": _persist_config_runner(preset.name),
        "trigger": _trigger_runner(preset.name),
    }
    return PresetWizard(
        preset_name=preset.name,
        steps=_make_steps(preset),
        runners=runners,
    )


WIZARDS: dict[str, PresetWizard] = {
    name: _build_wizard(preset) for name, preset in PRESETS.items()
}


def get_preset_wizard(preset_name: str) -> PresetWizard | None:
    return WIZARDS.get(preset_name)


def list_preset_wizards() -> list[PresetWizard]:
    return list(WIZARDS.values())


__all__ = [
    "PresetWizard",
    "WIZARDS",
    "get_preset_wizard",
    "list_preset_wizards",
]
