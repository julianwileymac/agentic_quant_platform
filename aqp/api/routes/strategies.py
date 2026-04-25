"""Strategy persistence + testing API.

Endpoints:

- ``POST   /strategies/``                 — save a new strategy (writes v1)
- ``GET    /strategies/``                 — list strategies (+ latest version)
- ``GET    /strategies/{id}``             — detail with versions + tests
- ``PUT    /strategies/{id}``             — update config → auto-bumps version
- ``DELETE /strategies/{id}``             — soft-delete (status=archived)
- ``POST   /strategies/{id}/test``        — enqueue a backtest against the latest version
- ``GET    /strategies/{id}/tests``       — list tests
- ``GET    /strategies/{id}/versions``    — list versions
- ``GET    /strategies/{id}/versions/{v}/diff?against={other}`` — unified YAML diff
"""
from __future__ import annotations

import contextlib
import difflib
import logging
from datetime import datetime
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    BacktestRun,
    Strategy,
    StrategyTest,
    StrategyVersion,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/strategies", tags=["strategies"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StrategyCreate(BaseModel):
    name: str = Field(..., description="Human-readable name")
    config_yaml: str = Field(..., description="YAML recipe for the strategy")
    author: str = Field(default="system")
    notes: str | None = None


class StrategyUpdate(BaseModel):
    config_yaml: str
    author: str = Field(default="system")
    notes: str | None = None


class StrategySummary(BaseModel):
    id: str
    name: str
    status: str
    version: int
    author: str
    created_at: datetime
    last_tested_at: datetime | None = None
    last_sharpe: float | None = None


class StrategyDetail(StrategySummary):
    config_yaml: str
    versions: list[dict[str, Any]] = Field(default_factory=list)
    tests: list[dict[str, Any]] = Field(default_factory=list)


class StrategyTestRequest(BaseModel):
    engine: str = Field(default="EventDrivenBacktester")
    start: str | None = None
    end: str | None = None
    notes: str | None = None


class VersionSummary(BaseModel):
    id: str
    version: int
    author: str
    created_at: datetime
    notes: str | None = None


class TestSummary(BaseModel):
    id: str
    status: str
    engine: str | None
    sharpe: float | None
    total_return: float | None
    max_drawdown: float | None
    backtest_id: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("/", response_model=StrategyDetail)
def create_strategy(req: StrategyCreate) -> StrategyDetail:
    _validate_yaml(req.config_yaml)
    with get_session() as s:
        strategy = Strategy(
            name=req.name,
            version=1,
            config_yaml=req.config_yaml,
            created_by=req.author,
            status="draft",
        )
        s.add(strategy)
        s.flush()
        version = StrategyVersion(
            strategy_id=strategy.id,
            version=1,
            config_yaml=req.config_yaml,
            author=req.author,
            notes=req.notes,
        )
        s.add(version)
        s.flush()
        return _to_detail(s, strategy)


@router.get("/", response_model=list[StrategySummary])
def list_strategies(limit: int = 50, include_archived: bool = False) -> list[StrategySummary]:
    with get_session() as s:
        stmt = select(Strategy).order_by(desc(Strategy.created_at)).limit(limit)
        if not include_archived:
            stmt = stmt.where(Strategy.status != "archived")
        rows = s.execute(stmt).scalars().all()
        return [_to_summary(s, r) for r in rows]


# ---------------------------------------------------------------------------
# Browser endpoints — power the Strategy Browser UI.
# ---------------------------------------------------------------------------


class StrategyBrowserRow(BaseModel):
    id: str
    name: str
    status: str
    version: int
    created_at: datetime
    author: str
    alpha_class: str | None = None
    engine: str | None = None
    last_sharpe: float | None = None
    last_total_return: float | None = None
    last_max_drawdown: float | None = None
    last_tested_at: datetime | None = None
    latest_mlflow_run_id: str | None = None
    experiment_name: str | None = None
    tags: list[str] = Field(default_factory=list)


class StrategyBrowserCatalogRow(BaseModel):
    alpha_class: str
    module_path: str
    tags: list[str] = Field(default_factory=list)
    config_paths: list[str] = Field(default_factory=list)


