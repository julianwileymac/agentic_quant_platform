"""High-level orchestration for agentic backtesting pipelines."""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _pick_symbols(
    symbols: list[str],
    idx: int,
    *,
    max_symbols: int | None = None,
    rotate: bool = True,
) -> list[str]:
    clean = [str(s).strip() for s in symbols if str(s).strip()]
    if not clean:
        return []
    if not max_symbols or max_symbols <= 0 or max_symbols >= len(clean):
        return clean
    n = int(max_symbols)
    if not rotate:
        return clean[:n]
    offset = idx % len(clean)
    ordered = clean[offset:] + clean[:offset]
    return ordered[:n]


def _window_for_variant(
    start: str,
    end: str,
    idx: int,
    total: int,
    *,
    mode: str = "fixed",
) -> tuple[str, str]:
    if mode != "rolling" or total <= 1:
        return start, end
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    if e <= s:
        return start, end
    window = (e - s) / total
    vs = s + window * idx
    ve = min(e, vs + window)
    return str(vs.date()), str(ve.date())


def _apply_conditions(cfg: dict[str, Any], conditions: dict[str, Any]) -> dict[str, Any]:
    """Inject generic condition filters into known strategy kwargs."""
    out = deepcopy(cfg)
    strategy = dict(out.get("strategy") or {})
    kwargs = dict(strategy.get("kwargs") or {})
    kwargs["conditions"] = dict(conditions or {})
    strategy["kwargs"] = kwargs
    out["strategy"] = strategy
    return out


def run_agentic_pipeline(
    *,
    cfg: dict[str, Any],
    symbols: list[str],
    start: str,
    end: str,
    strategy_id: str,
    run_name: str,
    x_backtests: int,
    mode: str,
    skip_precompute: bool,
    rebalance_frequency: str,
    preset: str | None,
    provider: str | None,
    deep_model: str | None,
    quick_model: str | None,
    max_debate_rounds: int | None,
    universe_filter: dict[str, Any] | None,
    conditions: dict[str, Any] | None,
    runner: Callable[..., dict[str, Any]],
    on_progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Run ``x_backtests`` variants and aggregate diagnostics."""
    n = max(1, int(x_backtests or 1))
    ufilter = dict(universe_filter or {})
    conds = dict(conditions or {})
    sweep_mode = str(ufilter.get("sweep_mode") or "fixed").strip().lower()
    rotate = bool(ufilter.get("rotate_symbols", True))
    max_symbols = int(ufilter["max_symbols"]) if ufilter.get("max_symbols") else None

    variants: list[dict[str, Any]] = []
    for idx in range(n):
        v_start, v_end = _window_for_variant(start, end, idx, n, mode=sweep_mode)
        v_symbols = _pick_symbols(symbols, idx, max_symbols=max_symbols, rotate=rotate)
        v_cfg = _apply_conditions(cfg, conds)
        v_cfg.setdefault("agentic_pipeline", {})
        v_cfg["agentic_pipeline"].update(
            {
                "variant_index": idx,
                "variant_count": n,
                "window_start": v_start,
                "window_end": v_end,
                "symbols": v_symbols,
                "conditions": conds,
                "universe_filter": ufilter,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        v_run_name = f"{run_name}-v{idx + 1:02d}" if n > 1 else run_name
        v_strategy = f"{strategy_id}-v{idx + 1:02d}" if n > 1 else strategy_id
        if on_progress:
            on_progress((idx / max(n, 1)) * 100.0, f"Running variant {idx + 1}/{n}: {v_run_name}")
        try:
            result = runner(
                cfg=v_cfg,
                symbols=v_symbols,
                start=v_start,
                end=v_end,
                strategy_id=v_strategy,
                run_name=v_run_name,
                preset=preset,
                provider=provider,
                deep_model=deep_model,
                quick_model=quick_model,
                max_debate_rounds=max_debate_rounds,
                rebalance_frequency=rebalance_frequency,
                mode=mode,
                skip_precompute=skip_precompute,
            )
            variants.append(
                {
                    "variant_index": idx,
                    "run_name": v_run_name,
                    "strategy_id": v_strategy,
                    "symbols": v_symbols,
                    "start": v_start,
                    "end": v_end,
                    "status": "completed",
                    "result": result,
                }
            )
        except Exception as exc:  # noqa: BLE001
            variants.append(
                {
                    "variant_index": idx,
                    "run_name": v_run_name,
                    "strategy_id": v_strategy,
                    "symbols": v_symbols,
                    "start": v_start,
                    "end": v_end,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    completed = [v for v in variants if v.get("status") == "completed" and isinstance(v.get("result"), dict)]
    metric_rows = [v["result"] for v in completed]
    agg: dict[str, Any] = {}
    for key in ("sharpe", "sortino", "total_return", "max_drawdown", "final_equity", "n_trades"):
        vals = [float(r[key]) for r in metric_rows if r.get(key) is not None]
        if vals:
            agg[f"{key}_avg"] = float(sum(vals) / len(vals))
            agg[f"{key}_min"] = float(min(vals))
            agg[f"{key}_max"] = float(max(vals))

    if on_progress:
        on_progress(100.0, "Pipeline complete")
    return {
        "run_name": run_name,
        "strategy_id": strategy_id,
        "variant_count": n,
        "completed_count": len(completed),
        "failed_count": n - len(completed),
        "variants": variants,
        "aggregate": agg,
    }

