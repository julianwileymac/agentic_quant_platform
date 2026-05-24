"""``/bots`` — first-class Bot CRUD + lifecycle endpoints.

A :class:`aqp_bots.spec.BotSpec` is the smallest self-contained,
deployable unit on AQP. Each row in the ``bots`` table corresponds to
one named spec inside a project; ``bot_versions`` carries an immutable
hash-locked snapshot per change; ``bot_deployments`` ledgers every run
(backtest / paper / chat / k8s deploy).

Naming
------

Endpoints follow the existing tenancy-routes shape (see
:mod:`aqp.api.routes.projects`): mutations are async-session backed,
read-only listings drop into the same pattern, and lifecycle actions
hand off to Celery tasks under :mod:`aqp.tasks.bot_tasks`.

Streaming
---------

Async lifecycle actions return a :class:`aqp.api.schemas.TaskAccepted`
with ``stream_url`` pointing at the existing
``/chat/stream/{task_id}`` WebSocket — no new transport.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aqp.api.security import secure_router
from aqp.api.schemas import TaskAccepted
from aqp_bots.spec import BotSpec
from aqp.persistence import async_session_dep
from aqp.persistence.models_bots import Bot as BotRow
from aqp.persistence.models_bots import BotDeployment, BotVersion

logger = logging.getLogger(__name__)

router = secure_router(prefix="/bots", tags=["bots"], default_scope="trade:read")


# ----------------------------------------------------------------- schemas


class BotSummary(BaseModel):
    id: str
    name: str
    slug: str
    kind: str
    description: str | None = None
    status: str
    current_version: int
    project_id: str | None = None
    workspace_id: str | None = None
    annotations: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BotDetail(BotSummary):
    spec: dict[str, Any] = Field(default_factory=dict)
    spec_yaml: str | None = None


class BotCreate(BaseModel):
    spec: dict[str, Any]
    project_id: str | None = None


class BotUpdate(BaseModel):
    spec: dict[str, Any] | None = None
    spec_yaml: str | None = None
    status: str | None = None
    description: str | None = None


class BotVersionOut(BaseModel):
    id: str
    bot_id: str
    version: int
    spec_hash: str
    created_at: datetime
    notes: str | None = None


class BotDeploymentOut(BaseModel):
    id: str
    bot_id: str | None
    version_id: str | None
    target: str
    status: str
    task_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    error: str | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)


class BotBacktestRequest(BaseModel):
    run_name: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class BotPaperRequest(BaseModel):
    run_name: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class BotDeployRequest(BaseModel):
    target: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class BotChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    agent_role: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


# ----------------------------------------------------------------- helpers


def _to_summary(row: BotRow) -> BotSummary:
    return BotSummary(
        id=row.id,
        name=row.name,
        slug=row.slug,
        kind=row.kind,
        description=row.description,
        status=row.status,
        current_version=int(row.current_version or 1),
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        annotations=list(row.annotations or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_detail(row: BotRow) -> BotDetail:
    spec_payload: dict[str, Any] = {}
    if row.spec_yaml:
        try:
            spec_payload = BotSpec.from_yaml_str(row.spec_yaml).model_dump(mode="json")
        except Exception:
            spec_payload = {}
    return BotDetail(
        id=row.id,
        name=row.name,
        slug=row.slug,
        kind=row.kind,
        description=row.description,
        status=row.status,
        current_version=int(row.current_version or 1),
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        annotations=list(row.annotations or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        spec=spec_payload,
        spec_yaml=row.spec_yaml,
    )


async def _get_row(session: AsyncSession, bot_ref: str) -> BotRow:
    """Resolve a bot by id (UUID-ish) or slug, raise 404 if missing."""
    if len(bot_ref) == 36 and bot_ref.count("-") == 4:
        row = await session.get(BotRow, bot_ref)
        if row is not None:
            return row
    stmt = select(BotRow).where(BotRow.slug == bot_ref)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"bot {bot_ref!r} not found")
    return row


def _validate_spec_payload(payload: dict[str, Any]) -> BotSpec:
    try:
        return BotSpec.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"invalid bot spec: {exc}") from exc


# ----------------------------------------------------------------- CRUD


@router.get("", response_model=list[BotSummary])
async def list_bots(
    project_id: str | None = None,
    kind: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(async_session_dep),
) -> list[BotSummary]:
    stmt = select(BotRow).order_by(BotRow.updated_at.desc()).limit(min(max(limit, 1), 500))
    if project_id:
        stmt = stmt.where(BotRow.project_id == project_id)
    if kind:
        stmt = stmt.where(BotRow.kind == kind)
    if status_filter:
        stmt = stmt.where(BotRow.status == status_filter)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_summary(r) for r in rows]


@router.post("", response_model=BotDetail, status_code=status.HTTP_201_CREATED)
async def create_bot(
    body: BotCreate,
    session: AsyncSession = Depends(async_session_dep),
) -> BotDetail:
    spec = _validate_spec_payload(body.spec)
    if not spec.slug:
        raise HTTPException(status_code=422, detail="bot spec must have a non-empty slug")

    existing = (
        await session.execute(
            select(BotRow).where(
                BotRow.slug == spec.slug,
                BotRow.project_id == (body.project_id or BotRow.project_id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"bot with slug {spec.slug!r} already exists in this project",
        )

    row = BotRow(
        name=spec.name,
        slug=spec.slug,
        kind=spec.kind,
        description=spec.description,
        status="draft",
        current_version=1,
        spec_yaml=spec.to_yaml(),
        annotations=spec.annotations,
    )
    if body.project_id:
        row.project_id = body.project_id
    session.add(row)
    await session.flush()

    version_row = BotVersion(
        bot_id=row.id,
        version=1,
        spec_hash=spec.snapshot_hash(),
        payload=spec.model_dump(mode="json"),
    )
    if body.project_id:
        version_row.project_id = body.project_id
    session.add(version_row)
    await session.commit()
    await session.refresh(row)
    return _to_detail(row)


@router.get("/{bot_ref}", response_model=BotDetail)
async def get_bot(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> BotDetail:
    row = await _get_row(session, bot_ref)
    return _to_detail(row)


@router.put("/{bot_ref}", response_model=BotDetail)
async def update_bot(
    bot_ref: str,
    body: BotUpdate,
    session: AsyncSession = Depends(async_session_dep),
) -> BotDetail:
    row = await _get_row(session, bot_ref)
    spec_dirty = False

    if body.spec is not None:
        spec = _validate_spec_payload(body.spec)
        row.name = spec.name
        row.kind = spec.kind
        row.description = spec.description
        row.spec_yaml = spec.to_yaml()
        row.annotations = spec.annotations
        spec_dirty = True
    elif body.spec_yaml is not None:
        try:
            spec = BotSpec.from_yaml_str(body.spec_yaml)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"invalid spec_yaml: {exc}") from exc
        row.name = spec.name
        row.kind = spec.kind
        row.description = spec.description
        row.spec_yaml = body.spec_yaml
        row.annotations = spec.annotations
        spec_dirty = True
    else:
        spec = None

    if body.status is not None:
        row.status = body.status
    if body.description is not None and not spec_dirty:
        row.description = body.description

    if spec is not None and spec_dirty:
        sha = spec.snapshot_hash()
        existing_version = (
            await session.execute(
                select(BotVersion).where(BotVersion.bot_id == row.id, BotVersion.spec_hash == sha)
            )
        ).scalar_one_or_none()
        if existing_version is None:
            next_version = int(row.current_version or 0) + 1
            version_row = BotVersion(
                bot_id=row.id,
                version=next_version,
                spec_hash=sha,
                payload=spec.model_dump(mode="json"),
            )
            if row.project_id:
                version_row.project_id = row.project_id
            session.add(version_row)
            row.current_version = next_version

    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_detail(row)


@router.delete(
    "/{bot_ref}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_bot(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> None:
    row = await _get_row(session, bot_ref)
    await session.delete(row)
    await session.commit()


# ----------------------------------------------------------------- versions


@router.get("/{bot_ref}/versions", response_model=list[BotVersionOut])
async def list_bot_versions(
    bot_ref: str,
    limit: int = 50,
    session: AsyncSession = Depends(async_session_dep),
) -> list[BotVersionOut]:
    row = await _get_row(session, bot_ref)
    stmt = (
        select(BotVersion)
        .where(BotVersion.bot_id == row.id)
        .order_by(desc(BotVersion.version))
        .limit(min(max(limit, 1), 500))
    )
    versions = (await session.execute(stmt)).scalars().all()
    return [
        BotVersionOut(
            id=v.id,
            bot_id=v.bot_id,
            version=v.version,
            spec_hash=v.spec_hash,
            created_at=v.created_at,
            notes=v.notes,
        )
        for v in versions
    ]


# ----------------------------------------------------------------- deployments


@router.get("/{bot_ref}/deployments", response_model=list[BotDeploymentOut])
async def list_bot_deployments(
    bot_ref: str,
    limit: int = 50,
    session: AsyncSession = Depends(async_session_dep),
) -> list[BotDeploymentOut]:
    row = await _get_row(session, bot_ref)
    stmt = (
        select(BotDeployment)
        .where(BotDeployment.bot_id == row.id)
        .order_by(desc(BotDeployment.started_at))
        .limit(min(max(limit, 1), 500))
    )
    deployments = (await session.execute(stmt)).scalars().all()
    return [
        BotDeploymentOut(
            id=d.id,
            bot_id=d.bot_id,
            version_id=d.version_id,
            target=d.target,
            status=d.status,
            task_id=d.task_id,
            started_at=d.started_at,
            ended_at=d.ended_at,
            error=d.error,
            result_summary=d.result_summary or {},
        )
        for d in deployments
    ]


# ----------------------------------------------------------------- lifecycle


@router.post("/{bot_ref}/backtest", response_model=TaskAccepted)
async def backtest_bot(
    bot_ref: str,
    body: BotBacktestRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    row = await _get_row(session, bot_ref)
    body = body or BotBacktestRequest()
    from aqp.tasks.bot_tasks import run_bot_backtest

    handle = run_bot_backtest.delay(
        row.id,
        run_name=body.run_name,
        overrides=body.overrides,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")


@router.post("/{bot_ref}/paper/start", response_model=TaskAccepted)
async def start_bot_paper(
    bot_ref: str,
    body: BotPaperRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    row = await _get_row(session, bot_ref)
    body = body or BotPaperRequest()
    from aqp.tasks.bot_tasks import run_bot_paper

    handle = run_bot_paper.delay(
        row.id,
        run_name=body.run_name,
        overrides=body.overrides,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")


@router.post("/{bot_ref}/paper/stop/{task_id}")
async def stop_bot_paper(bot_ref: str, task_id: str) -> dict[str, Any]:
    """Send a stop signal to an in-flight paper session.

    Reuses :func:`aqp.tasks.paper_tasks.publish_stop_signal` so existing
    paper-stop infrastructure (Redis pub/sub) covers bots transparently.
    """
    from aqp.tasks.paper_tasks import publish_stop_signal

    publish_stop_signal(task_id, reason=f"bot:{bot_ref}:manual")
    return {"task_id": task_id, "bot": bot_ref, "ok": True}


@router.post("/{bot_ref}/deploy", response_model=TaskAccepted)
async def deploy_bot_route(
    bot_ref: str,
    body: BotDeployRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    row = await _get_row(session, bot_ref)
    body = body or BotDeployRequest()
    from aqp.tasks.bot_tasks import deploy_bot as deploy_task

    handle = deploy_task.delay(
        row.id,
        target=body.target,
        overrides=body.overrides,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")


@router.post("/halt-all")
async def halt_all_bots(
    session: AsyncSession = Depends(async_session_dep),
) -> dict[str, Any]:
    """Halt every active bot deployment.

    Idempotent kill-switch fan-out target. Selects every
    :class:`BotDeployment` with ``status in {pending, running}`` and a
    populated ``task_id`` and revokes the underlying Celery task. For
    ``target='paper'`` deployments we additionally publish the stop
    signal so the long-running paper session loop drains gracefully.
    """
    from aqp.tasks.celery_app import celery_app as _celery
    from aqp.tasks.paper_tasks import publish_stop_signal

    revoked: list[str] = []
    paper_signals: list[str] = []
    failed: list[dict[str, str]] = []

    rows = (
        (
            await session.execute(
                select(BotDeployment).where(BotDeployment.status.in_(["pending", "running"]))
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        tid = (row.task_id or "").strip()
        if not tid:
            continue
        try:
            _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
            revoked.append(tid)
        except Exception as exc:  # noqa: BLE001
            failed.append({"task_id": tid, "error": str(exc)})
        if (row.target or "").lower() == "paper":
            try:
                publish_stop_signal(tid, reason="bots.halt-all: kill_switch fanout")
                paper_signals.append(tid)
            except Exception as exc:  # noqa: BLE001
                failed.append({"task_id": tid, "error": f"paper-stop: {exc}"})
        row.status = "halted"
        row.error = (row.error or "") + "\nhalted by kill switch"
    await session.commit()

    return {
        "stopped": len(revoked),
        "task_ids": revoked,
        "paper_stop_signals": paper_signals,
        "failures": failed,
    }


@router.post("/{bot_ref}/halt")
async def halt_bot(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> dict[str, Any]:
    """Halt every active deployment for a single bot.

    Wired to the per-bot ``BotsApi.halt`` button in
    ``aqp_client/src/lib/api/bots.ts``. Mirrors :func:`halt_all_bots`
    but scopes the revoke fan-out to one bot's deployments.
    """
    from aqp.tasks.celery_app import celery_app as _celery
    from aqp.tasks.paper_tasks import publish_stop_signal

    row = await _get_row(session, bot_ref)
    revoked: list[str] = []
    paper_signals: list[str] = []
    failed: list[dict[str, str]] = []

    deployments = (
        (
            await session.execute(
                select(BotDeployment).where(
                    BotDeployment.bot_id == row.id,
                    BotDeployment.status.in_(["pending", "running"]),
                )
            )
        )
        .scalars()
        .all()
    )
    for d in deployments:
        tid = (d.task_id or "").strip()
        if not tid:
            continue
        try:
            _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
            revoked.append(tid)
        except Exception as exc:  # noqa: BLE001
            failed.append({"task_id": tid, "error": str(exc)})
        if (d.target or "").lower() == "paper":
            try:
                publish_stop_signal(tid, reason=f"bot:{bot_ref}:halt")
                paper_signals.append(tid)
            except Exception as exc:  # noqa: BLE001
                failed.append({"task_id": tid, "error": f"paper-stop: {exc}"})
        d.status = "halted"
        d.error = (d.error or "") + "\nhalted by per-bot halt"
    await session.commit()

    return {
        "bot": bot_ref,
        "stopped": len(revoked),
        "task_ids": revoked,
        "paper_stop_signals": paper_signals,
        "failures": failed,
    }


# ----------------------------------------------------------------- QuantBot Platform extensions


class BotReplayRequest(BaseModel):
    since_seq: int = 0
    until_seq: int | None = None
    limit: int | None = None


class BotReplayResponse(BaseModel):
    bot_id: str
    events_seen: int
    final_seq_no: int
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BotConformanceResponse(BaseModel):
    bot: str
    cases_run: int
    cases_passed: int
    cases_failed: list[dict[str, Any]] = Field(default_factory=list)
    passing: bool


class BotStressRequest(BaseModel):
    duration_s: float = 5.0
    rate_multiplier: float = 2.0
    explicit_target_rate: float | None = None


class BotStressResponse(BaseModel):
    bot: str
    target_rate_per_s: float
    throughput_per_s: float
    messages_sent: int
    blocks: int
    warnings: int
    allows: int
    passed: bool


class BotStateSnapshotResponse(BaseModel):
    bot_id: str
    seq_no: int | None = None
    snapshot_at: datetime | None = None
    positions: dict[str, Any] = Field(default_factory=dict)
    exposures: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class BotStateEventOut(BaseModel):
    seq_no: int
    event_type: str
    event_data: dict[str, Any]
    occurred_at: datetime | None = None


@router.post("/{bot_ref}/replay", response_model=BotReplayResponse)
async def replay_bot(
    bot_ref: str,
    body: BotReplayRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> BotReplayResponse:
    """Time-travel replay of bot_events for a single bot."""
    from aqp_bots.state.replay import replay_events

    row = await _get_row(session, bot_ref)
    body = body or BotReplayRequest()

    def _capture(_event_data: dict[str, Any]) -> None:
        return None

    cursor = replay_events(
        bot_id=row.id,
        handlers={"order": _capture, "fill": _capture, "snapshot": _capture},
        since_seq=body.since_seq,
        until_seq=body.until_seq,
        limit=body.limit,
    )
    return BotReplayResponse(
        bot_id=cursor.bot_id,
        events_seen=cursor.events_seen,
        final_seq_no=cursor.final_seq_no,
        skipped=sorted(set(cursor.skipped)),
        errors=cursor.errors,
    )


@router.post("/{bot_ref}/conformance", response_model=BotConformanceResponse)
async def conformance_bot(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> BotConformanceResponse:
    """Run the RTS 6 Article 6 conformance harness against the bot's risk policies."""
    from decimal import Decimal as _Decimal

    from aqp_bots.risk.engine import PreTradeRiskEngine
    from aqp_bots.risk.policies import (
        MaxOrderValuePolicy,
        MaxOrderVolumePolicy,
        PriceCollarPolicy,
    )
    from aqp_bots.risk.reg.conformance import run_conformance_tests

    row = await _get_row(session, bot_ref)
    spec = BotSpec.from_yaml_str(row.spec_yaml) if row.spec_yaml else None
    rl = spec.risk_layer if spec is not None else None
    engine = PreTradeRiskEngine(
        policies=[
            PriceCollarPolicy(max_bps=int((rl.price_collar_bps if rl else None) or 100)),
            MaxOrderValuePolicy(
                max_value_usd=_Decimal(str((rl.max_order_value_usd if rl else None) or "100000"))
            ),
            MaxOrderVolumePolicy(
                max_qty=_Decimal(str((rl.max_order_qty if rl else None) or "10000"))
            ),
        ],
        check_kill_switch=False,
        check_legacy_risk_manager=False,
    )
    result = run_conformance_tests(engine=engine)
    return BotConformanceResponse(
        bot=row.slug,
        cases_run=result.cases_run,
        cases_passed=result.cases_passed,
        cases_failed=result.cases_failed,
        passing=result.is_passing(),
    )


