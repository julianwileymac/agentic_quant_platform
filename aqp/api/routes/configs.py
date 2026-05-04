"""``/configs`` — read / write / inspect the layered config from the webui.

Resolution order: ``global > org > team > user > workspace > project``.
Effective config is whatever :func:`aqp.config.resolve_config` returns
for the active :class:`RequestContext`.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from aqp.auth import CurrentUser, RequestContext, current_context, current_user
from aqp.config import (
    clear_overlay,
    get_overlay,
    resolve_config,
    set_overlay,
)
from aqp.config.defaults import ALL_SCOPE_KINDS, SCOPE_GLOBAL

router = APIRouter(prefix="/configs", tags=["tenancy"])

_VALID_SCOPES = {k for k in ALL_SCOPE_KINDS if k != SCOPE_GLOBAL}


class OverlayIn(BaseModel):
    payload: dict[str, Any]
    conflict: str = "last"  # last | first | error


@router.get("/effective")
def effective(
    namespace: str,
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    """Return the merged effective config for ``namespace`` under the
    current request context."""
    return resolve_config(namespace=namespace, context=ctx)


@router.get("/{scope_kind}/{scope_id}/{namespace}")
def get_layer(scope_kind: str, scope_id: str, namespace: str) -> dict[str, Any]:
    """Return the raw payload of one overlay layer (or ``{}`` if missing)."""
    if scope_kind not in {*_VALID_SCOPES, SCOPE_GLOBAL}:
        raise HTTPException(status_code=400, detail=f"unknown scope_kind {scope_kind!r}")
    layer = get_overlay(scope_kind, scope_id, namespace)
    return layer or {}


@router.put("/{scope_kind}/{scope_id}/{namespace}", status_code=status.HTTP_200_OK)
def put_layer(
    scope_kind: str,
    scope_id: str,
    namespace: str,
    body: OverlayIn,
    user: CurrentUser = Depends(current_user),
) -> dict[str, str]:
    if scope_kind not in _VALID_SCOPES:
        raise HTTPException(status_code=400, detail=f"unknown scope_kind {scope_kind!r}")
    rid = set_overlay(
        scope_kind,
        scope_id,
        namespace,
        body.payload,
        updated_by=user.id,
        conflict=body.conflict,
    )
    return {"overlay_id": rid}


@router.delete(
    "/{scope_kind}/{scope_id}/{namespace}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_layer(scope_kind: str, scope_id: str, namespace: str) -> None:
    if scope_kind not in _VALID_SCOPES:
        raise HTTPException(status_code=400, detail=f"unknown scope_kind {scope_kind!r}")
    removed = clear_overlay(scope_kind, scope_id, namespace)
    if not removed:
        raise HTTPException(status_code=404, detail="overlay not found")
