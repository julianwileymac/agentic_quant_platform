"""Local dbt + DuckDB project endpoints."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.dbt import (
    DbtExportOptions,
    DbtExporter,
    DbtProjectManager,
    DbtRunnerService,
    artifact_paths,
    load_manifest_models,
    load_model_detail,
    load_run_results,
)
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog
from aqp.persistence.models_dbt import (
    DbtModelVersionRow,
    DbtProjectRow,
    DbtRunRow,
    DbtSourceMappingRow,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dbt", tags=["dbt"])


class BootstrapRequest(BaseModel):
    force: bool = False


class ExportRequest(BaseModel):
    include_dataset_models: bool = True
    include_platform_tables: bool = True
    force_project: bool = False
    selected_tables: list[str] = Field(default_factory=list)


class DbtCommandRequest(BaseModel):
    select: list[str] = Field(default_factory=list)
    inline: str | None = None
    limit: int = Field(default=50, ge=1, le=1000)
    triggered_by: str | None = None


class FileWriteRequest(BaseModel):
    path: str
    content: str


@router.get("/project")
def get_project() -> dict[str, Any]:
    manager = DbtProjectManager.from_settings()
    return {
        **manager.status().to_dict(),
        "artifacts": artifact_paths(manager.project_dir),
        "files": manager.list_files(),
    }


@router.post("/project/bootstrap")
def bootstrap_project(payload: BootstrapRequest | None = None) -> dict[str, Any]:
    manager = DbtProjectManager.from_settings()
    result = manager.ensure_project(force=bool(payload.force if payload else False))
    _persist_project(manager)
    return result


@router.post("/export")
def export_project(payload: ExportRequest | None = None) -> dict[str, Any]:
    manager = DbtProjectManager.from_settings()
    opts = payload or ExportRequest()
    exporter = DbtExporter(manager)
    selected = opts.selected_tables or []
    result = exporter.export(
        DbtExportOptions(
            include_dataset_models=opts.include_dataset_models,
            include_platform_tables=opts.include_platform_tables,
            force_project=opts.force_project,
            selected_tables=selected or DbtExportOptions().selected_tables,
        )
    )
    project_id = _persist_project(manager)
    _persist_export_mappings(project_id)
    return {"status": "ok", "project": manager.status().to_dict(), "export": result.to_dict()}


@router.get("/models")
def list_models() -> list[dict[str, Any]]:
    manager = DbtProjectManager.from_settings()
    return load_manifest_models(manager.project_dir)


@router.get("/models/{unique_id:path}")
def get_model(unique_id: str) -> dict[str, Any]:
    manager = DbtProjectManager.from_settings()
    detail = load_model_detail(unique_id, manager.project_dir)
    if detail is None:
        raise HTTPException(status_code=404, detail="dbt model not found")
    return detail


@router.post("/parse")
def parse_project(payload: DbtCommandRequest | None = None) -> dict[str, Any]:
    return _invoke_dbt("parse", payload or DbtCommandRequest()).to_dict()


@router.post("/build")
def build_project(payload: DbtCommandRequest) -> dict[str, Any]:
    return _invoke_dbt("build", payload).to_dict()


@router.post("/test")
def test_project(payload: DbtCommandRequest) -> dict[str, Any]:
    return _invoke_dbt("test", payload).to_dict()


@router.post("/compile")
def compile_project(payload: DbtCommandRequest) -> dict[str, Any]:
    return _invoke_dbt("compile", payload).to_dict()


@router.post("/show")
def show_project(payload: DbtCommandRequest) -> dict[str, Any]:
    return _invoke_dbt("show", payload).to_dict()


@router.get("/runs/latest")
def latest_run_results() -> dict[str, Any]:
    manager = DbtProjectManager.from_settings()
    return load_run_results(manager.project_dir)


@router.get("/files")
def list_or_read_files(
    path: Annotated[str | None, Query()] = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    manager = DbtProjectManager.from_settings()
    try:
        return manager.read_file(path) if path else manager.list_files()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="dbt file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/files")
def write_file(payload: FileWriteRequest) -> dict[str, Any]:
    manager = DbtProjectManager.from_settings()
    try:
        return manager.write_file(payload.path, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _invoke_dbt(command: str, payload: DbtCommandRequest):
    manager = DbtProjectManager.from_settings()
    runner = DbtRunnerService(manager)
    project_id = _persist_project(manager)
    started = datetime.utcnow()
    run_id = _start_run(project_id, command, payload, started)

    if command == "parse":
        result = runner.parse()
    elif command == "build":
        result = runner.build(select=payload.select)
    elif command == "test":
        result = runner.test(select=payload.select)
    elif command == "compile":
        result = runner.compile(select=payload.select)
    elif command == "show":
        result = runner.show(select=payload.select, inline=payload.inline, limit=payload.limit)
    else:
        raise HTTPException(status_code=400, detail=f"unsupported dbt command: {command}")

    _finish_run(run_id, result, started)
    _persist_model_versions(project_id, result.models)
    return result


def _persist_project(manager: DbtProjectManager) -> str | None:
    try:
        with get_session() as session:
            row = session.execute(
                select(DbtProjectRow)
                .where(DbtProjectRow.name == "aqp")
                .where(DbtProjectRow.project_dir == str(manager.project_dir))
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                row = DbtProjectRow(
                    name="aqp",
                    project_dir=str(manager.project_dir),
                    profiles_dir=str(manager.profiles_dir),
                    target=manager.target,
                    adapter="duckdb",
                    duckdb_path=str(manager.duckdb_path),
                    generated_schema=manager.generated_schema,
                    generated_tag=manager.generated_tag,
                    meta={"export_dir": str(manager.export_dir)},
                )
            else:
                row.profiles_dir = str(manager.profiles_dir)
                row.target = manager.target
                row.duckdb_path = str(manager.duckdb_path)
                row.generated_schema = manager.generated_schema
                row.generated_tag = manager.generated_tag
                row.updated_at = datetime.utcnow()
                row.meta = {**(row.meta or {}), "export_dir": str(manager.export_dir)}
            session.add(row)
            session.flush()
            return str(row.id)
    except Exception:  # noqa: BLE001
        logger.debug("dbt project persistence skipped", exc_info=True)
        return None


def _start_run(
    project_id: str | None,
    command: str,
    payload: DbtCommandRequest,
    started: datetime,
) -> str | None:
    try:
        with get_session() as session:
            row = DbtRunRow(
                project_id=project_id,
                command=command,
                selector=list(payload.select),
                status="running",
                started_at=started,
                triggered_by=payload.triggered_by,
            )
            session.add(row)
            session.flush()
            return str(row.id)
    except Exception:  # noqa: BLE001
        logger.debug("dbt run start persistence skipped", exc_info=True)
        return None


def _finish_run(run_id: str | None, result: Any, started: datetime) -> None:
    if not run_id:
        return
    finished = datetime.utcnow()
    try:
        with get_session() as session:
            row = session.get(DbtRunRow, run_id)
            if row is None:
                return
            row.status = "ok" if result.success else "error"
            row.success = bool(result.success)
            row.finished_at = finished
            row.duration_seconds = (finished - started).total_seconds()
            row.artifacts = dict(result.artifacts)
            row.args = list(result.args)
            row.run_results = dict(result.run_results)
            row.error = result.exception
            row.models_count = len(result.models)
            session.add(row)
    except Exception:  # noqa: BLE001
        logger.debug("dbt run finish persistence skipped", exc_info=True)


def _persist_model_versions(project_id: str | None, models: list[dict[str, Any]]) -> None:
    if not project_id or not models:
        return
    try:
        with get_session() as session:
            for model in models:
                row = DbtModelVersionRow(
                    project_id=project_id,
                    unique_id=str(model.get("unique_id") or ""),
                    name=str(model.get("name") or ""),
                    resource_type=str(model.get("resource_type") or "model"),
                    package_name=model.get("package_name"),
                    original_file_path=model.get("original_file_path"),
                    database=model.get("database"),
                    schema=model.get("schema"),
                    alias=model.get("alias"),
                    materialized=model.get("materialized"),
                    checksum=(model.get("raw") or {}).get("checksum"),
                    tags=list(model.get("tags") or []),
                    depends_on=list(model.get("depends_on") or []),
                    columns=list(model.get("columns") or []),
                    raw=dict(model),
                )
                session.add(row)
    except Exception:  # noqa: BLE001
        logger.debug("dbt model version persistence skipped", exc_info=True)


def _persist_export_mappings(project_id: str | None) -> None:
    if not project_id:
        return
    try:
        with get_session() as session:
            datasets = session.execute(select(DatasetCatalog)).scalars().all()
            for dataset in datasets:
                identifier = dataset.iceberg_identifier or dataset.name or dataset.id
                unique_id = f"model.aqp_dbt.dataset_{_slugify(str(identifier))}"
                row = session.execute(
                    select(DbtSourceMappingRow)
                    .where(DbtSourceMappingRow.project_id == project_id)
                    .where(DbtSourceMappingRow.dbt_unique_id == unique_id)
                    .where(DbtSourceMappingRow.source_kind == "dataset")
                    .where(DbtSourceMappingRow.source_name == str(identifier))
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    row = DbtSourceMappingRow(
                        project_id=project_id,
                        dbt_unique_id=unique_id,
                        source_kind="dataset",
                        source_name=str(identifier),
                    )
                row.dataset_catalog_id = dataset.id
                row.iceberg_identifier = dataset.iceberg_identifier
                row.storage_uri = dataset.storage_uri
                row.meta = {"source_uri": dataset.source_uri, "provider": dataset.provider}
                dataset.meta = {
                    **(dataset.meta or {}),
                    "dbt": {"unique_id": unique_id, "project": "aqp"},
                }
                dataset.updated_at = datetime.utcnow()
                session.add(row)
                session.add(dataset)
    except Exception:  # noqa: BLE001
        logger.debug("dbt source mapping persistence skipped", exc_info=True)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    if not slug:
        return "unnamed"
    if slug[0].isdigit():
        return f"n_{slug}"
    return slug