@router.post("/{bot_ref}/stress", response_model=BotStressResponse)
async def stress_bot(
    bot_ref: str,
    body: BotStressRequest | None = None,
    session: AsyncSession = Depends(async_session_dep),
) -> BotStressResponse:
    """Run the RTS 6 Article 10 stress test (2x prior 6-month peak by default)."""
    from decimal import Decimal as _Decimal

    from aqp_bots.risk.engine import PreTradeRiskEngine
    from aqp_bots.risk.policies import MaxOrderValuePolicy, MaxOrderVolumePolicy
    from aqp_bots.risk.reg.stress import run_stress_test

    row = await _get_row(session, bot_ref)
    body = body or BotStressRequest()
    spec = BotSpec.from_yaml_str(row.spec_yaml) if row.spec_yaml else None
    rl = spec.risk_layer if spec is not None else None
    engine = PreTradeRiskEngine(
        policies=[
            MaxOrderValuePolicy(
                max_value_usd=_Decimal(str((rl.max_order_value_usd if rl else None) or "100000"))
            ),
            MaxOrderVolumePolicy(
                max_qty=_Decimal(str((rl.max_order_qty if rl else None) or "10000"))
            ),
        ],
        check_kill_switch=False,
        check_legacy_risk_manager=False,
    )
    result = run_stress_test(
        engine=engine,
        bot_id=row.id,
        duration_s=body.duration_s,
        rate_multiplier=body.rate_multiplier,
        explicit_target_rate=body.explicit_target_rate,
    )
    return BotStressResponse(
        bot=row.slug,
        target_rate_per_s=result.target_rate_per_s,
        throughput_per_s=result.throughput_per_s,
        messages_sent=result.messages_sent,
        blocks=result.blocks,
        warnings=result.warnings,
        allows=result.allows,
        passed=result.passed,
    )


