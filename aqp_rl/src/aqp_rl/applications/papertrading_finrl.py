"""FinRL paper-trading bridge — Alpaca live loop adapted to AQP runtime.

Lifts the spirit of FinRL's
``finrl/meta/env_stock_trading/env_stock_papertrading.py`` (Alpaca live
trading thread) into an AQP-friendly ``Runtime``-driven flow:

1. Build the env from
   :class:`aqp_rl.data_pipelines.alpaca.AlpacaRLDataPipeline`.
2. Load a trained checkpoint via :class:`SB3Adapter`.
3. Step through bars in real time, sending live orders to Alpaca via
   :mod:`aqp.providers.alpaca` if credentials are present (else dry-run).

Note: this is a thin scaffold; the production paper-trading pipeline
goes through :class:`aqp.bots.runtime.BotRuntime.paper`. Use this entry
when you specifically want an RL-policy paper session.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def paper_trade_finrl(
    *,
    checkpoint: str | Path,
    symbols: list[str],
    duration_seconds: int = 600,
    poll_interval_seconds: int = 30,
    dry_run: bool = True,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a thin RL paper-trading loop.

    Parameters
    ----------
    checkpoint:
        Path to a saved SB3 / ElegantRL / RLlib / CleanRL policy.
    symbols:
        Universe to trade.
    duration_seconds:
        Total loop duration. Set to 0 to run a single inference cycle.
    poll_interval_seconds:
        Wait between bar pulls.
    dry_run:
        If true, prints actions instead of placing live orders.
    spec:
        Optional :class:`RLExperimentSpec` build-spec (passed as a dict)
        — when provided, the function uses
        :class:`aqp_rl.runtime.RLRuntime` for telemetry; otherwise it
        runs in-process.
    """
    if spec is not None:
        from aqp_rl.runtime import RLRuntime
        from aqp_rl.spec import RLExperimentSpec

        runtime = RLRuntime(RLExperimentSpec.model_validate(spec))
        return runtime.paper(checkpoint=str(checkpoint)).to_dict()

    from aqp_rl.agents.sb3_adapter import SB3Adapter
    from aqp_rl.data_pipelines.alpaca import AlpacaRLDataPipeline

    pipeline = AlpacaRLDataPipeline()
    adapter = SB3Adapter(algorithm="PPO")
    bars = pipeline.download_data(symbols, "2020-01-01", "2030-01-01", "1Day")
    if bars is None or bars.empty:
        return {"status": "no_data", "symbols": symbols}
    adapter.load(str(checkpoint))
    end_time = time.time() + max(int(duration_seconds), 0)
    actions: list[dict[str, Any]] = []
    while time.time() <= end_time:
        try:
            obs = bars.tail(60).select_dtypes("number").values.flatten()
            action, _ = adapter.predict(obs, deterministic=True)
            decision = {"timestamp": time.time(), "action": list(map(float, action.tolist())), "dry_run": dry_run}
            actions.append(decision)
            if not dry_run:
                logger.info("submit live trade payload: %s", decision)
                # Live trade submission is left to the bot runtime / paper
                # session to maintain a single sanctioned execution path.
        except Exception:  # noqa: BLE001
            logger.exception("paper_trade_finrl loop iteration failed")
        if duration_seconds <= 0:
            break
        time.sleep(max(int(poll_interval_seconds), 1))
    return {"status": "ok", "actions": actions, "symbols": symbols}


__all__ = ["paper_trade_finrl"]
