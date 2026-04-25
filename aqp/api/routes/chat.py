"""Chat endpoints — direct LLM chat + WebSocket for crew streaming."""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, func, select

from aqp.api.schemas import (
    ChatRequest,
    ChatResponse,
    ChatThreadCreate,
    ChatThreadSummary,
)
from aqp.llm.ollama_client import deep_llm, quick_llm
from aqp.llm.prompts import SYSTEM_QUANT_ASSISTANT
from aqp.persistence.db import get_session
from aqp.persistence.models import ChatMessage
from aqp.persistence.models import Session as ChatSession
from aqp.ws.broker import asubscribe
from aqp.ws.manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


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


@router.websocket("/stream/{task_id}")
async def stream(ws: WebSocket, task_id: str) -> None:
    """Relay pub/sub progress for a given task_id to the connected client."""
    await manager.connect(task_id, ws)
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
