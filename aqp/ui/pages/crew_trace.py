"""Crew Trace — live view of an agentic research crew.

Left rail: list of recent :class:`CrewRun` rows with status pills and a
prompt-search box. Right pane: for the selected run, a per-agent swim
lane (Data Scout → Hypothesis Designer → Backtester → Risk Controller →
Performance Evaluator → Meta-Agent) that consumes the
``/chat/stream/{task_id}`` WebSocket in real time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import solara

from aqp.ui.api_client import post
from aqp.ui.components import (
    MetricTile,
    SplitPane,
    TaskStreamer,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader

AGENT_LANES: list[tuple[str, str, str]] = [
    ("Data Scout", "data scout", "🔎"),
    ("Hypothesis Designer", "hypothesis", "💡"),
    ("Strategy Backtester", "backtester", "⚙️"),
    ("Risk Controller", "risk", "🛡️"),
    ("Performance Evaluator", "evaluator", "📊"),
    ("Meta-Agent", "meta-agent", "🧩"),
]


@solara.component
def Page() -> None:
    crews = use_api("/agents/crews?limit=40", default=[], interval=10.0)
    selected_task = solara.use_reactive("")
    prompt_draft = solara.use_reactive("")
    running_task = solara.use_reactive("")

    def _run_crew() -> None:
        if not prompt_draft.value.strip():
            return
        try:
            resp = post(
                "/agents/crew/run",
                json={"prompt": prompt_draft.value.strip()},
            )
            tid = resp.get("task_id", "")
            running_task.set(tid)
            selected_task.set(tid)
            crews.refresh()
            prompt_draft.set("")
        except Exception as exc:  # noqa: BLE001
            solara.Error(str(exc))

    PageHeader(
        title="Agent Crew Trace",
        subtitle=(
            "Dispatch the research crew and watch each agent's output stream "
            "into its own swim lane. Uses the same ``/chat/stream/{task_id}`` "
            "WebSocket the workers publish to."
        ),
        icon="🧩",
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        SplitPane(
            left_width="340px",
            left=lambda: _left_rail(
                crews=crews.value or [],
                selected_task=selected_task,
                prompt_draft=prompt_draft,
                on_run=_run_crew,
                on_refresh=crews.refresh,
            ),
            right=lambda: _right_pane(
                crews=crews.value or [],
                task_id=selected_task.value,
            ),
        )


def _left_rail(
    *,
    crews: list[dict[str, Any]],
    selected_task: solara.Reactive[str],
    prompt_draft: solara.Reactive[str],
    on_run,
    on_refresh,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Kick off a crew"):
            solara.InputTextArea(
                "Prompt",
                value=prompt_draft,
                rows=4,
            )
            solara.Button("Run crew", on_click=on_run, color="primary")
        with solara.Card("Recent crews"):
            with solara.Row(gap="6px"):
                solara.Button("Refresh", on_click=on_refresh, outlined=True, dense=True)
            if not crews:
                solara.Markdown("_No crew runs yet._")
                return
            for c in crews:
                _crew_button(c, selected_task)


def _crew_button(
    crew: dict[str, Any], selected_task: solara.Reactive[str]
) -> None:
    status = (crew.get("status") or "queued").lower()
    bg, fg = _STATUS_COLORS.get(status, ("#334155", "#cbd5e1"))
    active = selected_task.value == crew.get("task_id")
    prompt = (crew.get("prompt") or "")[:80]
    started = _fmt_ts(crew.get("started_at"))
    with solara.Div(
        style={
            "background": bg,
            "color": fg,
            "padding": "10px 12px",
            "border-radius": "8px",
            "border-left": "3px solid #38bdf8" if active else "3px solid transparent",
            "cursor": "pointer",
            "margin-bottom": "6px",
        }
    ):
        solara.Button(
            label=f"{status.upper()} · {prompt}",
            on_click=lambda t=crew.get("task_id", ""): selected_task.set(t),
            text=True,
            dense=True,
            style={
                "text-align": "left",
                "width": "100%",
                "color": fg,
            },
        )
        solara.Markdown(
            f"<div style='font-size:10px;opacity:0.75'>task {crew.get('task_id', '')[:12]} · {started}</div>"
        )


_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "queued": ("#334155", "#cbd5e1"),
    "running": ("#1e3a8a", "#dbeafe"),
    "completed": ("#064e3b", "#bbf7d0"),
    "error": ("#7f1d1d", "#fecaca"),
}


def _right_pane(crews: list[dict[str, Any]], task_id: str) -> None:
    if not task_id:
        with solara.Card():
            solara.Markdown("_Pick a crew on the left to inspect its stream._")
        return
    selected = next((c for c in crews if c.get("task_id") == task_id), None)
    if selected is None:
        with solara.Card():
            solara.Markdown(f"_Task `{task_id}` not in the recent list._")
        return

    events_api = use_api(f"/agents/crews/{task_id}/events", default={})
    all_events = (events_api.value or {}).get("events") or []

    _kpi_strip(selected, len(all_events))
    TaskStreamer(
        task_id=task_id,
        title="Live WebSocket stream",
        show_result=True,
    )
    _swim_lanes(events=all_events)
    _prompt_card(selected)


def _kpi_strip(crew: dict[str, Any], event_count: int) -> None:
    status = (crew.get("status") or "queued").lower()
    tone = {
        "queued": "neutral",
        "running": "info",
        "completed": "success",
        "error": "error",
    }.get(status, "neutral")
    duration = _duration(crew.get("started_at"), crew.get("completed_at"))
    cost = float(crew.get("cost_usd") or 0.0)
    crew_type = crew.get("crew_type") or "research"
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile("Status", status.upper(), tone=tone)
        MetricTile("Duration", duration or "—")
        MetricTile("Events buffered", event_count)
        MetricTile("Crew type", crew_type)
        MetricTile(
            "Crew",
            crew.get("crew_name") or "research",
        )
        MetricTile(
            "Total cost",
            f"${cost:.4f}" if cost else "—",
            tone="info" if cost else "neutral",
        )


def _swim_lanes(events: list[dict[str, Any]]) -> None:
    """Bucket events into per-agent lanes by keyword match on the message.

    The Celery task emits plain text — not structured events — so we do a
    cheap substring heuristic. This is deliberately imperfect; any agent
    mention is good enough for a visual trace.
    """
    lane_buckets: dict[str, list[dict[str, Any]]] = {name: [] for name, _, _ in AGENT_LANES}
    unassigned: list[dict[str, Any]] = []
    for event in events:
        message = (event.get("message") or event.get("raw") or "").lower()
        matched = False
        for name, needle, _ in AGENT_LANES:
            if needle in message:
                lane_buckets[name].append(event)
                matched = True
                break
        if not matched:
            unassigned.append(event)

    with solara.Card("Agent swim lanes"):
        if not events:
            solara.Markdown("_No events yet._")
            return
        for name, _needle, glyph in AGENT_LANES:
            bucket = lane_buckets[name]
            with solara.Column(
                gap="4px",
                style={
                    "padding": "8px 10px",
                    "background": "rgba(148, 163, 184, 0.06)",
                    "border-radius": "8px",
                    "margin-bottom": "6px",
                },
            ):
                solara.Markdown(
                    f"<div style='font-size:12px;font-weight:600;letter-spacing:0.02em'>"
                    f"{glyph} {name}</div>"
                )
                if not bucket:
                    solara.Markdown(
                        "<div style='font-size:11px;opacity:0.5'>(no events)</div>"
                    )
                    continue
                for event in bucket[-5:]:
                    solara.Markdown(
                        f"<div style='font-size:11px;opacity:0.8'>`{_event_time(event)}` "
                        f"{event.get('message') or event.get('raw') or ''}</div>"
                    )
        if unassigned:
            with solara.Details(summary=f"Unclassified events ({len(unassigned)})"):
                for event in unassigned[-20:]:
                    solara.Markdown(
                        f"`{_event_time(event)}` {event.get('message') or event.get('raw') or ''}"
                    )


def _prompt_card(crew: dict[str, Any]) -> None:
    with solara.Card("Prompt"):
        solara.Markdown(f"> {crew.get('prompt') or '—'}")
    if crew.get("error"):
        solara.Error(crew["error"])


def _duration(started: Any, completed: Any) -> str:
    if not started:
        return ""
    try:
        s = datetime.fromisoformat(str(started))
    except ValueError:
        return ""
    end = None
    if completed:
        try:
            end = datetime.fromisoformat(str(completed))
        except ValueError:
            end = None
    delta = (end or datetime.utcnow()) - s
    total = int(delta.total_seconds())
    if total < 60:
        return f"{total}s"
    mins, secs = divmod(total, 60)
    if mins < 60:
        return f"{mins}m {secs}s"
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins}m"


def _event_time(event: dict[str, Any]) -> str:
    ts = event.get("timestamp")
    if not ts:
        return "--:--:--"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return str(ts)


def _fmt_ts(value: Any) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(value)
