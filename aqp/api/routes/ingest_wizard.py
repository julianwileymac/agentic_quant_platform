"""Guided ingest wizard orchestration endpoints.

These routes provide a single control surface for the Vite Data Ingest
wizard while delegating real execution to existing battle-tested routes
(``/sources``, ``/dataset-presets``, ``/pipelines``, ``/engine``).
"""
from __future__ import annotations

import logging
from datetime import datetime
from math import inf
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.routes import (
    compute as compute_routes,
    data_pipelines as pipelines_routes,
    monitoring as monitoring_routes,
    sources as sources_routes,
)
from aqp.config import settings
from aqp.data.compute.selection import SizeHint, pick_backend
from aqp.data.dataset_presets import list_presets
from aqp.data.engine.manifest import ComputeBackendKind, ComputeSpec
from aqp.data.loading_templates import list_loading_templates
from aqp.data.sources.registry import get_data_source, list_data_sources
from aqp.data.sources.setup_wizards import list_wizards
from aqp.services import service_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest/wizard", tags=["ingest-wizard"])


Severity = Literal["info", "warn", "error"]
QueuePressure = Literal["low", "moderate", "high"]


class QueueSnapshot(BaseModel):
    workers_seen: int = 0
    active: int = 0
    reserved: int = 0
    scheduled: int = 0
    queued: int = 0
    total: int = 0
    ingestion_active: int = 0
    ingestion_reserved: int = 0
    ingestion_scheduled: int = 0
    ingestion_queued: int = 0


class BootstrapResponse(BaseModel):
    generated_at: datetime
    sources: list[dict[str, Any]] = Field(default_factory=list)
    source_wizards: list[dict[str, Any]] = Field(default_factory=list)
    dataset_presets: list[dict[str, Any]] = Field(default_factory=list)
    loading_templates: list[dict[str, Any]] = Field(default_factory=list)
    service_health: dict[str, Any] = Field(default_factory=dict)
    compute_status: dict[str, Any] = Field(default_factory=dict)
    queue: QueueSnapshot = Field(default_factory=QueueSnapshot)


class ImportProbeInput(BaseModel):
    raw_source_url: str | None = None
    uri: str | None = None
    reference_path: str | None = None
    timeout_s: float = Field(default=5.0, ge=0.5, le=30.0)


class PreflightRequest(BaseModel):
    source_name: str | None = None
    source_wizard_step_id: str | None = None
    source_wizard_payload: dict[str, Any] = Field(default_factory=dict)
    preset_name: str | None = None
    template_id: str | None = None
    template_overrides: dict[str, Any] = Field(default_factory=dict)
    import_probe: ImportProbeInput | None = None
    required_credentials: list[str] = Field(default_factory=list)
    run_service_health: bool = True
    run_compute_status: bool = True
    run_queue_snapshot: bool = True
    run_source_probe: bool = True
    run_template_dry_run: bool = False


class PreflightCheckResult(BaseModel):
    check_id: str
    ok: bool
    severity: Severity = "info"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PreflightResponse(BaseModel):
    generated_at: datetime
    ok: bool
    checks: list[PreflightCheckResult] = Field(default_factory=list)
    queue: QueueSnapshot | None = None


class Advisory(BaseModel):
    severity: Severity = "info"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RecommendRequest(BaseModel):
    source_name: str | None = None
    requested_backend: str = Field(default=ComputeBackendKind.AUTO.value)
    estimated_rows: int = Field(default=0, ge=0)
    estimated_bytes: int = Field(default=0, ge=0)
    symbol_count: int = Field(default=0, ge=0)
    desired_rpm: float | None = Field(default=None, ge=0)
    schedule_cron: str | None = None


class ComputeRecommendation(BaseModel):
    requested_backend: str
    backend: str
    chunk_rows: int
    max_concurrent_pipelines: int
    dask_address: str | None = None
    ray_address: str | None = None
    rationale: list[str] = Field(default_factory=list)


class QueueRecommendation(BaseModel):
    pressure: QueuePressure
    recommended_parallel_runs: int
    recommended_spacing_seconds: float
    rationale: list[str] = Field(default_factory=list)


class RateLimitRecommendation(BaseModel):
    source_name: str | None = None
    provider_rpm: float | None = None
    provider_daily: int | None = None
    desired_rpm: float | None = None
    recommended_rpm: float | None = None
    rationale: list[str] = Field(default_factory=list)


