"""Service layer over :class:`StrategyRegimeMemory`.

Public surface:

- :func:`get_best_params(strategy_id, regime, *, ctx, ...)` — return
  the highest-sharpe row for the given strategy + regime in the
  active workspace. Reads through Redis when available.
- :func:`record_observation(strategy_id, regime, params, metrics, *,
  ctx, backtest_run_id=None)` — upsert a row from a completed
  backtest. Idempotent on ``(workspace, strategy, regime, params_hash)``.
- :func:`top_k_for_regime(strategy_id, regime, *, ctx, k=5)` — return
  the K best parameter sets recorded under the regime (used by
  agents that want to consider multiple warm-starts).

The service treats Redis purely as a cache: the canonical store is
Postgres. A failed Redis call degrades to direct DB reads silently.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select

from aqp.auth.context import RequestContext
from aqp.auth.contextvars import get_context_or_default
from aqp.persistence.db import get_session
from aqp.persistence.models_strategy_memory import StrategyRegimeMemory

logger = logging.getLogger(__name__)


_REDIS_KEY_TEMPLATE = "aqp:strategy_memory:{ws}:{strategy}:{regime}"
_REDIS_TTL_SECONDS = 3600


def _params_hash(params: dict[str, Any]) -> str:
    """Deterministic SHA-256 hash of a parameter dict."""
    canonical = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _redis_client():
    try:
        from aqp.config import settings
        import redis

        return redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
        )
    except Exception:  # noqa: BLE001
        return None


def _redis_key(workspace_id: str, strategy_id: str, regime: str) -> str:
    return _REDIS_KEY_TEMPLATE.format(
        ws=workspace_id or "default",
        strategy=strategy_id,
        regime=regime,
    )


def _row_to_dict(row: StrategyRegimeMemory) -> dict[str, Any]:
    return {
        "id": row.id,
        "strategy_id": row.strategy_id,
        "regime": row.regime,
        "params": dict(row.params or {}),
        "params_hash": row.params_hash,
        "best_sharpe": float(row.best_sharpe or 0.0),
        "best_sortino": float(row.best_sortino or 0.0),
        "best_calmar": float(row.best_calmar or 0.0),
        "max_drawdown": float(row.max_drawdown or 0.0),
        "n_observations": int(row.n_observations or 0),
        "backtest_run_id": row.backtest_run_id,
        "notes": dict(row.notes or {}),
        "workspace_id": row.workspace_id,
        "owner_user_id": row.owner_user_id,
        "last_observed_at": row.last_observed_at.isoformat() if row.last_observed_at else None,
    }


def get_best_params(
    strategy_id: str,
    regime: str,
    *,
    ctx: RequestContext | None = None,
) -> dict[str, Any] | None:
    """Return the highest-sharpe :class:`StrategyRegimeMemory` row.

    Workspace-scoped: only rows in the active workspace are
    considered. NULL-workspace rows (cross-tenant shared / legacy)
    are ignored to prevent accidental leakage of another workspace's
    parameters.
    """
    ctx = ctx if ctx is not None else get_context_or_default()
    if not ctx.workspace_id:
        return None

    redis = _redis_client()
    cache_key = _redis_key(ctx.workspace_id, strategy_id, regime)
    if redis is not None:
        try:
            cached = redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:  # noqa: BLE001
            logger.debug("redis cache read failed; falling through", exc_info=True)

    with get_session() as session:
        row = (
            session.execute(
                select(StrategyRegimeMemory)
                .where(StrategyRegimeMemory.workspace_id == ctx.workspace_id)
                .where(StrategyRegimeMemory.strategy_id == strategy_id)
                .where(StrategyRegimeMemory.regime == regime)
                .order_by(StrategyRegimeMemory.best_sharpe.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            return None
        payload = _row_to_dict(row)

    if redis is not None:
        try:
            redis.setex(cache_key, _REDIS_TTL_SECONDS, json.dumps(payload, default=str))
        except Exception:  # noqa: BLE001
            logger.debug("redis cache write failed; ignoring", exc_info=True)
    return payload


def top_k_for_regime(
    strategy_id: str,
    regime: str,
    *,
    ctx: RequestContext | None = None,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Return the K highest-sharpe rows for ``(strategy, regime)``."""
    ctx = ctx if ctx is not None else get_context_or_default()
    if not ctx.workspace_id:
        return []
    with get_session() as session:
        rows = (
            session.execute(
                select(StrategyRegimeMemory)
                .where(StrategyRegimeMemory.workspace_id == ctx.workspace_id)
                .where(StrategyRegimeMemory.strategy_id == strategy_id)
                .where(StrategyRegimeMemory.regime == regime)
                .order_by(StrategyRegimeMemory.best_sharpe.desc())
                .limit(int(k))
            )
            .scalars()
            .all()
        )
        return [_row_to_dict(r) for r in rows]


