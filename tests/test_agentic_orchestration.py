from __future__ import annotations

from aqp.agents.trading.orchestration import run_agentic_pipeline


def test_run_agentic_pipeline_aggregates_variants() -> None:
    calls: list[dict] = []

    def _runner(**kwargs):
        calls.append(kwargs)
        return {
            "run_id": f"run-{len(calls)}",
            "sharpe": 1.0 + len(calls),
            "sortino": 1.5 + len(calls),
            "total_return": 0.1 * len(calls),
            "max_drawdown": -0.01 * len(calls),
            "final_equity": 100000 + (1000 * len(calls)),
            "n_trades": 10 * len(calls),
        }

    payload = run_agentic_pipeline(
        cfg={"strategy": {"kwargs": {}}, "backtest": {"kwargs": {}}},
        symbols=["AAPL", "MSFT", "NVDA"],
        start="2024-01-01",
        end="2024-06-30",
        strategy_id="agentic-test",
        run_name="agentic-test",
        x_backtests=3,
        mode="precompute",
        skip_precompute=False,
        rebalance_frequency="weekly",
        preset="trader_crew_quick",
        provider="ollama",
        deep_model="nemotron",
        quick_model="llama3.2",
        max_debate_rounds=2,
        universe_filter={"max_symbols": 2, "rotate_symbols": True, "sweep_mode": "rolling"},
        conditions={"entry_rule": "close > sma_20"},
        runner=_runner,
    )

    assert payload["variant_count"] == 3
    assert payload["completed_count"] == 3
    assert payload["failed_count"] == 0
    assert len(payload["variants"]) == 3
    assert payload["aggregate"]["sharpe_avg"] > 1.0
    assert len(calls) == 3
    assert all(len(c["symbols"]) == 2 for c in calls)
