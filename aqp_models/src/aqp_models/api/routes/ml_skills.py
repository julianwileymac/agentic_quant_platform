"""``/ml/skills`` REST surface.

Endpoints:

- ``GET /ml/skills`` — list registered :class:`MLSkillSpec` specs.
- ``GET /ml/skills/{name}`` — describe one spec.
- ``POST /ml/skills/{name}/run`` — queue a Celery task driving
  :class:`MLSkillRuntime.run`.

All long-running ops dispatch to ``aqp_models.tasks`` (Hard Rule 4 +
the cardinal "routes thin-wrap tasks; tasks thin-wrap subsystem
functions" guidance in :file:`.cursor/rules/tasks-api.mdc`).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.api.schemas import TaskAccepted
from aqp_models.registry import get_skill_spec, list_skill_specs

logger = logging.getLogger(__name__)

router = secure_router(prefix="/ml/skills", tags=["ml-skills"], default_scope="data:read")


class SkillSummary(BaseModel):
    name: str
    description: str
    kind: str
    n_steps: int
    annotations: list[str] = Field(default_factory=list)
    spec_hash: str


class SkillDescribe(SkillSummary):
    steps: list[dict[str, Any]]
    guardrails: dict[str, Any]


class SkillRunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    experiment_id: str | None = None
    test_id: str | None = None


@router.get("", response_model=list[SkillSummary])
def list_skills() -> list[SkillSummary]:
    return [_summary(spec) for spec in list_skill_specs()]


@router.get("/{name}", response_model=SkillDescribe)
def describe_skill(name: str) -> SkillDescribe:
    try:
        spec = get_skill_spec(name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return SkillDescribe(
        **_summary(spec).model_dump(),
        steps=[step.model_dump(mode="json") for step in spec.steps],
        guardrails=spec.guardrails.model_dump(mode="json"),
    )


@router.post("/{name}/run", response_model=TaskAccepted)
def run_skill(name: str, req: SkillRunRequest) -> TaskAccepted:
    """Queue a Celery task driving :class:`MLSkillRuntime`."""
    try:
        get_skill_spec(name)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    from aqp_models.tasks.ml_skill_tasks import run_ml_skill

    async_result = run_ml_skill.delay(
        name=name,
        inputs=dict(req.inputs or {}),
        experiment_id=req.experiment_id,
        test_id=req.test_id,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


def _summary(spec: Any) -> SkillSummary:
    return SkillSummary(
        name=spec.name,
        description=spec.description,
        kind=spec.kind,
        n_steps=len(spec.steps),
        annotations=list(spec.annotations),
        spec_hash=spec.spec_hash(),
    )