@router.get("/browse", response_model=list[StrategyBrowserRow])
def browse_strategies(
    tag: str | None = None,
    status: str | None = None,
    query: str | None = None,
    min_sharpe: float | None = None,
    limit: int = 100,
) -> list[StrategyBrowserRow]:
    """Enriched strategy catalog for the browser UI.

    Joins :class:`Strategy` with the most recent :class:`StrategyTest` +
    :class:`BacktestRun` to show the latest Sharpe / return / MLflow run id
    per strategy, filtered by optional tag / status / query / min_sharpe.
    """
    with get_session() as s:
        stmt = select(Strategy).order_by(desc(Strategy.created_at)).limit(limit)
        if status:
            stmt = stmt.where(Strategy.status == status)
        if query:
            stmt = stmt.where(Strategy.name.ilike(f"%{query}%"))
        rows = s.execute(stmt).scalars().all()
        out: list[StrategyBrowserRow] = []
        for row in rows:
            cfg = {}
            with contextlib.suppress(Exception):
                cfg = yaml.safe_load(row.config_yaml) or {}
            alpha_cls, tags = _extract_alpha_and_tags(cfg)
            engine = _extract_engine(cfg)
            last_test = s.execute(
                select(StrategyTest)
                .where(StrategyTest.strategy_id == row.id)
                .order_by(desc(StrategyTest.created_at))
                .limit(1)
            ).scalar_one_or_none()
            last_run: BacktestRun | None = None
            if last_test and last_test.backtest_id:
                last_run = s.execute(
                    select(BacktestRun).where(BacktestRun.id == last_test.backtest_id)
                ).scalar_one_or_none()
            if last_run is None:
                last_run = s.execute(
                    select(BacktestRun)
                    .where(BacktestRun.strategy_id == row.id)
                    .order_by(desc(BacktestRun.created_at))
                    .limit(1)
                ).scalar_one_or_none()

            last_sharpe = (last_run.sharpe if last_run else None) or (last_test.sharpe if last_test else None)
            if min_sharpe is not None and (last_sharpe is None or last_sharpe < min_sharpe):
                continue
            if tag and tag not in tags:
                continue

            out.append(
                StrategyBrowserRow(
                    id=row.id,
                    name=row.name,
                    status=row.status,
                    version=int(row.version or 1),
                    created_at=row.created_at,
                    author=row.created_by,
                    alpha_class=alpha_cls,
                    engine=engine,
                    last_sharpe=last_sharpe,
                    last_total_return=(
                        last_run.total_return if last_run else (last_test.total_return if last_test else None)
                    ),
                    last_max_drawdown=(
                        last_run.max_drawdown if last_run else (last_test.max_drawdown if last_test else None)
                    ),
                    last_tested_at=last_test.created_at if last_test else None,
                    latest_mlflow_run_id=last_run.mlflow_run_id if last_run else None,
                    experiment_name=f"strategy/{row.id[:8]}",
                    tags=list(tags),
                )
            )
        return out


@router.get("/browse/catalog", response_model=list[StrategyBrowserCatalogRow])
def strategy_catalog() -> list[StrategyBrowserCatalogRow]:
    """Catalog of *code-available* alpha classes (not user-saved strategies).

    Pulls the tag list from :mod:`aqp.strategies` (``STRATEGY_TAGS`` per
    module) and pairs each class with any ``configs/strategies/*.yaml``
    recipes that reference it, so the UI can show "here are all the alphas
    you can instantiate + example YAMLs".
    """
    import importlib
    import inspect
    from pathlib import Path

    from aqp.strategies import list_strategy_tags

    tags = list_strategy_tags()
    # Build the class -> tags mapping then attach discovered YAML paths.
    config_paths_by_class: dict[str, list[str]] = {}
    try:
        configs_dir = Path(__file__).resolve().parents[3] / "configs" / "strategies"
        if configs_dir.exists():
            for cfg in configs_dir.glob("*.yaml"):
                try:
                    parsed = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                except yaml.YAMLError:
                    continue
                alpha = (parsed.get("strategy", {}).get("kwargs", {}) or {}).get("alpha_model", {})
                alpha_cls = alpha.get("class") if isinstance(alpha, dict) else None
                if alpha_cls:
                    config_paths_by_class.setdefault(alpha_cls, []).append(str(cfg.relative_to(configs_dir.parents[0])))
    except Exception:
        logger.debug("strategy catalog YAML scan failed", exc_info=True)

    out: list[StrategyBrowserCatalogRow] = []
    strategies_mod = importlib.import_module("aqp.strategies")
    for name in getattr(strategies_mod, "__all__", []):
        obj = getattr(strategies_mod, name, None)
        if obj is None or not inspect.isclass(obj):
            continue
        module = getattr(obj, "__module__", "")
        if not module.startswith("aqp.strategies"):
            continue
        out.append(
            StrategyBrowserCatalogRow(
                alpha_class=name,
                module_path=module,
                tags=list(tags.get(name, ())),
                config_paths=config_paths_by_class.get(name, []),
            )
        )
    return out