class RecommendResponse(BaseModel):
    generated_at: datetime
    queue: QueueSnapshot
    compute: ComputeRecommendation
    queue_strategy: QueueRecommendation
    rate_limit: RateLimitRecommendation
    advisories: list[Advisory] = Field(default_factory=list)


def _queue_snapshot() -> QueueSnapshot:
    runs = monitoring_routes.list_runs()
    ingestion_active = 0
    ingestion_reserved = 0
    ingestion_scheduled = 0
    for row in runs.active:
        if row.queue == "ingestion":
            ingestion_active += 1
    for row in runs.reserved:
        if row.queue == "ingestion":
            ingestion_reserved += 1
    for row in runs.scheduled:
        if row.queue == "ingestion":
            ingestion_scheduled += 1
    return QueueSnapshot(
        workers_seen=int(runs.workers_seen),
        active=len(runs.active),
        reserved=len(runs.reserved),
        scheduled=len(runs.scheduled),
        queued=int(runs.totals.get("queued", 0)),
        total=int(runs.totals.get("all", 0)),
        ingestion_active=ingestion_active,
        ingestion_reserved=ingestion_reserved,
        ingestion_scheduled=ingestion_scheduled,
        ingestion_queued=ingestion_reserved + ingestion_scheduled,
    )


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _safe_int(value: Any) -> int | None:
    out = _safe_float(value)
    if out is None:
        return None
    return int(out)


def _extract_rate_limits(raw_limits: dict[str, Any] | None) -> tuple[float | None, int | None]:
    limits = dict(raw_limits or {})
    rpm = None
    daily = None
    for key in (
        "rpm",
        "requests_per_minute",
        "calls_per_minute",
        "per_minute",
        "minute",
    ):
        rpm = _safe_float(limits.get(key))
        if rpm is not None:
            break
    for key in (
        "daily",
        "requests_per_day",
        "calls_per_day",
        "per_day",
        "day",
    ):
        daily = _safe_int(limits.get(key))
        if daily is not None:
            break
    return rpm, daily


