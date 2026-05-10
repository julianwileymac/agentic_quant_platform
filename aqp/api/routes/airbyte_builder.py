"""Graphical Airbyte connector builder REST surface (phase 2).

Backs `frontend/src/components/airbyte/builder/ConnectorBuilderForm.tsx`.
The builder produces either a low-code YAML manifest (declarative
only) or an AQP-native :class:`Fetcher` stub generated under
:file:`aqp/data/fetchers/userland/<slug>.py` — the latter being the
"custom Python escape hatch" path that does NOT require
``AIRBYTE_ENABLE_UNSAFE_CODE`` because it executes inside AQP's
worker, not Airbyte's.
"""
from __future__ import annotations

import difflib
import logging
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from aqp.config import settings
from aqp.data.airbyte.builder import (
    infer_streams,
    schema_to_json,
    state_to_fetcher_stub,
    state_to_yaml,
    validate_manifest,
)
from aqp.persistence.db import get_session
from aqp.persistence.models_airbyte import AirbyteConnectorRow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/airbyte/builder", tags=["airbyte", "builder"])


_FETCHER_USERLAND_DIR = Path("aqp/data/fetchers/userland")
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


class BuilderState(BaseModel):
    """Round-tripped builder form state."""

    model_config = ConfigDict(extra="allow")


class GenerateRequest(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)
    commit: bool = False


class StateRequest(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)


@router.get("/cdk-schema")
def get_schema() -> dict[str, Any]:
    return {"sections": schema_to_json()}


@router.post("/manifest/draft")
def manifest_draft(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    state = payload.get("state") or payload
    try:
        yaml_text = state_to_yaml(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"yaml": yaml_text, "validation": validate_manifest(state)}


@router.post("/manifest/validate")
def manifest_validate(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    state = payload.get("state") or payload
    return validate_manifest(state)


@router.post("/streams/infer")
def streams_infer(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    state = payload.get("state") or payload
    try:
        return infer_streams(state)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/codegen/fetcher")
def codegen_fetcher(payload: GenerateRequest) -> dict[str, Any]:
    """Generate an AQP Fetcher stub. Default is dry-run (returns diff)."""
    state = payload.state
    try:
        rendered = state_to_fetcher_stub(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    metadata = state.get("metadata") or {}
    slug = _slug_from_state(metadata)
    target = _FETCHER_USERLAND_DIR / f"{slug}.py"
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    diff = "".join(
        difflib.unified_diff(
            existing.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=f"a/{target}",
            tofile=f"b/{target}",
            n=3,
        )
    )
    if not payload.commit:
        return {
            "path": str(target),
            "rendered": rendered,
            "diff": diff,
            "would_write": True,
            "exists": target.exists(),
        }
    if not getattr(settings, "airbyte_builder_codegen_enabled", True):
        raise HTTPException(
            status_code=403,
            detail="codegen commit disabled (set AQP_AIRBYTE_BUILDER_CODEGEN_ENABLED=true)",
        )
    if target.exists() and not getattr(settings, "airbyte_builder_overwrite", False):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{target} already exists; set "
                "AQP_AIRBYTE_BUILDER_OVERWRITE=true to overwrite"
            ),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    _ensure_userland_init()
    _persist_fetcher_path(metadata.get("connector_id"), str(target), state)
    return {
        "path": str(target),
        "written": True,
        "diff": diff,
    }


@router.get("/state/{connector_id}")
def get_state(connector_id: str) -> dict[str, Any]:
    cleaned = _clean_connector_id(connector_id)
    with get_session() as session:
        row = session.execute(
            select(AirbyteConnectorRow).where(AirbyteConnectorRow.connector_id == cleaned).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"connector {cleaned!r} not found")
        return {
            "connector_id": cleaned,
            "state": getattr(row, "builder_state_json", None) or {},
            "manifest_yaml": getattr(row, "manifest_yaml", None),
            "aqp_fetcher_path": getattr(row, "aqp_fetcher_path", None),
        }


@router.put("/state/{connector_id}")
def put_state(connector_id: str, payload: StateRequest) -> dict[str, Any]:
    cleaned = _clean_connector_id(connector_id)
    state = payload.state
    report = validate_manifest(state)
    if report["errors"]:
        raise HTTPException(status_code=400, detail=report)
    yaml_text = state_to_yaml(state)
    with get_session() as session:
        row = session.execute(
            select(AirbyteConnectorRow).where(AirbyteConnectorRow.connector_id == cleaned).limit(1)
        ).scalar_one_or_none()
        if row is None:
            row = AirbyteConnectorRow(
                connector_id=cleaned,
                name=str((state.get("metadata") or {}).get("display_name") or cleaned),
                kind="source",
                runtime="hybrid",
                config_schema={},
                streams=[],
            )
            session.add(row)
        row.builder_state_json = state
        row.manifest_yaml = yaml_text
        session.add(row)
        session.commit()
        try:
            from aqp.cache import cache_write_through

            cache_write_through(
                "airbyte_connectors",
                {
                    "id": cleaned,
                    "name": str((state.get("metadata") or {}).get("display_name") or cleaned),
                    "kind": "source",
                    "runtime": "hybrid",
                },
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "connector_id": cleaned,
            "saved": True,
            "manifest_yaml": yaml_text,
        }


def _slug_from_state(metadata: dict[str, Any]) -> str:
    raw = str(metadata.get("connector_id") or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if not cleaned or not _SLUG_RE.match(cleaned):
        raise HTTPException(status_code=400, detail="invalid connector_id slug")
    return cleaned


def _clean_connector_id(connector_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]+", "", str(connector_id or "").strip().lower())
    if not cleaned:
        raise HTTPException(status_code=400, detail="invalid connector_id")
    return cleaned


def _ensure_userland_init() -> None:
    """Make sure the userland package is importable."""
    init = _FETCHER_USERLAND_DIR / "__init__.py"
    if init.exists():
        return
    _FETCHER_USERLAND_DIR.mkdir(parents=True, exist_ok=True)
    init.write_text(
        '"""User-generated Airbyte builder fetchers (data fabric phase 2)."""\n',
        encoding="utf-8",
    )


def _persist_fetcher_path(
    connector_id: str | None, path: str, state: dict[str, Any]
) -> None:
    if not connector_id:
        return
    cleaned = _clean_connector_id(connector_id)
    try:
        with get_session() as session:
            row = session.execute(
                select(AirbyteConnectorRow).where(AirbyteConnectorRow.connector_id == cleaned).limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = AirbyteConnectorRow(
                    connector_id=cleaned,
                    name=str((state.get("metadata") or {}).get("display_name") or cleaned),
                    kind="source",
                    runtime="hybrid",
                    config_schema={},
                    streams=[],
                )
                session.add(row)
            module_path = (
                "aqp.data.fetchers.userland."
                + os.path.splitext(os.path.basename(path))[0]
            )
            row.aqp_fetcher_path = module_path
            row.builder_state_json = state
            session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("aqp_fetcher_path persist failed for %s", cleaned, exc_info=True)
