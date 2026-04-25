"""Agentic Trader Quickstart Wizard.

A five-step Solara wizard that walks a user from "pick tickers" to
"watch the agent trade on historical bars in a few minutes":

1. **Goal & universe** — symbols + start/end dates.
2. **Agent recipe** — preset, provider, deep/quick model, debate rounds.
3. **Data & rules** — rebalance cadence, position cap, benchmark.
4. **Review & launch** — preview the config, submit to ``/agentic/backtest``.
5. **Results** — live task progress + decision timeline + debate view.

Under the hood the wizard just POSTs an :class:`AgenticBacktestRequest`
and polls the returned task id. All of the heavy lifting —
precompute, backtest replay, sidecar persistence — happens in
:mod:`aqp.tasks.agentic_backtest_tasks`.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import solara
import yaml

from aqp.ui.api_client import get, post
from aqp.ui.components.data.task_streamer import TaskStreamer
from aqp.ui.components.debate_visualizer import DebateVisualizer
from aqp.ui.components.decision_timeline import DecisionTimeline
from aqp.ui.components.layout.stepper import StepSpec, Stepper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_symbols() -> list[str]:
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]


def _today() -> str:
    return date.today().isoformat()


def _six_months_ago() -> str:
    return (date.today() - timedelta(days=180)).isoformat()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


@solara.component
def Page() -> None:
    # Step 1 — universe
    symbols_raw = solara.use_reactive(",".join(_default_symbols()))
    start = solara.use_reactive(_six_months_ago())
    end = solara.use_reactive(_today())

    # Step 2 — agent recipe
    preset = solara.use_reactive("trader_crew_quick")
    provider = solara.use_reactive("")
    deep_model = solara.use_reactive("")
    quick_model = solara.use_reactive("")
    max_debate_rounds = solara.use_reactive(1)

    providers_data = solara.use_reactive({"providers": [], "active": "", "available": []})
    presets_data = solara.use_reactive({"presets": []})

    def _load_choices() -> None:
        try:
            providers_data.set(get("/agentic/providers") or {})
            presets_data.set(get("/agentic/presets") or {})
        except Exception:
            pass

    solara.use_effect(_load_choices, [])

    # Step 3 — data & rules
    rebalance_frequency = solara.use_reactive("weekly")
    position_cap_pct = solara.use_reactive(15)
    starting_cash = solara.use_reactive(100000)
    benchmark = solara.use_reactive("SPY")
    mode = solara.use_reactive("precompute")

    # Step 4/5 — run state
    task_id = solara.use_reactive("")
    backtest_id = solara.use_reactive("")
    crew_run_id = solara.use_reactive("")
    submit_error = solara.use_reactive("")

    step_index = solara.use_reactive(0)

    # --- Step validators ---
    def validate_step_1() -> str | None:
        syms = _parse_symbols(symbols_raw.value)
        if not syms:
            return "Please enter at least one symbol."
        try:
            s, e = start.value, end.value
            if not (s and e and s < e):
                return "start must be before end and both must be non-empty."
        except Exception:
            return "Dates must be ISO (YYYY-MM-DD)."
        return None

    def validate_step_2() -> str | None:
        if not preset.value:
            return "Pick a crew preset."
        if provider.value == "" and providers_data.value.get("active", "") == "":
            return None  # fall through to server default
        return None

    def validate_step_3() -> str | None:
        if position_cap_pct.value <= 0 or position_cap_pct.value > 100:
            return "Position cap must be between 1% and 100%."
        return None

    # --- Submit ---
    def submit() -> None:
        submit_error.set("")
        payload = {
            "symbols": _parse_symbols(symbols_raw.value),
            "start": start.value,
            "end": end.value,
            "preset": preset.value,
            "provider": provider.value,
            "deep_model": deep_model.value,
            "quick_model": quick_model.value,
            "max_debate_rounds": int(max_debate_rounds.value),
            "rebalance_frequency": rebalance_frequency.value,
            "mode": mode.value,
            "run_name": f"quickstart-{_parse_symbols(symbols_raw.value)[0].lower()}",
        }
        try:
            r = post("/agentic/backtest", json=payload) or {}
            tid = r.get("task_id", "")
            task_id.set(tid)
            step_index.set(len(STEPS) - 1)
        except Exception as exc:
            submit_error.set(str(exc))

    def _reset() -> None:
        task_id.set("")
        backtest_id.set("")
        crew_run_id.set("")
        submit_error.set("")
        step_index.set(0)

    # --- Polling: once a task completes, pull the result → backtest_id ---
    def _poll_result() -> None:
        if not task_id.value:
            return

        def _try_fetch() -> None:
            try:
                crews = get(f"/agents/crews/{task_id.value}") or {}
                result = crews.get("result") or {}
                if result.get("run_id"):
                    backtest_id.set(str(result["run_id"]))
            except Exception:
                pass

        _try_fetch()

    solara.use_effect(_poll_result, [task_id.value])

    STEPS = [
        StepSpec(
            key="goal",
            label="Goal & universe",
            description="Which tickers and what period should the agent trade?",
            render=lambda: _step_goal_universe(symbols_raw, start, end),
            validate=validate_step_1,
        ),
        StepSpec(
            key="recipe",
            label="Agent recipe",
            description="Pick the LLM and how many rounds of Bull/Bear debate to run.",
            render=lambda: _step_agent_recipe(
                preset,
                provider,
                deep_model,
                quick_model,
                max_debate_rounds,
                providers_data,
                presets_data,
            ),
            validate=validate_step_2,
        ),
        StepSpec(
            key="rules",
            label="Data & rules",
            description="Rebalance cadence, position limits, and execution mode.",
            render=lambda: _step_data_rules(
                rebalance_frequency,
                position_cap_pct,
                starting_cash,
                benchmark,
                mode,
            ),
            validate=validate_step_3,
        ),
        StepSpec(
            key="review",
            label="Review & launch",
            description="Confirm the resolved config and kick off the backtest.",
            render=lambda: _step_review(
                symbols_raw,
                start,
                end,
                preset,
                provider,
                deep_model,
                quick_model,
                max_debate_rounds,
                rebalance_frequency,
                position_cap_pct,
                starting_cash,
                benchmark,
                mode,
                submit_error,
            ),
        ),
        StepSpec(
            key="results",
            label="Results",
            description="Live progress, then the decision timeline and debate transcript.",
            render=lambda: _step_results(task_id, backtest_id, crew_run_id),
        ),
    ]

    with solara.Column(gap="18px", style={"padding": "16px", "min-height": "80vh"}):
        solara.Markdown("# Agentic Trader Quickstart")
        solara.Markdown(
            "A guided wizard that creates an LLM trader, backtests it over your chosen window, "
            "and surfaces every decision + debate alongside the equity curve."
        )

        Stepper(
            steps=STEPS,
            step_index=step_index,
            on_finish=submit,
            next_label="Next →",
            finish_label=(
                "Launch backtest 🚀"
                if step_index.value == len(STEPS) - 2
                else "Reset"
            ),
        )

        with solara.Row(justify="end"):
            solara.Button("Restart wizard", text=True, on_click=_reset)


# ---------------------------------------------------------------------------
# Step renderers
# ---------------------------------------------------------------------------


def _step_goal_universe(
    symbols_raw: solara.Reactive,
    start: solara.Reactive,
    end: solara.Reactive,
) -> None:
    solara.InputText("Symbols (comma separated)", value=symbols_raw)
    with solara.Row(gap="12px"):
        solara.InputText("Start date (YYYY-MM-DD)", value=start)
        solara.InputText("End date (YYYY-MM-DD)", value=end)
    parsed = _parse_symbols(symbols_raw.value)
    solara.Markdown(f"Will trade **{len(parsed)}** symbols.")


def _step_agent_recipe(
    preset: solara.Reactive,
    provider: solara.Reactive,
    deep_model: solara.Reactive,
    quick_model: solara.Reactive,
    max_debate_rounds: solara.Reactive,
    providers_data: solara.Reactive,
    presets_data: solara.Reactive,
) -> None:
    preset_items = [p.get("name", "") for p in (presets_data.value.get("presets") or [])]
    if not preset_items:
        preset_items = ["trader_crew_quick", "trader_crew"]
    provider_items = [""] + [p.get("slug", "") for p in (providers_data.value.get("providers") or [])]

    with solara.Row(gap="12px"):
        solara.Select(label="Preset", value=preset, values=preset_items)
        solara.Select(
            label=f"Provider (default: {providers_data.value.get('active', 'ollama')})",
            value=provider,
            values=provider_items,
        )
    with solara.Row(gap="12px"):
        solara.InputText("Deep model (blank uses default)", value=deep_model)
        solara.InputText("Quick model (blank uses default)", value=quick_model)
    solara.SliderInt(
        "Max debate rounds",
        value=max_debate_rounds,
        min=0,
        max=5,
    )
    solara.Markdown(
        "**Cost preview.** The LLM is called ~"
        "`(debate_rounds × 2 + 6) × symbols × rebalance_dates` times. "
        "Lower the debate rounds and/or pick a cheap provider for exploration runs."
    )

    # Show any providers that are missing API keys so the user isn't
    # surprised when the worker fails.
    missing = [
        p.get("slug", "")
        for p in (providers_data.value.get("providers") or [])
        if p.get("requires_api_key") and not p.get("key_configured")
    ]
    if missing:
        solara.Warning(
            "Missing API keys for: " + ", ".join(missing)
            + ". Set them in your `.env` (AQP_OPENAI_API_KEY, etc.) before running "
            "with those providers.",
            dense=True,
        )


def _step_data_rules(
    rebalance_frequency: solara.Reactive,
    position_cap_pct: solara.Reactive,
    starting_cash: solara.Reactive,
    benchmark: solara.Reactive,
    mode: solara.Reactive,
) -> None:
    with solara.Row(gap="12px"):
        solara.Select(
            label="Rebalance frequency",
            value=rebalance_frequency,
            values=["daily", "weekly", "monthly"],
        )
        solara.SliderInt(
            "Max position size (%)",
            value=position_cap_pct,
            min=1,
            max=50,
        )
    with solara.Row(gap="12px"):
        solara.InputInt("Starting cash (USD)", value=starting_cash)
        solara.Select(
            label="Benchmark",
            value=benchmark,
            values=["SPY", "VOO", "QQQ", "DIA", "IWM"],
        )
    solara.Select(
        label="Execution mode",
        value=mode,
        values=["precompute", "precompute_plus_audit", "live"],
    )


def _step_review(
    symbols_raw: solara.Reactive,
    start: solara.Reactive,
    end: solara.Reactive,
    preset: solara.Reactive,
    provider: solara.Reactive,
    deep_model: solara.Reactive,
    quick_model: solara.Reactive,
    max_debate_rounds: solara.Reactive,
    rebalance_frequency: solara.Reactive,
    position_cap_pct: solara.Reactive,
    starting_cash: solara.Reactive,
    benchmark: solara.Reactive,
    mode: solara.Reactive,
    submit_error: solara.Reactive,
) -> None:
    resolved: dict[str, Any] = {
        "symbols": _parse_symbols(symbols_raw.value),
        "start": start.value,
        "end": end.value,
        "preset": preset.value,
        "provider": provider.value or "(platform default)",
        "deep_model": deep_model.value or "(platform default)",
        "quick_model": quick_model.value or "(platform default)",
        "max_debate_rounds": int(max_debate_rounds.value),
        "rebalance_frequency": rebalance_frequency.value,
        "position_cap_pct": int(position_cap_pct.value),
        "starting_cash": int(starting_cash.value),
        "benchmark": benchmark.value,
        "mode": mode.value,
    }
    solara.Markdown("#### Resolved configuration")
    solara.Markdown(f"```yaml\n{yaml.safe_dump(resolved, sort_keys=False)}\n```")
    if submit_error.value:
        solara.Error(submit_error.value)
    solara.Markdown(
        "Clicking **Launch backtest** will queue a Celery job. The crew runs "
        "on the `agents` queue; the backtest replay uses the `backtest` queue."
    )


def _step_results(
    task_id: solara.Reactive,
    backtest_id: solara.Reactive,
    crew_run_id: solara.Reactive,
) -> None:
    if not task_id.value:
        solara.Info(
            "Go back to **Review & launch** and click *Launch backtest* to start.",
            dense=True,
        )
        return

    TaskStreamer(task_id.value, title="Agentic backtest progress")

    with solara.Row(gap="12px", style={"align-items": "center"}):
        solara.InputText("Backtest ID (auto-fills when the run finishes)", value=backtest_id)
        solara.Button(
            "Refresh decisions",
            on_click=lambda: solara.Info("Hit the backtest tab for a full view."),
        )
    DecisionTimeline(backtest_id.value or None)

    with solara.Row(gap="12px", style={"align-items": "center"}):
        solara.InputText("Crew run ID (for the debate view)", value=crew_run_id)
    DebateVisualizer(crew_run_id.value or None)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in (raw or "").split(",") if s.strip()]
