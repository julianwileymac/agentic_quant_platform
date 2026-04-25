"""Bridge MLflow runs / dataset hashes to the ``agentic_assistants`` lineage API.

The sister project at ``C:/Users/.../agentic_assistants`` maintains a shared
lineage graph (dataset → run → model → report). AQP publishes events to
the same API so both codebases show a unified view in the Lineage UI.

When the ``agentic_assistants_api`` setting is empty the bridge becomes a
no-op; callers can always safely invoke the emit functions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aqp.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LineageEvent:
    """One node-or-edge emitted to the ``agentic_assistants`` lineage service."""

    kind: str  # dataset | run | model | report | strategy | serve_deployment
    id: str
    attrs: dict[str, Any]
    parents: list[str]


def _post(path: str, payload: dict[str, Any], timeout: float = 5.0) -> bool:
    if not settings.agentic_assistants_api:
        logger.debug("lineage-bridge disabled (agentic_assistants_api empty)")
        return False
    try:
        import httpx

        url = settings.agentic_assistants_api.rstrip("/") + path
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
        return True
    except Exception:
        logger.exception("lineage_bridge: POST %s failed", path)
        return False


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def emit_event(event: LineageEvent) -> bool:
    return _post(
        "/api/lineage/events",
        {"kind": event.kind, "id": event.id, "attrs": event.attrs, "parents": event.parents},
    )


def emit_dataset(dataset_hash: str, **attrs: Any) -> bool:
    """Record a dataset node (typically called once per feature-engineering run)."""
    return emit_event(
        LineageEvent(kind="dataset", id=f"ds:{dataset_hash}", attrs=attrs, parents=[])
    )


def emit_run(
    run_id: str,
    kind: str = "backtest",
    dataset_hash: str | None = None,
    **attrs: Any,
) -> bool:
    parents = [f"ds:{dataset_hash}"] if dataset_hash else []
    return emit_event(
        LineageEvent(
            kind="run",
            id=f"run:{run_id}",
            attrs={"subkind": kind, **attrs},
            parents=parents,
        )
    )


def emit_model(
    name: str,
    version: str | int,
    run_id: str | None = None,
    **attrs: Any,
) -> bool:
    parents = [f"run:{run_id}"] if run_id else []
    return emit_event(
        LineageEvent(
            kind="model",
            id=f"model:{name}/{version}",
            attrs=attrs,
            parents=parents,
        )
    )


def emit_serve_deployment(
    endpoint_url: str,
    backend: str,
    model_uri: str,
    **attrs: Any,
) -> bool:
    parents = [f"model:{model_uri}"]
    return emit_event(
        LineageEvent(
            kind="serve_deployment",
            id=f"serve:{endpoint_url}",
            attrs={"backend": backend, "model_uri": model_uri, **attrs},
            parents=parents,
        )
    )


def emit_strategy_version(strategy_id: str, version: int, **attrs: Any) -> bool:
    return emit_event(
        LineageEvent(
            kind="strategy",
            id=f"strategy:{strategy_id}/v{version}",
            attrs=attrs,
            parents=[],
        )
    )


__all__ = [
    "LineageEvent",
    "emit_dataset",
    "emit_event",
    "emit_model",
    "emit_run",
    "emit_serve_deployment",
    "emit_strategy_version",
]