@router.get("/{strategy_id}/experiment")
def strategy_experiment(strategy_id: str) -> dict[str, Any]:
    """Return the MLflow experiment + runs linked to this strategy."""
    with get_session() as s:
        row = s.get(Strategy, strategy_id)
        if row is None:
            raise HTTPException(404, "strategy not found")
        runs = s.execute(
            select(BacktestRun)
            .where(BacktestRun.strategy_id == strategy_id)
            .order_by(desc(BacktestRun.created_at))
            .limit(50)
        ).scalars().all()
        experiment_name = f"strategy/{strategy_id[:8]}"
        from aqp.config import settings

        return {
            "strategy_id": strategy_id,
            "experiment_name": experiment_name,
            "tracking_uri": settings.mlflow_tracking_uri,
            "runs": [
                {
                    "id": r.id,
                    "mlflow_run_id": r.mlflow_run_id,
                    "sharpe": r.sharpe,
                    "total_return": r.total_return,
                    "max_drawdown": r.max_drawdown,
                    "engine": (r.metrics or {}).get("engine"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs
            ],
        }


def _extract_alpha_and_tags(cfg: dict[str, Any]) -> tuple[str | None, list[str]]:
    alpha = (cfg.get("strategy", {}).get("kwargs", {}) or {}).get("alpha_model") or {}
    alpha_cls = alpha.get("class") if isinstance(alpha, dict) else None
    if alpha_cls is None:
        return None, []
    try:
        from aqp.strategies import list_strategy_tags

        return alpha_cls, list(list_strategy_tags().get(alpha_cls, ()))
    except Exception:
        return alpha_cls, []


def _extract_engine(cfg: dict[str, Any]) -> str | None:
    bt = cfg.get("backtest") or {}
    if isinstance(bt, dict):
        return bt.get("engine") or bt.get("class")
    return None


@router.get("/{strategy_id}", response_model=StrategyDetail)
def get_strategy(strategy_id: str) -> StrategyDetail:
    with get_session() as s:
        row = s.get(Strategy, strategy_id)
        if row is None:
            raise HTTPException(404, "strategy not found")
        return _to_detail(s, row)


@router.put("/{strategy_id}", response_model=StrategyDetail)
def update_strategy(strategy_id: str, req: StrategyUpdate) -> StrategyDetail:
    _validate_yaml(req.config_yaml)
    with get_session() as s:
        row = s.get(Strategy, strategy_id)
        if row is None:
            raise HTTPException(404, "strategy not found")
        new_version = int((row.version or 0) + 1)
        row.version = new_version
        row.config_yaml = req.config_yaml
        s.add(
            StrategyVersion(
                strategy_id=row.id,
                version=new_version,
                config_yaml=req.config_yaml,
                author=req.author,
                notes=req.notes,
            )
        )
        s.flush()
        return _to_detail(s, row)


@router.delete("/{strategy_id}")
def archive_strategy(strategy_id: str) -> dict[str, Any]:
    with get_session() as s:
        row = s.get(Strategy, strategy_id)
        if row is None:
            raise HTTPException(404, "strategy not found")
        row.status = "archived"
        return {"id": strategy_id, "status": "archived"}


# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------


@router.post("/{strategy_id}/test", response_model=TaskAccepted)
def test_strategy(strategy_id: str, req: StrategyTestRequest) -> TaskAccepted:
    with get_session() as s:
        row = s.get(Strategy, strategy_id)
        if row is None:
            raise HTTPException(404, "strategy not found")
        latest_version = s.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(desc(StrategyVersion.version))
            .limit(1)
        ).scalar_one_or_none()
        try:
            cfg = yaml.safe_load(row.config_yaml) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(400, f"stored config_yaml is invalid: {exc}") from exc
        if req.start and req.end:
            cfg.setdefault("backtest", {}).setdefault("kwargs", {})
            cfg["backtest"]["kwargs"]["start"] = req.start
            cfg["backtest"]["kwargs"]["end"] = req.end

        # Queue the backtest task via the same pipeline the Backtest Lab uses.
        from aqp.tasks.backtest_tasks import run_backtest

        async_result = run_backtest.delay(cfg, f"test-{row.name}")
        test = StrategyTest(
            strategy_id=row.id,
            version_id=latest_version.id if latest_version else None,
            status="queued",
            engine=req.engine,
            notes=req.notes,
        )
        s.add(test)
        s.flush()
        return TaskAccepted(
            task_id=async_result.id,
            stream_url=f"/chat/stream/{async_result.id}",
        )


@router.get("/{strategy_id}/tests", response_model=list[TestSummary])
def list_tests(strategy_id: str, limit: int = 50) -> list[TestSummary]:
    with get_session() as s:
        rows = s.execute(
            select(StrategyTest)
            .where(StrategyTest.strategy_id == strategy_id)
            .order_by(desc(StrategyTest.created_at))
            .limit(limit)
        ).scalars().all()
        return [
            TestSummary(
                id=r.id,
                status=r.status,
                engine=r.engine,
                sharpe=r.sharpe,
                total_return=r.total_return,
                max_drawdown=r.max_drawdown,
                backtest_id=r.backtest_id,
                created_at=r.created_at,
            )
            for r in rows
        ]


@router.get("/{strategy_id}/versions", response_model=list[VersionSummary])
def list_versions(strategy_id: str) -> list[VersionSummary]:
    with get_session() as s:
        rows = s.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(desc(StrategyVersion.version))
        ).scalars().all()
        return [
            VersionSummary(
                id=r.id,
                version=r.version,
                author=r.author,
                created_at=r.created_at,
                notes=r.notes,
            )
            for r in rows
        ]