def _queue_strategy(snapshot: QueueSnapshot) -> QueueRecommendation:
    max_parallel = max(1, int(settings.engine_max_concurrent_pipelines or 1))
    high_threshold = max_parallel * 4
    moderate_threshold = max_parallel * 2
    pressure: QueuePressure
    rationale: list[str] = []
    if snapshot.ingestion_queued >= high_threshold or snapshot.ingestion_active >= high_threshold:
        pressure = "high"
        recommended_parallel = 1
        spacing = 60.0
        rationale.append(
            "Ingestion queue pressure is high relative to engine max concurrency."
        )
    elif snapshot.ingestion_queued >= moderate_threshold or snapshot.ingestion_active >= moderate_threshold:
        pressure = "moderate"
        recommended_parallel = max(1, max_parallel // 2)
        spacing = 20.0
        rationale.append(
            "Ingestion queue pressure is moderate; reduce fan-out to avoid backlog."
        )
    else:
        pressure = "low"
        recommended_parallel = max_parallel
        spacing = 5.0
        rationale.append("Queue pressure is low; normal fan-out is safe.")
    return QueueRecommendation(
        pressure=pressure,
        recommended_parallel_runs=recommended_parallel,
        recommended_spacing_seconds=spacing,
        rationale=rationale,
    )


def _requested_backend(value: str) -> ComputeBackendKind:
    try:
        return ComputeBackendKind(value)
    except ValueError:
        return ComputeBackendKind.AUTO


def _compute_recommendation(
    *,
    requested_backend: ComputeBackendKind,
    estimated_rows: int,
    estimated_bytes: int,
    compute_status: dict[str, Any],
) -> tuple[ComputeRecommendation, list[Advisory]]:
    advisories: list[Advisory] = []
    hint = SizeHint(rows=int(estimated_rows or 0), bytes=int(estimated_bytes or 0))
    spec = pick_backend(
        hint=hint,
        requested=requested_backend,
        spec=ComputeSpec(backend=requested_backend),
    )
    rationale: list[str] = []
    if hint.rows:
        rationale.append(f"Estimated rows: {hint.rows:,}")
    if hint.bytes:
        rationale.append(f"Estimated bytes: {hint.bytes:,}")
    if spec.backend == ComputeBackendKind.DASK:
        dask_available = bool(
            ((compute_status.get("dask") or {}).get("available"))
        )
        if not dask_available:
            advisories.append(
                Advisory(
                    severity="warn",
                    message="Dask recommended by size hint, but dask backend is unavailable; falling back to local.",
                )
            )
            spec.backend = ComputeBackendKind.LOCAL
            spec.dask_address = None
    if spec.backend == ComputeBackendKind.RAY:
        ray_available = bool(
            ((compute_status.get("ray") or {}).get("available"))
        )
        if not ray_available:
            advisories.append(
                Advisory(
                    severity="warn",
                    message="Ray recommended by size hint, but ray backend is unavailable; falling back to local.",
                )
            )
            spec.backend = ComputeBackendKind.LOCAL
            spec.ray_address = None
    rec = ComputeRecommendation(
        requested_backend=requested_backend.value,
        backend=spec.backend.value,
        chunk_rows=int(spec.chunk_rows),
        max_concurrent_pipelines=int(spec.max_concurrent_pipelines),
        dask_address=spec.dask_address,
        ray_address=spec.ray_address,
        rationale=rationale,
    )
    return rec, advisories


@router.get("/bootstrap", response_model=BootstrapResponse)
def bootstrap() -> BootstrapResponse:
    """Aggregate wizard dependencies into one bootstrap payload."""
    try:
        queue = _queue_snapshot()
    except Exception:
        logger.exception("ingest wizard bootstrap queue snapshot failed")
        queue = QueueSnapshot()
    try:
        sources = list_data_sources(enabled_only=False)
    except Exception:
        logger.exception("ingest wizard bootstrap sources failed")
        sources = []
    try:
        source_wizards = [wizard.to_dict() for wizard in list_wizards()]
    except Exception:
        logger.exception("ingest wizard bootstrap source wizards failed")
        source_wizards = []
    try:
        presets = [preset.to_dict() for preset in list_presets()]
    except Exception:
        logger.exception("ingest wizard bootstrap presets failed")
        presets = []
    try:
        templates = [template.model_dump(mode="json") for template in list_loading_templates()]
    except Exception:
        logger.exception("ingest wizard bootstrap loading templates failed")
        templates = []
    try:
        services = service_manager.health()
    except Exception:
        logger.exception("ingest wizard bootstrap service health failed")
        services = {"ok": False, "services": {}, "config": {}}
    try:
        compute = compute_routes.status()
    except Exception:
        logger.exception("ingest wizard bootstrap compute status failed")
        compute = {}
    return BootstrapResponse(
        generated_at=datetime.utcnow(),
        sources=sources,
        source_wizards=source_wizards,
        dataset_presets=presets,
        loading_templates=templates,
        service_health=services,
        compute_status=compute,
        queue=queue,
    )


@router.post("/preflight", response_model=PreflightResponse)
def preflight(payload: PreflightRequest) -> PreflightResponse:
    """Run preflight checks used by the ingest wizard's Test step."""
    checks: list[PreflightCheckResult] = []
    queue_snapshot: QueueSnapshot | None = None

    if payload.run_service_health:
        try:
            service = service_manager.health()
            ok = bool(service.get("ok"))
            checks.append(
                PreflightCheckResult(
                    check_id="service-health",
                    ok=ok,
                    severity="info" if ok else "warn",
                    message="Service health probe passed" if ok else "Some services are degraded",
                    details=service,
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheckResult(
                    check_id="service-health",
                    ok=False,
                    severity="error",
                    message=f"Service health probe failed: {exc}",
                )
            )

    if payload.run_compute_status:
        try:
            status = compute_routes.status()
            checks.append(
                PreflightCheckResult(
                    check_id="compute-status",
                    ok=True,
                    severity="info",
                    message="Compute status fetched",
                    details=status,
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheckResult(
                    check_id="compute-status",
                    ok=False,
                    severity="error",
                    message=f"Compute status failed: {exc}",
                )
            )

    if payload.run_queue_snapshot:
        try:
            queue_snapshot = _queue_snapshot()
            checks.append(
                PreflightCheckResult(
                    check_id="queue-snapshot",
                    ok=True,
                    severity="info",
                    message="Queue snapshot fetched",
                    details=queue_snapshot.model_dump(mode="json"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheckResult(
                    check_id="queue-snapshot",
                    ok=False,
                    severity="error",
                    message=f"Queue snapshot failed: {exc}",
                )
            )

    if payload.source_name:
        source = get_data_source(payload.source_name)
        if source is None:
            checks.append(
                PreflightCheckResult(
                    check_id="source-exists",
                    ok=False,
                    severity="error",
                    message=f"Source {payload.source_name!r} not found",
                )
            )
        else:
            checks.append(
                PreflightCheckResult(
                    check_id="source-exists",
                    ok=True,
                    severity="info",
                    message=f"Source {payload.source_name!r} is registered",
                    details={"source": source},
                )
            )

    if payload.source_name and payload.run_source_probe:
        try:
            probe = sources_routes.probe_source(payload.source_name)
            checks.append(
                PreflightCheckResult(
                    check_id="source-probe",
                    ok=bool(probe.ok),
                    severity="info" if probe.ok else "warn",
                    message=probe.message,
                    details=probe.model_dump(mode="json"),
                )
            )
        except HTTPException as exc:
            checks.append(
                PreflightCheckResult(
                    check_id="source-probe",
                    ok=False,
                    severity="error",
                    message=f"Source probe failed: {exc.detail}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheckResult(
                    check_id="source-probe",
                    ok=False,
                    severity="error",
                    message=f"Source probe failed: {exc}",
                )
            )

    if payload.source_name and payload.source_wizard_step_id:
        wizard = sources_routes.get_setup_wizard(payload.source_name)
        step = next(
            (entry for entry in wizard.steps if entry.id == payload.source_wizard_step_id),
            None,
        )
        if step is None:
            checks.append(
                PreflightCheckResult(
                    check_id="source-wizard-step",
                    ok=False,
                    severity="error",
                    message=(
                        f"Unknown source wizard step {payload.source_wizard_step_id!r} "
                        f"for {payload.source_name!r}"
                    ),
                )
            )
        else:
            result = sources_routes.run_setup_wizard_step(
                payload.source_name,
                sources_routes.SetupWizardStepRequest(
                    step_id=payload.source_wizard_step_id,
                    payload=payload.source_wizard_payload,
                ),
            )
            checks.append(
                PreflightCheckResult(
                    check_id="source-wizard-step",
                    ok=bool(result.ok),
                    severity="info" if result.ok else "warn",
                    message=result.message,
                    details=result.model_dump(mode="json"),
                )
            )

    if payload.import_probe is not None:
        try:
            probe = sources_routes.probe_import(
                sources_routes.ImportProbeRequest(
                    raw_source_url=payload.import_probe.raw_source_url,
                    uri=payload.import_probe.uri,
                    reference_path=payload.import_probe.reference_path,
                    timeout_s=payload.import_probe.timeout_s,
                )
            )
            checks.append(
                PreflightCheckResult(
                    check_id="import-probe",
                    ok=bool(probe.reachable),
                    severity="info" if probe.reachable else "warn",
                    message=probe.message or "Import probe completed",
                    details=probe.model_dump(mode="json"),
                )
            )
        except HTTPException as exc:
            checks.append(
                PreflightCheckResult(
                    check_id="import-probe",
                    ok=False,
                    severity="error",
                    message=f"Import probe failed: {exc.detail}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheckResult(
                    check_id="import-probe",
                    ok=False,
                    severity="error",
                    message=f"Import probe failed: {exc}",
                )
            )

    if payload.template_id and payload.run_template_dry_run:
        try:
            result = pipelines_routes.run_loading_template(
                payload.template_id,
                pipelines_routes.LoadingTemplateRunRequest(
                    overrides=dict(payload.template_overrides),
                    dry_run=True,
                ),
            )
            checks.append(
                PreflightCheckResult(
                    check_id="template-dry-run",
                    ok=True,
                    severity="info",
                    message=f"Template {payload.template_id!r} dry-run succeeded",
                    details=result,
                )
            )
        except HTTPException as exc:
            checks.append(
                PreflightCheckResult(
                    check_id="template-dry-run",
                    ok=False,
                    severity="error",
                    message=f"Template dry-run failed: {exc.detail}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheckResult(
                    check_id="template-dry-run",
                    ok=False,
                    severity="error",
                    message=f"Template dry-run failed: {exc}",
                )
            )

    if payload.required_credentials:
        try:
            credentials = sources_routes.list_credentials()
            configured = {entry.key: bool(entry.configured) for entry in credentials.credentials}
            missing = [key for key in payload.required_credentials if not configured.get(key, False)]
            checks.append(
                PreflightCheckResult(
                    check_id="credential-presence",
                    ok=not missing,
                    severity="info" if not missing else "error",
                    message=(
                        "All required credentials are configured"
                        if not missing
                        else f"Missing required credentials: {', '.join(missing)}"
                    ),
                    details={"missing": missing},
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                PreflightCheckResult(
                    check_id="credential-presence",
                    ok=False,
                    severity="error",
                    message=f"Credential check failed: {exc}",
                )
            )

    ok = all(check.ok for check in checks)
    return PreflightResponse(
        generated_at=datetime.utcnow(),
        ok=ok,
        checks=checks,
        queue=queue_snapshot,
    )


@router.post("/recommend", response_model=RecommendResponse)
def recommend(payload: RecommendRequest) -> RecommendResponse:
    """Produce resource/rate-aware run coordination recommendations."""
    queue = _queue_snapshot()
    services = service_manager.health()
    compute_status = compute_routes.status()
    requested_backend = _requested_backend(payload.requested_backend)
    compute, advisories = _compute_recommendation(
        requested_backend=requested_backend,
        estimated_rows=payload.estimated_rows,
        estimated_bytes=payload.estimated_bytes,
        compute_status=compute_status,
    )
    queue_strategy = _queue_strategy(queue)
    source = get_data_source(payload.source_name) if payload.source_name else None
    source_limits = dict((source or {}).get("rate_limits") or {})
    provider_rpm, provider_daily = _extract_rate_limits(source_limits)
    desired_rpm = payload.desired_rpm
    effective_rpm = min(
        desired_rpm if desired_rpm is not None else inf,
        provider_rpm if provider_rpm is not None else inf,
    )
    if effective_rpm == inf:
        recommended_rpm: float | None = None
    else:
        recommended_rpm = float(max(0.0, effective_rpm))
    rate_rationale: list[str] = []
    if provider_rpm is not None:
        rate_rationale.append(f"Provider limit: {provider_rpm:.2f} RPM")
    if desired_rpm is not None:
        rate_rationale.append(f"Requested throughput: {desired_rpm:.2f} RPM")
    if queue_strategy.pressure == "high":
        if recommended_rpm is None:
            recommended_rpm = 5.0
        else:
            recommended_rpm = min(recommended_rpm, max(1.0, recommended_rpm * 0.5))
        advisories.append(
            Advisory(
                severity="warn",
                message="Queue pressure is high; reduce dispatch rate and parallelism.",
                details={"queue": queue.model_dump(mode="json")},
            )
        )
    elif queue_strategy.pressure == "moderate" and recommended_rpm is not None:
        recommended_rpm = min(recommended_rpm, max(1.0, recommended_rpm * 0.75))
    if provider_rpm is not None and desired_rpm is not None and desired_rpm > provider_rpm:
        advisories.append(
            Advisory(
                severity="warn",
                message="Requested RPM exceeds provider limit; throttling to provider cap.",
                details={"desired_rpm": desired_rpm, "provider_rpm": provider_rpm},
            )
        )
    if not bool(services.get("ok")):
        degraded = [
            name
            for name, state in (services.get("services") or {}).items()
            if not bool((state or {}).get("ok"))
        ]
        advisories.append(
            Advisory(
                severity="warn",
                message="Some platform services are degraded; prefer conservative scheduling.",
                details={"degraded_services": degraded},
            )
        )
    if payload.symbol_count and payload.symbol_count > 1_000:
        advisories.append(
            Advisory(
                severity="info",
                message="Large symbol fan-out detected; consider batching by sector or exchange.",
                details={"symbol_count": payload.symbol_count},
            )
        )
    rate_limit = RateLimitRecommendation(
        source_name=payload.source_name,
        provider_rpm=provider_rpm,
        provider_daily=provider_daily,
        desired_rpm=desired_rpm,
        recommended_rpm=recommended_rpm,
        rationale=rate_rationale,
    )
    return RecommendResponse(
        generated_at=datetime.utcnow(),
        queue=queue,
        compute=compute,
        queue_strategy=queue_strategy,
        rate_limit=rate_limit,
        advisories=advisories,
    )


__all__ = [
    "BootstrapResponse",
    "PreflightCheckResult",
    "PreflightRequest",
    "PreflightResponse",
    "RecommendRequest",
    "RecommendResponse",
    "router",
]
