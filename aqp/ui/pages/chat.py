"""Quant Assistant chat — now split into chat + crew-stream panes."""
from __future__ import annotations

import solara

from aqp.ui.api_client import post
from aqp.ui.components import SplitPane, TaskStreamer, use_api
from aqp.ui.components.chat_message import ChatBubble
from aqp.ui.layout.page_header import PageHeader


@solara.component
def Page() -> None:
    messages: solara.Reactive[list[dict]] = solara.use_reactive([])
    draft = solara.use_reactive("")
    session_id: solara.Reactive[str | None] = solara.use_reactive(None)
    tier = solara.use_reactive("quick")
    pending = solara.use_reactive(False)
    last_task_id = solara.use_reactive("")

    def _send() -> None:
        text = draft.value.strip()
        if not text or pending.value:
            return
        pending.set(True)
        messages.set([*messages.value, {"role": "user", "content": text}])
        draft.set("")
        try:
            resp = post(
                "/chat",
                json={
                    "prompt": text,
                    "session_id": session_id.value,
                    "tier": tier.value,
                },
            )
            session_id.set(resp.get("session_id"))
            messages.set(
                [
                    *messages.value,
                    {"role": "assistant", "content": resp.get("content", "")},
                ]
            )
        except Exception as exc:  # noqa: BLE001
            messages.set(
                [
                    *messages.value,
                    {"role": "assistant", "content": f"**Error:** {exc}"},
                ]
            )
        finally:
            pending.set(False)

    def _run_crew() -> None:
        text = draft.value.strip()
        if not text:
            return
        pending.set(True)
        try:
            resp = post(
                "/agents/crew/run",
                json={"prompt": text, "session_id": session_id.value},
            )
            tid = resp.get("task_id", "?")
            last_task_id.set(tid)
            messages.set(
                [
                    *messages.value,
                    {"role": "user", "content": text},
                    {
                        "role": "assistant",
                        "content": (
                            f"Crew kicked off (task `{tid}`). "
                            "Watch the right-hand pane for streaming output, or open the Crew Trace page."
                        ),
                    },
                ]
            )
            draft.set("")
        except Exception as exc:  # noqa: BLE001
            messages.set(
                [
                    *messages.value,
                    {"role": "assistant", "content": f"**Crew error:** {exc}"},
                ]
            )
        finally:
            pending.set(False)

    PageHeader(
        title="Quant Assistant",
        subtitle=(
            "Ask about data, design a strategy, or dispatch the full research "
            "crew — progress streams over WebSocket into the right-hand pane."
        ),
        icon="💬",
    )

    with solara.Column(style={"padding": "14px 20px"}):
        SplitPane(
            left_width="420px",
            sticky_left=False,
            left=lambda: _chat_pane(
                messages=messages,
                draft=draft,
                tier=tier,
                pending=pending,
                on_send=_send,
                on_run_crew=_run_crew,
            ),
            right=lambda: _stream_pane(last_task_id.value),
        )


def _chat_pane(
    *,
    messages: solara.Reactive[list[dict]],
    draft: solara.Reactive[str],
    tier: solara.Reactive[str],
    pending: solara.Reactive[bool],
    on_send,
    on_run_crew,
) -> None:
    with solara.Column(gap="10px"):
        with solara.Row(gap="10px"):
            solara.Select(label="LLM tier", value=tier, values=["quick", "deep"])
        with solara.Card():
            if not messages.value:
                solara.Markdown("_Start the conversation below…_")
            for m in messages.value:
                ChatBubble(role=m["role"], content=m["content"])
        solara.InputText(
            "Message",
            value=draft,
            on_value=lambda v: draft.set(v),
        )
        with solara.Row(gap="6px"):
            solara.Button(
                "Send",
                on_click=on_send,
                disabled=pending.value,
                color="primary",
            )
            solara.Button(
                "Run Crew",
                on_click=on_run_crew,
                disabled=pending.value,
            )


def _stream_pane(task_id: str) -> None:
    with solara.Column(gap="10px"):
        if not task_id:
            with solara.Card("Task stream"):
                solara.Markdown(
                    "_Kick off a crew with **Run Crew** to see live WebSocket progress here._"
                )
            return
        TaskStreamer(task_id=task_id, title="Task stream", show_result=True)
