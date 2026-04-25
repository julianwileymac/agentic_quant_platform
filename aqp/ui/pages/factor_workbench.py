"""Factor Workbench — tabbed IC tear sheet, formula lab, and operator library.

Supersedes the old narrow ``factor_eval.py`` page. Three tabs:

- **Evaluate** — submit an Alphalens-style job and stream worker progress.
- **Formula Lab** — type a formula against the :mod:`aqp.data.expressions`
  DSL, preview it on a small universe via ``POST /factors/preview``, and
  inspect the resulting IC summary before sending a full evaluation.
- **Library** — read-only table of registered operators + built-in factor
  names with inline docs and a click-to-insert shortcut.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara

from aqp.ui.api_client import post
from aqp.ui.components import (
    EntityTable,
    Heatmap,
    MetricTile,
    StatsGrid,
    TabPanel,
    TabSpec,
    TaskStreamer,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader

BUILTIN_FACTORS = [
    {"name": "mean_reversion_zscore", "description": "Rolling z-score of close over lookback."},
    {"name": "momentum_rank", "description": "Cross-sectional rank of trailing returns."},
]

EXAMPLE_FORMULAS = [
    ("Mean reversion z-score", "($close - Mean($close, 20)) / Std($close, 20)"),
    ("Momentum rank", "Rank( $close / Ref($close, 90) - 1 )"),
    ("Volatility regime", "Std(Log($close / Ref($close, 1)), 60)"),
    ("OBV-style divergence", "Corr($close, $volume, 20)"),
]


@solara.component
def Page() -> None:
    # --- shared form state ---
    symbols = solara.use_reactive("AAPL,MSFT,SPY,GOOGL,AMZN,TSLA,NVDA")
    start = solara.use_reactive("2023-01-01")
    end = solara.use_reactive("2024-12-31")
    factor_name = solara.use_reactive("mean_reversion_zscore")
    formula = solara.use_reactive("")
    lookback = solara.use_reactive("20")
    n_quantiles = solara.use_reactive("5")
    horizons = solara.use_reactive("1,5,10,21")

    # --- per-tab state ---
    task_id = solara.use_reactive("")
    preview_formula = solara.use_reactive(EXAMPLE_FORMULAS[0][1])
    preview_result: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    preview_error = solara.use_reactive("")

    operators = use_api("/factors/operators", default=[])

    def _submit_eval() -> None:
        body: dict[str, Any] = {
            "symbols": [s.strip() for s in symbols.value.split(",") if s.strip()],
            "start": start.value,
            "end": end.value,
            "factor_name": factor_name.value,
            "lookback": _to_int(lookback.value, 20),
            "n_quantiles": _to_int(n_quantiles.value, 5),
            "horizons": [
                _to_int(h, 1) for h in horizons.value.split(",") if h.strip()
            ],
        }
        if formula.value.strip():
            body["formula"] = formula.value.strip()
        try:
            resp = post("/factors/evaluate", json=body)
            task_id.set(resp.get("task_id", ""))
        except Exception as exc:  # noqa: BLE001
            preview_error.set(str(exc))

    def _run_preview() -> None:
        preview_error.set("")
        body = {
            "symbols": [s.strip() for s in symbols.value.split(",") if s.strip()][:10],
            "formula": preview_formula.value,
            "start": start.value,
            "end": end.value,
            "horizons": [
                _to_int(h, 1) for h in horizons.value.split(",") if h.strip()
            ],
            "n_quantiles": _to_int(n_quantiles.value, 5),
            "rows": 80,
        }
        try:
            preview_result.set(post("/factors/preview", json=body) or {})
        except Exception as exc:  # noqa: BLE001
            preview_error.set(str(exc))
            preview_result.set({})

    PageHeader(
        title="Factor Workbench",
        subtitle=(
            "Alphalens-style IC / quantile / turnover tear sheet plus an "
            "expressions DSL playground over the local Parquet lake."
        ),
        icon="🧪",
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        _universe_strip(symbols, start, end, horizons)
        TabPanel(
            tabs=[
                TabSpec(
                    key="evaluate",
                    label="Evaluate",
                    render=lambda: _evaluate_tab(
                        factor_name=factor_name,
                        formula=formula,
                        lookback=lookback,
                        n_quantiles=n_quantiles,
                        task_id=task_id.value,
                        on_submit=_submit_eval,
                    ),
                ),
                TabSpec(
                    key="lab",
                    label="Formula Lab",
                    render=lambda: _formula_lab(
                        preview_formula=preview_formula,
                        preview_result=preview_result.value,
                        preview_error=preview_error.value,
                        on_run=_run_preview,
                    ),
                ),
                TabSpec(
                    key="library",
                    label="Library",
                    render=lambda: _library(
                        operators=operators.value or [],
                        on_copy_formula=lambda f: preview_formula.set(f),
                    ),
                ),
            ]
        )


def _universe_strip(
    symbols: solara.Reactive[str],
    start: solara.Reactive[str],
    end: solara.Reactive[str],
    horizons: solara.Reactive[str],
) -> None:
    with solara.Card("Universe"):
        solara.InputText("Universe (comma-separated)", value=symbols)
        with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
            solara.InputText("start", value=start)
            solara.InputText("end", value=end)
            solara.InputText("horizons (days, comma-separated)", value=horizons)


def _evaluate_tab(
    *,
    factor_name: solara.Reactive[str],
    formula: solara.Reactive[str],
    lookback: solara.Reactive[str],
    n_quantiles: solara.Reactive[str],
    task_id: str,
    on_submit,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Factor"):
            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                solara.Select(
                    label="Built-in factor",
                    value=factor_name,
                    values=[f["name"] for f in BUILTIN_FACTORS],
                )
                solara.InputText("lookback", value=lookback)
                solara.InputText("quantiles", value=n_quantiles)
            solara.InputText("Custom formula (optional)", value=formula)
            solara.Button("Evaluate", on_click=on_submit, color="primary")
        if task_id:
            TaskStreamer(task_id=task_id, title="Evaluation stream", show_result=True)
            solara.Markdown(
                "_Final tear sheet lands in MLflow under `aqp.component=factor_eval`._"
            )


def _formula_lab(
    *,
    preview_formula: solara.Reactive[str],
    preview_result: dict[str, Any],
    preview_error: str,
    on_run,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Formula"):
            solara.InputText("DSL formula (use $close, $high, $low, $volume)", value=preview_formula)
            with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
                for label, expr in EXAMPLE_FORMULAS:
                    solara.Button(
                        label,
                        on_click=lambda expr=expr: preview_formula.set(expr),
                        dense=True,
                        outlined=True,
                    )
            solara.Button("Preview", on_click=on_run, color="primary")
            if preview_error:
                solara.Error(preview_error)
            if preview_result.get("message"):
                solara.Warning(preview_result["message"])

        if preview_result.get("rows"):
            summary = preview_result.get("summary") or {}
            _preview_summary(summary)
            EntityTable(
                rows=preview_result["rows"],
                columns=["timestamp", "vt_symbol", "factor", "close"],
                title=f"Sample rows ({preview_result.get('n_rows')} total across {preview_result.get('n_symbols')} symbols)",
                empty="_No rows in preview._",
            )


def _preview_summary(summary: dict[str, Any]) -> None:
    if not summary or "error" in summary:
        if "error" in summary:
            solara.Markdown(f"_IC summary failed: {summary['error']}_")
        return
    horizons = sorted(summary.keys(), key=lambda k: int(str(k).replace("fwd_", "") or 0))
    if not horizons:
        return
    with solara.Column(gap="8px"):
        solara.Markdown("**Mean Information Coefficient**")
        with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
            for h in horizons:
                mean_ic = summary[h].get("mean")
                MetricTile(
                    label=h,
                    value=mean_ic,
                    hint=f"IR {summary[h].get('ir', 0):.2f}",
                    tone=_ic_tone(mean_ic),
                )
        matrix = pd.DataFrame(
            {h: [summary[h].get(k) for k in ("mean", "ir", "t_stat", "hit_rate")] for h in horizons},
            index=["mean", "ir", "t_stat", "hit_rate"],
        )
        Heatmap(
            matrix,
            title="IC statistics",
            xaxis_title="horizon",
            yaxis_title="metric",
            height=240,
            show_values=True,
            value_fmt=".3f",
        )


def _ic_tone(mean_ic: Any) -> str:
    if mean_ic is None:
        return "neutral"
    try:
        v = float(mean_ic)
    except (TypeError, ValueError):
        return "neutral"
    if v >= 0.03:
        return "success"
    if v <= -0.03:
        return "error"
    return "warning"


def _library(operators: list[dict[str, Any]], on_copy_formula) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Built-in factors"):
            EntityTable(
                rows=BUILTIN_FACTORS,
                columns=["name", "description"],
                searchable=False,
                empty="_No built-ins registered._",
            )
        with solara.Card("Expression operators"):
            if not operators:
                solara.Markdown("_No operators (is the API up?)._")
            else:
                EntityTable(
                    rows=operators,
                    columns=["category", "name", "arity", "description"],
                    title=f"{len(operators)} registered",
                )
        with solara.Card("Example formulas"):
            with solara.Column(gap="6px"):
                for label, expr in EXAMPLE_FORMULAS:
                    with solara.Row(gap="8px", style={"align-items": "center"}):
                        solara.Markdown(f"**{label}** — `{expr}`")
                        solara.Button(
                            "Try in Lab",
                            on_click=lambda expr=expr: on_copy_formula(expr),
                            dense=True,
                            outlined=True,
                        )


def _to_int(text: str, default: int) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return default
