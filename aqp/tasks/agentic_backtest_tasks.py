"""Celery tasks for the agentic-trading wizard.

Two entry points:

- :func:`precompute_decisions` — walk the requested ``(symbols, dates)``
  grid, call the trader crew per ``(symbol, date)``, and write the
  resulting :class:`AgentDecision` rows into the Parquet cache + DB.
- :func:`run_agentic_backtest` — call ``precompute_decisions`` (unless
  ``skip_precompute`` is set) and then run
  :func:`aqp.backtest.runner.run_backtest_from_config` with an
  ``AgenticAlpha`` reading the cache. Writes an
  :class:`aqp.persistence.models.AgentBacktest` sidecar so the Backtest
  Lab can show the trader-crew metadata.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _daterange(start: datetime, end: datetime, frequency: str) -> list[datetime]:
    """Return the list of rebalance dates between ``start`` and ``end``."""
    freq = (frequency or "weekly").lower()
    map_ = {
        "daily": "B",       # business day
        "weekly": "W-MON",
        "monthly": "BMS",   # business-month start
    }
    pd_freq = map_.get(freq, freq)
    idx = pd.date_range(start=start, end=end, freq=pd_freq)
    return [d.to_pydatetime() for d in idx]


@celery_app.task(
    bind=True,
    name="aqp.tasks.agentic_backtest_tasks.precompute_decisions",
)
def precompute_decisions(
    self,
    strategy_id: str,
    symbols: list[str],
    start: str,
    end: str,
    *,
    preset: str = "trader_crew_quick",
    overrides: dict[str, Any] | None = None,
    rebalance_frequency: str = "weekly",
) -> dict[str, Any]:
    """Bulk-run the trader crew and populate the decision cache."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Precomputing decisions for {strategy_id}")

    try:
        from aqp.agents.trading.crew import build_trader_crew_config
        from aqp.agents.trading.decision_cache import DecisionCache

        start_dt = pd.to_datetime(start).to_pydatetime()
        end_dt = pd.to_datetime(end).to_pydatetime()
        dates = _daterange(start_dt, end_dt, rebalance_frequency)
        if not dates:
            raise ValueError(
                f"Empty date range after applying frequency={rebalance_frequency!r} "
                f"to {start}..{end}"
            )

        cache = DecisionCache(strategy_id=strategy_id)
        merged_overrides = dict(overrides or {})
        try:
            from aqp.runtime.control_plane import get_provider_control

            runtime_provider = get_provider_control()
            merged_overrides.setdefault("provider", runtime_provider.get("provider"))
            merged_overrides.setdefault("deep_model", runtime_provider.get("deep_model"))
            merged_overrides.setdefault("quick_model", runtime_provider.get("quick_model"))
        except Exception:
            logger.debug("runtime provider control unavailable", exc_info=True)
        cfg = build_trader_crew_config(preset=preset, overrides=merged_overrides)

        def on_progress(pct: float, message: str) -> None:
            emit(task_id, "running", message, progress=pct)

        decisions = cache.bulk_precompute(
            symbols=symbols,
            dates=dates,
            config=cfg,
            on_progress=on_progress,
        )
        total_cost = sum(d.token_cost_usd for d in decisions)
        summary = {
            "strategy_id": strategy_id,
            "n_decisions": len(decisions),
            "n_dates": len(dates),
            "n_symbols": len(symbols),
            "total_cost_usd": round(float(total_cost), 4),
            "provider": cfg.provider,
            "deep_model": cfg.deep_model,
            "quick_model": cfg.quick_model,
            "max_debate_rounds": cfg.max_debate_rounds,
            "cache_uri": str(cache.root),
        }
        emit_done(task_id, summary)
        return summary
    except Exception as exc:  # pragma: no cover - runtime
        logger.exception("precompute_decisions failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(
    bind=True,
    name="aqp.tasks.agentic_backtest_tasks.run_agentic_backtest",
)
def run_agentic_backtest(
    self,
    cfg: dict[str, Any],
    *,
    symbols: list[str],
    start: str,
    end: str,
    strategy_id: str | None = None,
    run_name: str = "agentic-adhoc",
    preset: str | None = None,
    provider: str | None = None,
    deep_model: str | None = None,
    quick_model: str | None = None,
    max_debate_rounds: int | None = None,
    rebalance_frequency: str = "weekly",
    mode: str = "precompute",
    skip_precompute: bool = False,
) -> dict[str, Any]:
    """End-to-end Quickstart: precompute + backtest + persist sidecar."""
    task_id = self.request.id or "local"
    emit(task_id, "start", "Preparing agentic backtest…")
    sid = strategy_id or f"agentic-{task_id[:8]}"
    try:
        from aqp.runtime.control_plane import get_provider_control

        runtime_provider = get_provider_control()
        provider = provider or runtime_provider.get("provider") or None
        deep_model = deep_model or runtime_provider.get("deep_model") or None
        quick_model = quick_model or runtime_provider.get("quick_model") or None
    except Exception:
        logger.debug("runtime provider control unavailable", exc_info=True)

    try:
        # 1. Precompute (unless the user pointed at an existing cache).
        if not skip_precompute:
            emit(task_id, "running", "Running trader crew per rebalance date…")
            overrides: dict[str, Any] = {}
            if provider:
                overrides["provider"] = provider
            if deep_model:
                overrides["deep_model"] = deep_model
            if quick_model:
                overrides["quick_model"] = quick_model
            if max_debate_rounds is not None:
                overrides["max_debate_rounds"] = int(max_debate_rounds)

            precompute_decisions(
                strategy_id=sid,
                symbols=symbols,
                start=start,
                end=end,
                preset=preset or "trader_crew_quick",
                overrides=overrides,
                rebalance_frequency=rebalance_frequency,
            )

        # 2. Inject the AgenticAlpha into the strategy config and run.
        cfg = dict(cfg)
        strategy_cfg = dict(cfg.get("strategy", {}))
        kwargs = dict(strategy_cfg.get("kwargs", {}))
        kwargs["alpha_model"] = {
            "class": "AgenticAlpha",
            "module_path": "aqp.strategies.agentic.agentic_alpha",
            "kwargs": {
                "strategy_id": sid,
                "mode": mode,
            },
        }
        # Keep the universe tight to the symbols the wizard selected.
        universe = kwargs.get("universe_model", {}) or {}
        universe_kwargs = dict(universe.get("kwargs", {}) or {})
        universe_kwargs["symbols"] = symbols
        universe = {
            "class": universe.get("class", "StaticUniverse"),
            "module_path": universe.get("module_path", "aqp.strategies.universes"),
            "kwargs": universe_kwargs,
        }
        kwargs["universe_model"] = universe
        strategy_cfg["kwargs"] = kwargs
        cfg["strategy"] = strategy_cfg

        backtest_cfg = dict(cfg.get("backtest", {}))
        bt_kwargs = dict(backtest_cfg.get("kwargs", {}))
        bt_kwargs.setdefault("start", start)
        bt_kwargs.setdefault("end", end)
        backtest_cfg["kwargs"] = bt_kwargs
        cfg["backtest"] = backtest_cfg

        from aqp.backtest.runner import run_backtest_from_config

        emit(task_id, "running", "Backtest replay over cached decisions…")
        result = run_backtest_from_config(cfg, run_name=run_name, strategy_id=strategy_id)

        # 3. Persist an AgentBacktest sidecar.
        _write_sidecar(
            backtest_id=result.get("run_id"),
            strategy_id=sid,
            cfg=cfg,
            mode=mode,
            provider=provider,
            deep_model=deep_model,
            quick_model=quick_model,
            max_debate_rounds=max_debate_rounds,
        )

        emit_done(task_id, result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("run_agentic_backtest failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(
    bind=True,
    name="aqp.tasks.agentic_backtest_tasks.run_agentic_pipeline",
)
def run_agentic_pipeline(
    self,
    *,
    cfg: dict[str, Any],
    symbols: list[str],
    start: str,
    end: str,
    strategy_id: str | None = None,
    run_name: str = "agentic-pipeline",
    x_backtests: int = 1,
    preset: str | None = None,
    provider: str | None = None,
    deep_model: str | None = None,
    quick_model: str | None = None,
    max_debate_rounds: int | None = None,
    rebalance_frequency: str = "weekly",
    mode: str = "precompute",
    skip_precompute: bool = False,
    universe_filter: dict[str, Any] | None = None,
    conditions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a multi-variant agentic backtesting pipeline."""
    task_id = self.request.id or "local"
    emit(task_id, "start", "Starting agentic pipeline orchestration…")
    sid = strategy_id or f"agentic-pipeline-{task_id[:8]}"
    try:
        from aqp.agents.trading.orchestration import run_agentic_pipeline as _run

        def _progress(pct: float, msg: str) -> None:
            emit(task_id, "running", msg, progress=float(pct))

        payload = _run(
            cfg=cfg,
            symbols=symbols,
            start=start,
            end=end,
            strategy_id=sid,
            run_name=run_name,
            x_backtests=x_backtests,
            mode=mode,
            skip_precompute=skip_precompute,
            rebalance_frequency=rebalance_frequency,
            preset=preset,
            provider=provider,
            deep_model=deep_model,
            quick_model=quick_model,
            max_debate_rounds=max_debate_rounds,
            universe_filter=universe_filter,
            conditions=conditions,
            runner=run_agentic_backtest,
            on_progress=_progress,
        )
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("run_agentic_pipeline failed")
        emit_error(task_id, str(exc))
        raise


def _write_sidecar(
    *,
    backtest_id: str | None,
    strategy_id: str,
    cfg: dict[str, Any],
    mode: str,
    provider: str | None,
    deep_model: str | None,
    quick_model: str | None,
    max_debate_rounds: int | None,
) -> None:
    if not backtest_id:
        return
    try:
        from aqp.agents.trading.decision_cache import DecisionCache
        from aqp.persistence.db import get_session
        from aqp.persistence.models import AgentBacktest, AgentDecision
        from sqlalchemy import func, select

        cache = DecisionCache(strategy_id=strategy_id)
        summary_df = cache.scan()
        n_decisions = int(len(summary_df))
        total_cost = float(summary_df["token_cost_usd"].sum()) if n_decisions else 0.0

        with get_session() as session:
            existing = (
                session.query(AgentBacktest)
                .filter(AgentBacktest.backtest_id == backtest_id)
                .first()
            )
            if existing is not None:
                return
            row = AgentBacktest(
                backtest_id=backtest_id,
                mode=mode,
                provider=provider,
                deep_model=deep_model,
                quick_model=quick_model,
                max_debate_rounds=int(max_debate_rounds or 1),
                n_decisions=n_decisions,
                total_token_cost_usd=total_cost,
                decision_cache_uri=str(cache.root),
                config=cfg,
            )
            session.add(row)
            # Also mirror each cache row into agent_decisions for easy SQL.
            if n_decisions > 0 and backtest_id:
                for _, record in summary_df.iterrows():
                    session.add(
                        AgentDecision(
                            backtest_id=backtest_id,
                            strategy_id=None,
                            crew_run_id=str(record.get("crew_run_id") or "") or None,
                            vt_symbol=str(record["vt_symbol"]),
                            ts=pd.to_datetime(record["timestamp"]).to_pydatetime(),
                            action=str(record["action"]),
                            size_pct=float(record["size_pct"] or 0.0),
                            confidence=float(record["confidence"] or 0.5),
                            rating=str(record["rating"] or "hold"),
                            rationale=str(record.get("rationale") or ""),
                            evidence=[],
                            provider=str(record.get("provider") or "") or None,
                            deep_model=str(record.get("deep_model") or "") or None,
                            quick_model=str(record.get("quick_model") or "") or None,
                            token_cost_usd=float(record.get("token_cost_usd") or 0.0),
                            context_hash=str(record.get("context_hash") or "") or None,
                            payload={},
                        )
                    )
    except Exception:  # pragma: no cover
        logger.debug("agent_backtest sidecar write skipped", exc_info=True)


# ---------------------------------------------------------------------------
# HITL phase 1 — LLM/agent-as-judge + post-hoc counterfactual replay.
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="aqp.tasks.agentic_backtest_tasks.run_agentic_judge",
)
def run_agentic_judge(
    self,
    backtest_id: str,
    judge_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the configured LLM judge over a backtest's decision trace.

    Persists exactly one :class:`AgentJudgeReport` row per
    ``(backtest_id, judge_class)`` pair. Returns the report payload.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Judging backtest {backtest_id}…")

    judge_cfg = dict(judge_cfg or {})
    judge_cfg.setdefault("class", "LLMJudge")
    judge_cfg.setdefault("module_path", "aqp.backtest.llm_judge")

    try:
        from aqp.backtest.llm_judge import BaseJudge, LLMJudge
        from aqp.core.registry import build_from_config
        from aqp.persistence.db import get_session
        from aqp.persistence.models import (
            AgentDecision,
            AgentJudgeReport,
            BacktestRun,
        )
        from sqlalchemy import select

        with get_session() as session:
            run = session.get(BacktestRun, backtest_id)
            if run is None:
                raise ValueError(f"backtest {backtest_id} not found")
            decisions = (
                session.execute(
                    select(AgentDecision)
                    .where(AgentDecision.backtest_id == backtest_id)
                    .order_by(AgentDecision.ts.asc())
                )
                .scalars()
                .all()
            )
            decision_records = [
                {
                    "id": d.id,
                    "vt_symbol": d.vt_symbol,
                    "ts": d.ts,
                    "action": d.action,
                    "size_pct": d.size_pct,
                    "confidence": d.confidence,
                    "rating": d.rating,
                    "rationale": d.rationale,
                    "token_cost_usd": d.token_cost_usd,
                }
                for d in decisions
            ]
            equity_curve = pd.Series(run.equity_curve or {}, dtype=float)
            if not equity_curve.empty:
                equity_curve.index = pd.to_datetime(equity_curve.index)

        try:
            judge = build_from_config(judge_cfg)
        except Exception:
            logger.exception("falling back to default LLMJudge")
            judge = LLMJudge()

        if not isinstance(judge, BaseJudge):
            raise TypeError(
                f"resolved judge is not a BaseJudge subclass: {type(judge).__name__}"
            )

        emit(task_id, "running", f"Calling {type(judge).__name__}…")
        report = judge.evaluate(
            decision_records,
            equity_curve=equity_curve if not equity_curve.empty else None,
            backtest_id=backtest_id,
        )

        with get_session() as session:
            row = AgentJudgeReport(
                backtest_id=backtest_id,
                judge_class=report.judge_class,
                score=float(report.score or 0.0),
                summary=report.summary,
                findings=[f.model_dump(mode="json") for f in report.findings],
                cost_usd=float(report.cost_usd or 0.0),
                provider=report.provider or None,
                model=report.model or None,
                rubric=report.rubric or "default",
                config=judge_cfg,
            )
            session.add(row)
            session.flush()
            report_id = row.id

        payload = {
            "report_id": report_id,
            "backtest_id": backtest_id,
            **report.to_json_dict(),
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("run_agentic_judge failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(
    bind=True,
    name="aqp.tasks.agentic_backtest_tasks.run_agentic_replay",
)
def run_agentic_replay(
    self,
    parent_backtest_id: str,
    edits: list[dict[str, Any]],
    *,
    note: str | None = None,
    created_by: str | None = None,
    judge_report_id: str | None = None,
) -> dict[str, Any]:
    """Re-run a backtest with one or more decision edits applied.

    Edits never mutate the original ``AgentDecision`` rows or Parquet
    cache — they live in an in-memory patched cache that
    :class:`AgenticAlpha` reads in ``PRECOMPUTE`` mode for the duration
    of the child backtest.
    """
    from aqp.persistence.db import get_session
    from aqp.persistence.models import (
        AgentBacktest,
        AgentDecision,
        AgentReplayRun,
        BacktestRun,
    )
    from sqlalchemy import select

    task_id = self.request.id or "local"
    emit(task_id, "start", f"Replaying backtest {parent_backtest_id}…")

    replay_id: str | None = None
    try:
        with get_session() as session:
            parent = session.get(BacktestRun, parent_backtest_id)
            if parent is None:
                raise ValueError(f"parent backtest {parent_backtest_id} not found")
            sidecar = (
                session.execute(
                    select(AgentBacktest).where(
                        AgentBacktest.backtest_id == parent_backtest_id
                    )
                )
                .scalar_one_or_none()
            )
            replay_row = AgentReplayRun(
                parent_backtest_id=parent_backtest_id,
                edits=list(edits or []),
                note=note,
                created_by=created_by,
                judge_report_id=judge_report_id,
                status="running",
            )
            session.add(replay_row)
            session.flush()
            replay_id = replay_row.id
            base_cfg = dict(sidecar.config) if sidecar and sidecar.config else {}
            decisions = (
                session.execute(
                    select(AgentDecision)
                    .where(AgentDecision.backtest_id == parent_backtest_id)
                    .order_by(AgentDecision.ts.asc())
                )
                .scalars()
                .all()
            )
            decision_rows = [
                {
                    "id": d.id,
                    "vt_symbol": d.vt_symbol,
                    "ts": d.ts,
                    "action": d.action,
                    "size_pct": d.size_pct,
                    "confidence": d.confidence,
                    "rating": d.rating,
                    "rationale": d.rationale,
                    "token_cost_usd": d.token_cost_usd,
                }
                for d in decisions
            ]

        if not base_cfg:
            raise RuntimeError(
                f"no agent_backtest sidecar found for {parent_backtest_id}; "
                "replay only supports agentic backtests"
            )

        # Apply edits. For now we only support overriding action / size /
        # rationale on a per-decision basis.
        edits_by_id = {str(e.get("decision_id")): e for e in edits if e.get("decision_id")}
        patched_rows: list[dict[str, Any]] = []
        for row in decision_rows:
            edit = edits_by_id.get(str(row["id"]))
            if not edit:
                patched_rows.append(row)
                continue
            new = dict(row)
            if "action" in edit:
                new["action"] = str(edit["action"]).upper()
            if "size_pct" in edit:
                new["size_pct"] = float(edit["size_pct"])
            if "rationale" in edit:
                new["rationale"] = str(edit["rationale"])[:1000]
            patched_rows.append(new)

        # Build a synthetic strategy_id so the patched cache writes
        # don't collide with the parent's. The replay cache is
        # ephemeral — we materialise it under a deterministic
        # subdirectory keyed on the replay id so re-running the same
        # task is idempotent.
        from aqp.agents.trading.decision_cache import DecisionCache
        from aqp.agents.trading.types import (
            AgentDecision as AgentDecisionModel,
            Rating5,
            TraderAction,
            parse_rating,
        )
        from aqp.config import settings

        replay_strategy_id = f"replay-{replay_id[:8]}"
        cache_root = settings.agentic_cache_dir / "replays"
        cache_root.mkdir(parents=True, exist_ok=True)
        cache = DecisionCache(root=cache_root, strategy_id=replay_strategy_id)
        for row in patched_rows:
            try:
                action = TraderAction(str(row["action"]).upper())
            except ValueError:
                action = TraderAction.HOLD
            try:
                rating = parse_rating(str(row.get("rating", "hold")))
            except Exception:
                rating = Rating5.HOLD
            decision = AgentDecisionModel(
                vt_symbol=str(row["vt_symbol"]),
                timestamp=pd.to_datetime(row["ts"]).to_pydatetime(),
                action=action,
                size_pct=float(row["size_pct"] or 0.0),
                confidence=float(row["confidence"] or 0.5),
                rating=rating,
                rationale=str(row.get("rationale") or ""),
                context_hash=f"replay-{row['id']}",
            )
            cache.put(decision, overwrite=True)

        # Build the child config: clone the parent's strategy block and
        # rewire the AgenticAlpha to read from the replay cache.
        cfg = dict(base_cfg)
        strategy_cfg = dict(cfg.get("strategy", {}))
        kwargs = dict(strategy_cfg.get("kwargs", {}))
        kwargs["alpha_model"] = {
            "class": "AgenticAlpha",
            "module_path": "aqp.strategies.agentic.agentic_alpha",
            "kwargs": {
                "strategy_id": replay_strategy_id,
                "cache_root": str(cache_root),
                "mode": "precompute",
            },
        }
        strategy_cfg["kwargs"] = kwargs
        cfg["strategy"] = strategy_cfg

        from aqp.backtest.runner import run_backtest_from_config

        emit(task_id, "running", "Running counterfactual backtest…")
        child = run_backtest_from_config(
            cfg,
            run_name=f"replay-of-{parent_backtest_id[:8]}",
            strategy_id=replay_strategy_id,
        )
        child_id = child.get("run_id")

        with get_session() as session:
            row = session.get(AgentReplayRun, replay_id)
            if row is not None:
                row.child_backtest_id = child_id
                row.status = "completed"
                row.completed_at = datetime.utcnow()

        payload = {
            "replay_id": replay_id,
            "parent_backtest_id": parent_backtest_id,
            "child_backtest_id": child_id,
            "n_edits": len(edits or []),
            **child,
        }
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("run_agentic_replay failed")
        if replay_id is not None:
            try:
                with get_session() as session:
                    row = session.get(AgentReplayRun, replay_id)
                    if row is not None:
                        row.status = "error"
                        row.error = str(exc)
                        row.completed_at = datetime.utcnow()
            except Exception:
                logger.debug("could not flag replay row as error", exc_info=True)
        emit_error(task_id, str(exc))
        raise