def record_observation(
    *,
    strategy_id: str,
    regime: str,
    params: dict[str, Any],
    metrics: dict[str, Any],
    backtest_run_id: str | None = None,
    notes: dict[str, Any] | None = None,
    ctx: RequestContext | None = None,
) -> dict[str, Any]:
    """Upsert a regime memory row from a completed backtest.

    The row is keyed by ``(workspace_id, strategy_id, regime, params_hash)``;
    re-running the same params under the same regime updates the
    sharpe / sortino / calmar / max_drawdown fields and bumps
    ``n_observations``.
    """
    from datetime import datetime

    ctx = ctx if ctx is not None else get_context_or_default()
    if not ctx.workspace_id:
        raise ValueError("record_observation requires an active workspace")

    sharpe = float(metrics.get("sharpe", 0.0) or 0.0)
    sortino = float(metrics.get("sortino", 0.0) or 0.0)
    calmar = float(metrics.get("calmar", 0.0) or 0.0)
    mdd = float(metrics.get("max_drawdown", 0.0) or 0.0)
    phash = _params_hash(params)
    now = datetime.utcnow()

    with get_session() as session:
        row = (
            session.execute(
                select(StrategyRegimeMemory)
                .where(StrategyRegimeMemory.workspace_id == ctx.workspace_id)
                .where(StrategyRegimeMemory.strategy_id == strategy_id)
                .where(StrategyRegimeMemory.regime == regime)
                .where(StrategyRegimeMemory.params_hash == phash)
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            row_kwargs: dict[str, Any] = dict(
                strategy_id=strategy_id,
                regime=regime,
                params=dict(params),
                params_hash=phash,
                best_sharpe=sharpe,
                best_sortino=sortino,
                best_calmar=calmar,
                max_drawdown=mdd,
                n_observations=1,
                backtest_run_id=backtest_run_id,
                notes=dict(notes) if notes else {},
                first_observed_at=now,
                last_observed_at=now,
                updated_at=now,
            )
            if ctx.user_id:
                row_kwargs["owner_user_id"] = ctx.user_id
            row_kwargs["workspace_id"] = ctx.workspace_id
            if ctx.project_id:
                row_kwargs["project_id"] = ctx.project_id
            row = StrategyRegimeMemory(**row_kwargs)
            session.add(row)
            session.flush()
        else:
            # Best-of-N tracking: only overwrite when the new run is
            # demonstrably better (higher Sharpe). Always bump the
            # observation counter + timestamps.
            if sharpe > float(row.best_sharpe or 0.0):
                row.best_sharpe = sharpe
                row.best_sortino = sortino
                row.best_calmar = calmar
                row.max_drawdown = mdd
                row.backtest_run_id = backtest_run_id
                if notes:
                    merged = dict(row.notes or {})
                    merged.update(notes)
                    row.notes = merged
            row.n_observations = int(row.n_observations or 0) + 1
            row.last_observed_at = now
            row.updated_at = now

        payload = _row_to_dict(row)

    redis = _redis_client()
    if redis is not None:
        try:
            redis.delete(_redis_key(ctx.workspace_id, strategy_id, regime))
        except Exception:  # noqa: BLE001
            pass
    return payload


__all__ = ["get_best_params", "record_observation", "top_k_for_regime"]
