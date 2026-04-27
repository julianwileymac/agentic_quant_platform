"""Celery tasks for the LLM model lifecycle.

These tasks back the ``/agentic/models/*`` and ``/agentic/vllm/*`` REST
endpoints. They stream progress over the same ``/chat/stream/{task_id}``
WebSocket the rest of the platform uses, so the UI can render pull
progress / compose output without inventing a new transport.
"""
from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="aqp.tasks.llm_tasks.pull_ollama_model")
def pull_ollama_model(self, name: str, host: str | None = None) -> dict[str, Any]:
    """Stream ``ollama pull <name>`` progress and emit Redis pubsub events."""
    from aqp.llm.ollama_client import pull_model

    task_id = self.request.id
    emit(task_id, "started", f"Pulling Ollama model {name}", model=name)
    last_total = 0
    last_completed = 0
    digests: set[str] = set()
    try:
        for event in pull_model(name, host=host):
            status = str(event.get("status") or "")
            digest = str(event.get("digest") or "")
            total = int(event.get("total") or 0)
            completed = int(event.get("completed") or 0)
            if total > last_total:
                last_total = total
            if completed > last_completed:
                last_completed = completed
            if digest:
                digests.add(digest)
            pct = (completed / total) if total else 0.0
            emit(
                task_id,
                "progress",
                status or "pulling",
                model=name,
                digest=digest or None,
                total=total or None,
                completed=completed or None,
                percent=round(pct * 100.0, 2) if total else None,
            )
        result = {
            "model": name,
            "total_bytes": last_total,
            "downloaded_bytes": last_completed,
            "n_layers": len(digests),
        }
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"Ollama pull failed: {exc}")
        raise


@shared_task(bind=True, name="aqp.tasks.llm_tasks.serve_vllm_profile")
def serve_vllm_profile(self, profile_name: str) -> dict[str, Any]:
    """Bring up the docker-compose service for the given vLLM profile."""
    from aqp.llm import vllm_runner

    task_id = self.request.id
    emit(task_id, "started", f"Starting vLLM profile {profile_name}", profile=profile_name)
    try:
        profile = vllm_runner.get_profile(profile_name)
        if profile is None:
            raise ValueError(f"unknown vLLM profile: {profile_name}")
        emit(task_id, "compose-up", "docker compose up -d", profile=profile_name)
        result = vllm_runner.compose_up(profile)
        emit(
            task_id,
            "compose-result",
            "compose up returned",
            ok=result.get("ok"),
            code=result.get("code"),
            stdout=(result.get("stdout") or "")[-2000:],
            stderr=(result.get("stderr") or "")[-2000:],
        )
        if not result.get("ok"):
            raise RuntimeError(result.get("stderr") or result.get("stdout") or "compose up failed")
        # Best-effort persist as the runtime override.
        try:
            from aqp.runtime.control_plane import update_provider_control

            update_provider_control(provider="vllm", vllm_base_url=profile.base_url)
        except Exception:  # noqa: BLE001
            logger.debug("could not persist vllm runtime override", exc_info=True)
        summary = vllm_runner.summarize_profile(profile)
        emit_done(task_id, summary)
        return summary
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"vLLM start failed: {exc}")
        raise


@shared_task(bind=True, name="aqp.tasks.llm_tasks.stop_vllm_profile")
def stop_vllm_profile(self, profile_name: str) -> dict[str, Any]:
    """Stop the compose service backing the given vLLM profile."""
    from aqp.llm import vllm_runner

    task_id = self.request.id
    emit(task_id, "started", f"Stopping vLLM profile {profile_name}", profile=profile_name)
    try:
        profile = vllm_runner.get_profile(profile_name)
        if profile is None:
            raise ValueError(f"unknown vLLM profile: {profile_name}")
        result = vllm_runner.compose_down(profile)
        emit(
            task_id,
            "compose-result",
            "compose stop returned",
            ok=result.get("ok"),
            code=result.get("code"),
            stdout=(result.get("stdout") or "")[-2000:],
            stderr=(result.get("stderr") or "")[-2000:],
        )
        if not result.get("ok"):
            raise RuntimeError(result.get("stderr") or "compose stop failed")
        summary = vllm_runner.summarize_profile(profile)
        emit_done(task_id, summary)
        return summary
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"vLLM stop failed: {exc}")
        raise
