"""Bull vs Bear debate visualizer.

Renders a two-column layout (green Bull, red Bear) per debate round
with the argument text and cited evidence. Sources its rows from
``GET /agentic/debates/{crew_run_id}``.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import solara

from aqp.ui.components.data.use_api import use_api


@solara.component
def DebateVisualizer(crew_run_id: str | None) -> None:
    """Render the full debate transcript for a crew run."""
    if not crew_run_id:
        solara.Info(
            "Select a decision to see the Bull vs Bear debate.",
            dense=True,
        )
        return

    result = use_api(f"/agentic/debates/{crew_run_id}", default=[])
    if result.loading:
        solara.Info("Loading debate…", dense=True)
        return
    if result.error:
        solara.Error(f"Failed to load debate: {result.error}", dense=True)
        return

    rows: list[dict[str, Any]] = list(result.value or [])
    if not rows:
        solara.Info(
            "No debate turns recorded. The preset may have ``max_debate_rounds=0`` "
            "or the crew run was aborted before the debate phase.",
            dense=True,
        )
        return

    rounds: dict[int, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"bull": [], "bear": []}
    )
    for row in rows:
        side = str(row.get("side", "")).lower()
        if side in ("bull", "bear"):
            rounds[int(row.get("round", 0))][side].append(row)

    with solara.Column(gap="14px", style={"flex": "1", "min-width": "0"}):
        total_cost = sum(float(r.get("token_cost_usd") or 0) for r in rows)
        solara.Markdown(
            f"**Rounds:** {len(rounds)}  •  **Turns:** {len(rows)}  •  "
            f"**Debate cost:** ${total_cost:.4f}"
        )
        for round_idx in sorted(rounds):
            _render_round(round_idx, rounds[round_idx])


def _render_round(round_idx: int, turns: dict[str, list[dict[str, Any]]]) -> None:
    with solara.Column(
        gap="8px",
        style={
            "padding": "10px 12px",
            "border": "1px solid rgba(148,163,184,0.2)",
            "border-radius": "10px",
            "background": "rgba(15,23,42,0.30)",
        },
    ):
        solara.Markdown(
            f"### Round {round_idx + 1}",
            style={"font-size": "1em"},
        )
        with solara.Row(gap="12px", style={"align-items": "stretch"}):
            with solara.Column(style={"flex": "1", "min-width": "0"}, gap="6px"):
                _column_header("Bull", "#22c55e")
                for t in turns["bull"]:
                    _render_turn(t, "#22c55e")
                if not turns["bull"]:
                    solara.Info("No bull turn recorded.", dense=True)
            with solara.Column(style={"flex": "1", "min-width": "0"}, gap="6px"):
                _column_header("Bear", "#ef4444")
                for t in turns["bear"]:
                    _render_turn(t, "#ef4444")
                if not turns["bear"]:
                    solara.Info("No bear turn recorded.", dense=True)


def _column_header(label: str, color: str) -> None:
    solara.Div(
        children=[solara.Text(label)],
        style={
            "padding": "2px 10px",
            "border-radius": "12px",
            "background": color,
            "color": "white",
            "font-weight": "700",
            "font-size": "0.85em",
            "letter-spacing": "0.04em",
            "align-self": "flex-start",
        },
    )


def _render_turn(row: dict[str, Any], color: str) -> None:
    with solara.Div(
        style={
            "padding": "8px 10px",
            "border-left": f"3px solid {color}",
            "background": "rgba(30,41,59,0.55)",
            "border-radius": "4px",
        }
    ):
        argument = str(row.get("argument", ""))
        solara.Markdown(
            argument or "_(no argument)_",
            style={
                "color": "rgba(226,232,240,0.95)",
                "font-size": "0.92em",
                "margin-bottom": "4px",
            },
        )
        cites = list(row.get("cites") or [])
        if cites:
            with solara.Row(gap="4px", style={"flex-wrap": "wrap"}):
                for c in cites:
                    solara.Div(
                        children=[solara.Text(f"cite: {c}")],
                        style={
                            "padding": "1px 6px",
                            "border-radius": "8px",
                            "border": "1px solid rgba(148,163,184,0.35)",
                            "color": "rgba(148,163,184,0.9)",
                            "font-size": "0.72em",
                        },
                    )
        cost = float(row.get("token_cost_usd") or 0)
        if cost:
            solara.Text(
                f"cost: ${cost:.4f}",
                style={
                    "color": "rgba(148,163,184,0.7)",
                    "font-size": "0.72em",
                    "margin-top": "4px",
                },
            )
