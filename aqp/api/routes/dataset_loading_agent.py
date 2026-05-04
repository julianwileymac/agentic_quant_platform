"""``/agents/dataset-loading`` REST surface.

Drives the ``dataset_loading_assistant`` AgentSpec via
:class:`aqp.agents.runtime.AgentRuntime`. The route exposes a single
``POST /consult`` endpoint that returns the agent's JSON proposal
(summary + preset_match + proposed_manifest + setup_wizard +
next_actions). The caller is responsible for accepting one of the
``next_actions`` and routing it through the standard data-plane
APIs (/sources, /sinks, /dataset-presets, /engine).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/dataset-loading", tags=["agents", "data-pipelines"])


class ConsultRequest(BaseModel):
    user_prompt: str = Field(
        ...,
        description="Free-text question, e.g. 'How do I ingest the SEC EDGAR daily index for 2024?'",
    )
    path: str | None = Field(
        default=None,
        description="Optional local path the agent can inspect via inspect_path.",
    )
    url: str | None = Field(
        default=None,
        description="Optional URL the agent can probe via peek_url.",
    )
    target_table: str | None = None
    target_namespace: str | None = None
    extra_context: dict[str, Any] = Field(default_factory=dict)


class ConsultResponse(BaseModel):
    run_id: str
    spec_name: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float = 0.0
    n_calls: int = 0
    n_tool_calls: int = 0
    error: str | None = None


@router.post("/consult", response_model=ConsultResponse)
def consult(
    body: ConsultRequest,
    ctx: RequestContext = Depends(current_context),
) -> ConsultResponse:
    """Run the dataset_loading_assistant agent with the user's prompt."""
    try:
        from aqp.agents.registry import get_spec
        from aqp.agents.runtime import AgentRuntime
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"agent runtime unavailable: {exc}") from exc

    try:
        spec = get_spec("dataset_loading_assistant")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=404,
            detail=f"dataset_loading_assistant spec not found: {exc}",
        ) from exc

    inputs: dict[str, Any] = {
        "user_prompt": body.user_prompt,
    }
    if body.path:
        inputs["path"] = body.path
    if body.url:
        inputs["url"] = body.url
    if body.target_namespace:
        inputs["target_namespace"] = body.target_namespace
    if body.target_table:
        inputs["target_table"] = body.target_table
    if body.extra_context:
        inputs["extra_context"] = dict(body.extra_context)

    try:
        runtime = AgentRuntime(spec=spec, context=ctx)
        result = runtime.run(inputs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("dataset_loading_assistant failed")
        raise HTTPException(status_code=500, detail=f"agent run failed: {exc}") from exc

    return ConsultResponse(
        run_id=result.run_id,
        spec_name=result.spec_name,
        status=result.status,
        output=dict(result.output or {}),
        cost_usd=float(result.cost_usd or 0.0),
        n_calls=int(result.n_calls or 0),
        n_tool_calls=int(result.n_tool_calls or 0),
        error=result.error,
    )


__all__ = ["router"]
