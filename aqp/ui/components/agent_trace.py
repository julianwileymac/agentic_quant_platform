"""Live agent-trace viewer — polls the REST API for task progress.

Uses a simple polling loop instead of a real WebSocket client (which Solara
supports, but polling keeps the first-draft UI simple and robust).
"""
from __future__ import annotations

from datetime import datetime

import solara


@solara.component
def AgentTrace(messages: list[dict]) -> None:
    with solara.Card("Agent Trace"):
        if not messages:
            solara.Markdown("_Waiting for agent output…_")
            return
        for m in messages:
            ts = m.get("timestamp")
            ts_str = ""
            if ts:
                try:
                    ts_str = datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
                except Exception:
                    ts_str = str(ts)
            stage = m.get("stage", "info").upper()
            msg = m.get("message", "")
            solara.Markdown(f"`{ts_str}` **[{stage}]** {msg}")
