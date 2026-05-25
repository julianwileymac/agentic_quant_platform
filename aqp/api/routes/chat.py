"""Chat endpoints — direct LLM chat + WebSocket for crew streaming."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, func, select

from aqp.api.security import secure_router
from aqp.api.schemas import (
    ChatRequest,
    ChatResponse,
    ChatThreadCreate,
    ChatThreadSummary,
    TaskAccepted,
)
from aqp.llm.ollama_client import deep_llm, quick_llm
from aqp.llm.prompts import SYSTEM_QUANT_ASSISTANT
from aqp.persistence.db import get_session
from aqp.persistence.models import ChatMessage
from aqp.persistence.models import Session as ChatSession
from aqp.ws.broker import asubscribe, replay_frames
from aqp.ws.manager import manager

logger = logging.getLogger(__name__)
router = secure_router(prefix="/chat", tags=["chat"], default_scope="agent:view")


def _context_to_system_prompt(req: ChatRequest) -> str:
    """Render the optional :class:`ChatContext` as an extra system sentence.

    Keeping this as a plain string (rather than a tool the assistant has to
    call) means the model can use it on every turn without round-tripping a
    tool call. The webui sets these fields based on the route the user is
    currently on (``/data/browser/AAPL.SMART`` ⇒ ``vt_symbol=AAPL.SMART``).
    """
    if req.context is None:
        return ""
    bits: list[str] = []
    ctx = req.context
    if ctx.page:
        bits.append(f"page={ctx.page}")
    if ctx.vt_symbol:
        bits.append(f"vt_symbol={ctx.vt_symbol}")
    if ctx.backtest_id:
        bits.append(f"backtest_id={ctx.backtest_id}")
    if ctx.strategy_id:
        bits.append(f"strategy_id={ctx.strategy_id}")
    if ctx.paper_run_id:
        bits.append(f"paper_run_id={ctx.paper_run_id}")
    if ctx.ml_model_id:
        bits.append(f"ml_model_id={ctx.ml_model_id}")
    if ctx.extra:
        for k, v in ctx.extra.items():
            bits.append(f"{k}={v}")
    if not bits:
        return ""
    return "User is currently looking at: " + ", ".join(bits) + "."


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    llm = deep_llm if req.tier == "deep" else quick_llm
    session_id = req.session_id
    if session_id is None:
        with get_session() as s:
            sess = ChatSession(title=req.prompt[:60], created_at=datetime.utcnow())
            s.add(sess)
            s.flush()
            session_id = sess.id

    with get_session() as s:
        s.add(ChatMessage(session_id=session_id, role="user", content=req.prompt))

    history = _load_history(session_id)
    system_parts = [SYSTEM_QUANT_ASSISTANT]
    ctx_line = _context_to_system_prompt(req)
    if ctx_line:
        system_parts.append(ctx_line)
    messages = [{"role": "system", "content": "\n\n".join(system_parts)}, *history]
    result = llm(messages=messages)

    with get_session() as s:
        s.add(
            ChatMessage(
                session_id=session_id,
                role="assistant",
                content=result.content,
                meta={"model": result.model, "tokens": result.total_tokens},
            )
        )

    return ChatResponse(
        session_id=session_id,
        content=result.content,
        model=result.model,
        tokens={
            "prompt": result.prompt_tokens,
            "completion": result.completion_tokens,
            "total": result.total_tokens,
        },
    )


@router.post("/messages", response_model=TaskAccepted)
def messages_async(req: ChatRequest) -> TaskAccepted:
    """Async chat completion — returns a ``task_id`` to subscribe to.

    Used by the Vite chat surface (``aqp_client/src/routes/chat/page.tsx``)
    which opens ``/chat/stream/{task_id}`` and renders the worker's
    ``delta`` / ``done`` frames into the assistant bubble.

    The synchronous ``POST /chat`` route above is preserved verbatim
    for the legacy webui; this surface is purely additive.
    """
    # Inline import per .cursor/rules/tasks-api.mdc (no Celery imports
    # at FastAPI route module top level — circular import risk).
    from aqp.tasks.chat_tasks import chat_completion

    payload_context = req.context.model_dump() if req.context else None
    async_result = chat_completion.delay(
        prompt=req.prompt,
        session_id=req.session_id,
        tier=req.tier,
        context=payload_context,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/sessions/{session_id}/messages")
def messages(session_id: str) -> list[dict]:
    return _load_history(session_id, include_meta=True)


# ---------------------------------------------------------------------------
# Thread CRUD — alias of ``Session`` rows so the webui can list / pick / delete.
# ---------------------------------------------------------------------------


@router.get("/threads", response_model=list[ChatThreadSummary])
def list_threads(limit: int = 100) -> list[ChatThreadSummary]:
    """Return the most recent chat threads with a message count."""
    with get_session() as s:
        msg_counts = (
            select(ChatMessage.session_id, func.count(ChatMessage.id).label("n"))
            .group_by(ChatMessage.session_id)
            .subquery()
        )
        rows = s.execute(
            select(ChatSession, msg_counts.c.n)
            .outerjoin(msg_counts, msg_counts.c.session_id == ChatSession.id)
            .order_by(desc(ChatSession.created_at))
            .limit(max(1, min(limit, 1000)))
        ).all()
        return [
            ChatThreadSummary(
                id=session.id,
                title=session.title,
                created_at=session.created_at,
                closed_at=session.closed_at,
                message_count=int(count or 0),
            )
            for session, count in rows
        ]


@router.post("/threads", response_model=ChatThreadSummary)
def create_thread(req: ChatThreadCreate) -> ChatThreadSummary:
    with get_session() as s:
        sess = ChatSession(title=req.title or None, created_at=datetime.utcnow())
        s.add(sess)
        s.flush()
        return ChatThreadSummary(
            id=sess.id,
            title=sess.title,
            created_at=sess.created_at,
            closed_at=sess.closed_at,
            message_count=0,
        )


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str) -> dict[str, str]:
    with get_session() as s:
        sess = s.get(ChatSession, thread_id)
        if sess is None:
            raise HTTPException(404, f"no such thread: {thread_id}")
        s.delete(sess)
    return {"id": thread_id, "deleted": "ok"}


def _load_history(session_id: str, include_meta: bool = False) -> list[dict]:
    with get_session() as s:
        rows = s.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        ).scalars().all()
        out = []
        for r in rows:
            item = {"role": r.role, "content": r.content}
            if include_meta:
                item["meta"] = r.meta or {}
                item["created_at"] = str(r.created_at)
            out.append(item)
        return out


@router.get("/replay/{task_id}")
def replay(
    task_id: str,
    since: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Replay buffered progress frames for ``task_id``.

    Phase 3 (WS replay): the BFF / frontend calls this on every
    WebSocket reconnect to fill the gap between ``since`` (the last
    ``frame_id`` it saw) and the next live frame. The response shape
    is::

        {
            "task_id": "<task_id>",
            "since": "<input since or null>",
            "frames": [
                {"frame_id": "1716...-0", "task_id": "...",
                 "stage": "...", "message": "...",
                 "timestamp": 1716..., "...": "..."},
                ...
            ],
            "last_frame_id": "1716...-N" | null
        }

    Frames are ordered by Redis Stream id (chronological). The
    ``last_frame_id`` value is what the client persists for the next
    reconnect — it's deliberately the id of the last returned frame
    (NOT the stream's tail) so the WS resume window starts strictly
    after this replay.

    AGENTS rule 4: frames carry the canonical
    ``{task_id, stage, message, timestamp, **extras}`` shape; we
    only ADD a ``frame_id`` key for replay bookkeeping. We never
    rename or drop existing keys.

    Limits: ``limit`` is clamped to ``[1, 10_000]`` upstream; the
    default of 500 is small enough that a slow client doesn't hold
    the BFF event loop for long.
    """
    bounded_limit = max(1, min(int(limit), 10_000))
    frames = replay_frames(task_id, since=since, limit=bounded_limit)
    last_frame_id = frames[-1].get("frame_id") if frames else None
    return {
        "task_id": task_id,
        "since": since,
        "frames": frames,
        "last_frame_id": last_frame_id,
    }


@router.websocket("/stream/{task_id}")
async def stream(ws: WebSocket, task_id: str) -> None:
    """Relay pub/sub progress for a given task_id to the connected client.

    Phase 3a authentication: after ``manager.connect`` accepts the socket,
    the first client frame must be ``{"type":"auth","token":"<JWT>"}``.
    Failure modes are handled by :class:`aqp.auth.ws.WebSocketAuthenticator`
    which closes the socket with the appropriate close code (4001 for
    protocol error, 4003 for invalid token). When
    ``settings.ws_auth_required`` is False (default during cutover),
    a missing or malformed first frame falls back to the local-first
    default context.
    """
    from aqp.auth.ws import ws_authenticator

    await manager.connect(task_id, ws)
    auth_result = await ws_authenticator.authenticate(ws)
    if auth_result is None:
        await manager.disconnect(task_id, ws)
        return
    try:
        async for msg in asubscribe(task_id):
            await ws.send_json(msg)
            if msg.get("stage") in {"done", "error"}:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws stream error for task %s", task_id)
    finally:
        await manager.disconnect(task_id, ws)
