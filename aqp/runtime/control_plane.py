"""Runtime control-plane state for UI-managed settings.

This module stores lightweight mutable runtime preferences in a JSON file
under ``data/runtime`` so the web UI can manage provider defaults and
backtest data-source definitions without editing ``.env``.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aqp.config import settings

_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _state_path() -> Path:
    path = settings.data_dir / "runtime" / "control_plane.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_state() -> dict[str, Any]:
    return {
        "provider": {
            "provider": "",
            "deep_model": "",
            "quick_model": "",
            "ollama_host": "",
            "vllm_base_url": "",
            "updated_at": _now_iso(),
        },
        "data_sources": [],
    }


def _read_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return _default_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()
    if not isinstance(payload, dict):
        return _default_state()
    state = _default_state()
    state.update(payload)
    if not isinstance(state.get("provider"), dict):
        state["provider"] = _default_state()["provider"]
    if not isinstance(state.get("data_sources"), list):
        state["data_sources"] = []
    return state


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def get_provider_control() -> dict[str, Any]:
    with _LOCK:
        state = _read_state()
    override = state.get("provider") or {}
    provider = str(override.get("provider") or settings.llm_provider or "ollama").strip().lower()
    deep_model = str(override.get("deep_model") or settings.llm_deep_model or "").strip()
    quick_model = str(override.get("quick_model") or settings.llm_quick_model or "").strip()
    ollama_host = str(override.get("ollama_host") or settings.ollama_host or "").strip()
    vllm_base_url = str(override.get("vllm_base_url") or settings.vllm_base_url or "").strip()
    return {
        "provider": provider,
        "deep_model": deep_model,
        "quick_model": quick_model,
        "ollama_host": ollama_host,
        "vllm_base_url": vllm_base_url,
        "updated_at": str(override.get("updated_at") or ""),
    }


def update_provider_control(
    *,
    provider: str | None = None,
    deep_model: str | None = None,
    quick_model: str | None = None,
    ollama_host: str | None = None,
    vllm_base_url: str | None = None,
) -> dict[str, Any]:
    with _LOCK:
        state = _read_state()
        blob = dict(state.get("provider") or {})
        if provider is not None:
            blob["provider"] = str(provider).strip().lower()
        if deep_model is not None:
            blob["deep_model"] = str(deep_model).strip()
        if quick_model is not None:
            blob["quick_model"] = str(quick_model).strip()
        if ollama_host is not None:
            blob["ollama_host"] = str(ollama_host).strip()
        if vllm_base_url is not None:
            blob["vllm_base_url"] = str(vllm_base_url).strip()
        blob["updated_at"] = _now_iso()
        state["provider"] = blob
        _write_state(state)
    return get_provider_control()


def _seed_data_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seeded = [dict(i) for i in items if isinstance(i, dict)]

    if not any(i.get("id") == "default-bars" for i in seeded):
        seeded.append(
            {
                "id": "default-bars",
                "name": "Default Parquet Bars",
                "kind": "bars_default",
                "config": {},
                "enabled": True,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        )

    for path in settings.local_data_roots_list:
        normalized = str(path).lower().replace(":", "").replace("/", "-").replace("\\", "-")
        pid = f"local-parquet-{normalized}"
        if any(i.get("id") == pid for i in seeded):
            continue
        seeded.append(
            {
                "id": pid,
                "name": f"Local Parquet Root ({path})",
                "kind": "parquet_root",
                "config": {"parquet_root": str(path)},
                "enabled": True,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        )
    return seeded


def list_backtest_data_sources() -> list[dict[str, Any]]:
    with _LOCK:
        state = _read_state()
        items = _seed_data_sources(list(state.get("data_sources") or []))
        state["data_sources"] = items
        _write_state(state)
        return items


def upsert_backtest_data_source(payload: dict[str, Any]) -> dict[str, Any]:
    now = _now_iso()
    with _LOCK:
        state = _read_state()
        items = _seed_data_sources(list(state.get("data_sources") or []))
        source_id = str(payload.get("id") or f"src-{uuid.uuid4().hex[:12]}").strip()
        candidate = {
            "id": source_id,
            "name": str(payload.get("name") or source_id),
            "kind": str(payload.get("kind") or "parquet_root"),
            "config": dict(payload.get("config") or {}),
            "enabled": bool(payload.get("enabled", True)),
            "updated_at": now,
        }
        existing = next((i for i in items if str(i.get("id")) == source_id), None)
        if existing is None:
            candidate["created_at"] = now
            items.append(candidate)
        else:
            existing.update(candidate)
        state["data_sources"] = items
        _write_state(state)
    return next(i for i in list_backtest_data_sources() if str(i.get("id")) == source_id)


def delete_backtest_data_source(source_id: str) -> bool:
    sid = str(source_id or "").strip()
    if not sid or sid == "default-bars":
        return False
    with _LOCK:
        state = _read_state()
        items = _seed_data_sources(list(state.get("data_sources") or []))
        next_items = [i for i in items if str(i.get("id")) != sid]
        changed = len(next_items) != len(items)
        if changed:
            state["data_sources"] = next_items
            _write_state(state)
        return changed

