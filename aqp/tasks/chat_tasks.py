"""Async LLM chat completion as a Celery task.

The Vite chat surface (``aqp_client/src/routes/chat/page.tsx``) posts a
prompt to ``POST /chat/messages`` and expects a ``TaskAccepted`` with a
``task_id``. The frontend then opens ``/chat/stream/{task_id}`` and
incrementally renders ``msg.delta`` chunks into the assistant bubble,
finalising the bubble on the ``done`` frame's ``content`` field.

This task implements the worker side of that contract: it persists the
user message, calls :func:`aqp.llm.ollama_client.quick_llm` /
:func:`deep_llm` to get the assistant reply, then chunks the reply into
small ``delta`` frames so the UI sees it land token-by-token. The final
``emit_done`` carries the full ``content`` so a late-connecting
WebSocket client still gets the complete reply on a single frame.

Synchronous ``POST /chat`` (in :mod:`aqp.api.routes.chat`) is preserved
unchanged for back-compat; ``POST /chat/messages`` is the new async
surface.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# Roughly token-sized chunk for synthetic streaming. The underlying LLM
# call is one-shot; we slice the resulting text into chunks of this many
# characters and pace them with a small sleep so the UI feels live.
_DELTA_CHUNK_CHARS = 24
_DELTA_INTERVAL_S = 0.04


def _chunked(text: str, *, size: int = _DELTA_CHUNK_CHARS):
    """Yield approximately equal-sized slices of ``text``.

    We bias each cut to fall on whitespace when possible so the user
    never sees a half-word land in the bubble.
    """
    if not text:
        return
    n = len(text)
    i = 0
    while i < n:
        end = min(i + size, n)
        # Try to land on whitespace within the next 8 chars.
        if end < n:
            window_end = min(end + 8, n)
            ws = text.rfind(" ", end - 4, window_end)
            if ws > i:
                end = ws + 1
        yield text[i:end]
        i = end


def _build_messages(
    *,
    prompt: str,
    session_id: str | None,
    context: dict[str, Any] | None,
) -> tuple[str | None, list[dict[str, str]]]:
    """Build (resolved_session_id, messages[]) for the LLM call.

    Mirrors the body of :func:`aqp.api.routes.chat.chat` so the user
    message persists, the existing context-as-system-prompt convention
    is preserved, and Postgres is the cross-task source of truth for
    chat history (AGENTS rule 5).
    """
    from aqp.api.routes.chat import _context_to_system_prompt, _load_history
    from aqp.api.schemas import ChatContext, ChatRequest
    from aqp.llm.prompts import SYSTEM_QUANT_ASSISTANT
    from aqp.persistence.db import get_session
    from aqp.persistence.models import ChatMessage
    from aqp.persistence.models import Session as ChatSession

    if session_id is None:
        with get_session() as s:
            sess = ChatSession(title=prompt[:60], created_at=datetime.utcnow())
            s.add(sess)
            s.flush()
            session_id = sess.id

    with get_session() as s:
        s.add(ChatMessage(session_id=session_id, role="user", content=prompt))

    history = _load_history(session_id)
    ctx_obj = ChatContext.model_validate(context) if context else None
    req_proxy = ChatRequest(prompt=prompt, session_id=session_id, context=ctx_obj)
    system_parts = [SYSTEM_QUANT_ASSISTANT]
    ctx_line = _context_to_system_prompt(req_proxy)
    if ctx_line:
        system_parts.append(ctx_line)
    messages = [{"role": "system", "content": "\n\n".join(system_parts)}, *history]
    return session_id, messages


@celery_app.task(bind=True, name="aqp.tasks.chat_tasks.chat_completion")
def chat_completion(
    self,
    *,
    prompt: str,
    session_id: str | None = None,
    tier: str = "quick",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Async equivalent of ``POST /chat`` with token-level progress.

    Emits ``stage="start"`` on launch, multiple ``stage="delta"`` frames
    carrying ``delta=<chunk>`` strings (consumed by
    ``aqp_client/src/lib/ws/useChatStream.ts``), then ``emit_done`` with
    the full ``content`` and rich result envelope.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", "completing chat", tier=tier)

    try:
        from aqp.llm.ollama_client import deep_llm, quick_llm
        from aqp.persistence.db import get_session
        from aqp.persistence.models import ChatMessage

        resolved_session_id, messages = _build_messages(
            prompt=prompt, session_id=session_id, context=context
        )
        emit(task_id, "llm_call", "calling LLM", session_id=resolved_session_id)

        llm_fn = deep_llm if (tier or "").lower() == "deep" else quick_llm
        result = llm_fn(messages=messages)
        full = str(getattr(result, "content", "") or "")
        model = str(getattr(result, "model", "") or "")
        tokens_in = int(getattr(result, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(result, "completion_tokens", 0) or 0)
        tokens_total = int(getattr(result, "total_tokens", 0) or 0)

        # Persist the assistant message before streaming so durable state
        # is correct even if the WS consumer disconnects.
        with get_session() as s:
            s.add(
                ChatMessage(
                    session_id=resolved_session_id,
                    role="assistant",
                    content=full,
                    meta={"model": model, "tokens": tokens_total},
                )
            )

        # Chunk the reply into delta frames. The frontend's
        # ``useChatStream`` accumulates each ``delta`` into the bubble.
        for chunk in _chunked(full):
            if not chunk:
                continue
            emit(task_id, "delta", "", delta=chunk)
            if _DELTA_INTERVAL_S > 0:
                time.sleep(_DELTA_INTERVAL_S)

        out = {
            "content": full,
            "session_id": resolved_session_id,
            "model": model,
            "tokens": {
                "prompt": tokens_in,
                "completion": tokens_out,
                "total": tokens_total,
            },
        }
        # ``content`` on the done frame lets late-connecting WS clients
        # render the full reply in a single frame; ``result`` is also
        # carried so downstream consumers that read AsyncResult.get()
        # see the same shape.
        emit_done(task_id, out, content=full)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat_completion task failed")
        emit_error(task_id, str(exc))
        raise


__all__ = ["chat_completion"]