@router.get("/{strategy_id}/versions/{version}/diff")
def version_diff(strategy_id: str, version: int, against: int | None = None) -> dict[str, Any]:
    """Unified YAML diff between two versions of the same strategy."""
    with get_session() as s:
        target = s.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .where(StrategyVersion.version == version)
        ).scalar_one_or_none()
        if target is None:
            raise HTTPException(404, f"version {version} not found")
        if against is None:
            # Compare to previous version (or itself if this is v1).
            prior = s.execute(
                select(StrategyVersion)
                .where(StrategyVersion.strategy_id == strategy_id)
                .where(StrategyVersion.version < version)
                .order_by(desc(StrategyVersion.version))
                .limit(1)
            ).scalar_one_or_none()
            base = prior.config_yaml if prior else target.config_yaml
            against_version = prior.version if prior else version
        else:
            other = s.execute(
                select(StrategyVersion)
                .where(StrategyVersion.strategy_id == strategy_id)
                .where(StrategyVersion.version == against)
            ).scalar_one_or_none()
            if other is None:
                raise HTTPException(404, f"version {against} not found")
            base = other.config_yaml
            against_version = against
        diff = "\n".join(
            difflib.unified_diff(
                base.splitlines(),
                target.config_yaml.splitlines(),
                fromfile=f"v{against_version}",
                tofile=f"v{version}",
                lineterm="",
            )
        )
        return {
            "strategy_id": strategy_id,
            "from_version": against_version,
            "to_version": version,
            "diff": diff,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_yaml(text: str) -> None:
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(400, f"invalid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(400, "config_yaml must be a YAML mapping")


def _to_summary(session, row: Strategy) -> StrategySummary:
    last = session.execute(
        select(StrategyTest)
        .where(StrategyTest.strategy_id == row.id)
        .order_by(desc(StrategyTest.created_at))
        .limit(1)
    ).scalar_one_or_none()
    return StrategySummary(
        id=row.id,
        name=row.name,
        status=row.status,
        version=row.version or 1,
        author=row.created_by,
        created_at=row.created_at,
        last_tested_at=last.created_at if last else None,
        last_sharpe=last.sharpe if last else None,
    )


def _to_detail(session, row: Strategy) -> StrategyDetail:
    versions = session.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == row.id)
        .order_by(desc(StrategyVersion.version))
    ).scalars().all()
    tests = session.execute(
        select(StrategyTest)
        .where(StrategyTest.strategy_id == row.id)
        .order_by(desc(StrategyTest.created_at))
        .limit(10)
    ).scalars().all()
    summary = _to_summary(session, row).model_dump()
    return StrategyDetail(
        **summary,
        config_yaml=row.config_yaml,
        versions=[
            {
                "id": v.id,
                "version": v.version,
                "author": v.author,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "notes": v.notes,
            }
            for v in versions
        ],
        tests=[
            {
                "id": t.id,
                "status": t.status,
                "engine": t.engine,
                "sharpe": t.sharpe,
                "total_return": t.total_return,
                "max_drawdown": t.max_drawdown,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "backtest_id": t.backtest_id,
            }
            for t in tests
        ],
    )