@router.get("/{bot_ref}/risk/validation-report")
async def risk_validation_report(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> dict[str, Any]:
    """Generate the RTS 6 Art. 9 / 15c3-5(e) annual validation report payload."""
    from aqp_bots.risk.reg.validation_report import generate_validation_report

    row = await _get_row(session, bot_ref)
    return generate_validation_report(
        bot_inventory=[
            {
                "slug": row.slug,
                "fleet": (row.annotations or [])[:1] or [""],
                "kind": row.kind,
            }
        ],
    )


@router.get("/{bot_ref}/state/snapshot", response_model=BotStateSnapshotResponse)
async def get_bot_state_snapshot(
    bot_ref: str,
    session: AsyncSession = Depends(async_session_dep),
) -> BotStateSnapshotResponse:
    """Return the latest event-sourced state snapshot for the bot."""
    from aqp_bots.state.snapshots import SnapshotWriter

    row = await _get_row(session, bot_ref)
    writer = SnapshotWriter(bot_id=row.id)
    latest = writer.latest()
    if latest is None:
        return BotStateSnapshotResponse(bot_id=row.id)
    return BotStateSnapshotResponse(
        bot_id=latest.bot_id,
        seq_no=latest.seq_no,
        snapshot_at=latest.snapshot_at,
        positions=latest.positions,
        exposures=latest.exposures,
        metrics=latest.metrics,
    )


@router.get("/{bot_ref}/state/events", response_model=list[BotStateEventOut])
async def get_bot_state_events(
    bot_ref: str,
    since_seq: int = 0,
    limit: int = 200,
    session: AsyncSession = Depends(async_session_dep),
) -> list[BotStateEventOut]:
    """Paginated event stream from ``bot_events``."""
    from aqp.persistence.models_bots import BotEvent

    row = await _get_row(session, bot_ref)
    stmt = (
        select(BotEvent)
        .where(BotEvent.bot_id == row.id, BotEvent.seq_no > since_seq)
        .order_by(BotEvent.seq_no)
        .limit(min(max(limit, 1), 1000))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        BotStateEventOut(
            seq_no=int(r.seq_no),
            event_type=r.event_type,
            event_data=dict(r.event_data or {}),
            occurred_at=r.occurred_at,
        )
        for r in rows
    ]


# ----------------------------------------------------------------- chat (existing)


@router.post("/{bot_ref}/chat", response_model=TaskAccepted)
async def chat_bot(
    bot_ref: str,
    body: BotChatRequest,
    session: AsyncSession = Depends(async_session_dep),
) -> TaskAccepted:
    """ResearchBot chat — dispatches a Celery task; consume via /chat/stream/{task_id}."""
    row = await _get_row(session, bot_ref)
    if row.kind != "research":
        raise HTTPException(
            status_code=400,
            detail=f"bot kind={row.kind!r} does not support chat (only 'research' bots do)",
        )
    from aqp.tasks.bot_tasks import chat_research_bot

    handle = chat_research_bot.delay(
        row.id,
        body.prompt,
        session_id=body.session_id,
        agent_role=body.agent_role,
        inputs=body.inputs,
    )
    return TaskAccepted(task_id=handle.id, stream_url=f"/chat/stream/{handle.id}")
