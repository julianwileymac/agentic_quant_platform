"""Content-addressed hashing for ``GraphSpec`` and friends.

The :func:`compute_content_hash` function mirrors
:meth:`aqp.agents.orchestration.spec.WorkflowSpec.snapshot_hash` exactly:
SHA256 of the canonical-JSON dump (sorted keys, no whitespace) of a
Pydantic model dumped with ``mode='json'``. This is THE reproducibility
key for the Data Lab — every ``lab_runs`` row, every WebSocket
envelope, every "Reproduce this run" button references it.

We also expose:

- :func:`snapshot_data_locator` — captures Iceberg snapshot IDs + Hudi
  commit times + QuestDB partition checksums + Redpanda subscribe
  offsets at graph-submit time so the full reproducibility triple
  ``(content_hash, data_snapshot, code_snapshot)`` is durable.
- :func:`compute_code_snapshot` — sha256 of the ``aqp_snippets`` git
  SHA (when checked out) and the sorted executor image digest map from
  ``settings.aqp_lab_executor_images``. Persisted on every
  :class:`aqp.persistence.models_lab.LabRun` and
  :class:`aqp.persistence.models_lab.LabGraph` so a "Reproduce" replay
  refuses if any executor image is no longer pinned.

Every introspection failure here is best-effort — the caller (a
mutation endpoint on the way to commit) must never block on the
locator going stale; failures fall back to a structured sentinel so
the replay path still has a target to attempt.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def compute_content_hash(model: BaseModel | Mapping[str, Any]) -> str:
    """SHA256 of canonical-JSON dump (sorted keys, no whitespace).

    Mirrors :meth:`WorkflowSpec.snapshot_hash` so any future code that
    needs cross-runtime equality checks can rely on the same algorithm.
    """
    if isinstance(model, BaseModel):
        payload = model.model_dump(mode="json", exclude={"content_hash"})
    else:
        payload = dict(model)
        payload.pop("content_hash", None)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Data snapshot
# ---------------------------------------------------------------------------


def snapshot_data_locator(spec: Any) -> dict[str, Any]:
    """Capture an Iceberg / Hudi / QuestDB / Redpanda locator for replay.

    Walks every ``data.*`` node in the graph and asks the relevant
    catalog for the current snapshot id / commit time / partition
    checksum. When the underlying source has no snapshot concept (live
    Redpanda topic, in-process synthetic), we record an empty entry
    with enough metadata for a deterministic replay.

    The returned dict shape is intentionally flat-ish so it lives
    happily inside ``lab_graphs.data_snapshot`` JSONB and can be
    GIN-indexed if needed.
    """
    nodes: list[Any] = list(getattr(spec, "nodes", []) or [])
    locator: dict[str, Any] = {}
    for node in nodes:
        node_type = getattr(node, "type", "") or ""
        node_id = getattr(node, "id", "") or ""
        if not node_type.startswith("data.") or not node_id:
            continue
        try:
            entry = _capture_one(node)
        except Exception as exc:  # noqa: BLE001 - never block submit
            logger.debug(
                "snapshot_data_locator capture failed node_id=%s err=%s",
                node_id,
                exc,
                exc_info=True,
            )
            entry = {"kind": node_type, "ok": False, "reason": "introspection_failed"}
        locator[node_id] = entry
    return locator


def _capture_one(node: Any) -> dict[str, Any]:
    """Best-effort snapshot capture for a single Data Source node."""
    params = dict(getattr(node, "params", {}) or {})
    node_type: str = getattr(node, "type", "") or ""

    if node_type == "data.iceberg_scan":
        return _capture_iceberg(params)
    if node_type == "data.hudi_scan":
        return _capture_hudi(params)
    if node_type == "data.questdb_query":
        return _capture_questdb(params)
    if node_type == "data.duckdb_sql":
        return {
            "kind": node_type,
            "sql_hash": hashlib.sha256(
                str(params.get("sql", "")).encode("utf-8")
            ).hexdigest()[:16],
        }
    if node_type == "data.redpanda_subscribe":
        return {
            "kind": node_type,
            "topic": params.get("topic"),
            "subscribed_at": None,
        }
    if node_type == "data.synthetic":
        return {
            "kind": node_type,
            "seed": params.get("seed"),
            "n": params.get("n"),
        }
    return {"kind": node_type, "params_keys": sorted(params.keys())}


def _capture_iceberg(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve the current Iceberg snapshot id for an iceberg_scan node.

    The capture is read-only and resilient: when PyIceberg is missing,
    the warehouse is empty, or the REST catalog is down, we fall back
    to the user-supplied identifier so a future re-run can still
    re-derive the table address.
    """
    entry: dict[str, Any] = {
        "kind": "data.iceberg_scan",
        "namespace": params.get("namespace"),
        "table": params.get("table"),
        "snapshot_id": params.get("snapshot_id"),
        "predicates": list(params.get("predicates") or []),
    }
    namespace = params.get("namespace")
    table_name = params.get("table")
    if not namespace or not table_name:
        return entry
    try:
        from aqp.data.iceberg_catalog import load_table

        table = load_table(f"{namespace}.{table_name}")
    except Exception as exc:  # noqa: BLE001
        logger.debug("iceberg load_table failed ns=%s table=%s: %s", namespace, table_name, exc)
        return entry
    if table is None:
        entry["ok"] = False
        entry["reason"] = "table_not_found"
        return entry
    try:
        current = table.current_snapshot()
        if current is not None:
            entry["snapshot_id"] = int(current.snapshot_id)
            ts_ms = getattr(current, "timestamp_ms", None)
            if ts_ms is not None:
                entry["snapshot_timestamp_ms"] = int(ts_ms)
            try:
                # Schema fingerprint helps the replay detect schema drift.
                schema_json = current.schema().model_dump(mode="json")  # type: ignore[attr-defined]
                entry["schema_fingerprint"] = hashlib.sha256(
                    json.dumps(schema_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()[:16]
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("iceberg snapshot resolve failed: %s", exc)
        entry["ok"] = False
        entry["reason"] = f"snapshot_resolve_failed:{type(exc).__name__}"
    return entry


def _capture_hudi(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve the latest Hudi commit_time for a hudi_scan node."""
    entry: dict[str, Any] = {
        "kind": "data.hudi_scan",
        "namespace": params.get("namespace"),
        "table": params.get("table"),
        "commit_time": params.get("commit_time"),
    }
    namespace = params.get("namespace")
    table_name = params.get("table")
    if not namespace or not table_name:
        return entry
    # Hudi exposes its timeline via the .hoodie/ folder on the warehouse
    # path; we resolve through the existing HudiWriter helpers when
    # available. Fall back to a sentinel so replay can still target the
    # table even when the Hudi runtime isn't installed.
    try:
        from aqp.config import settings
        from aqp.data.lakehouse.hudi.namespaces import hudi_namespace

        warehouse = str(getattr(settings, "hudi_warehouse_url", "") or "").rstrip("/")
        if not warehouse:
            entry["ok"] = False
            entry["reason"] = "hudi_warehouse_url_unset"
            return entry
        # The Hudi target URI scheme is ``{warehouse}/{hudi_ns}/{table}/``
        # — same as :meth:`HudiWriteSpec.target_uri`. Only local
        # filesystem reads work here; for S3/MinIO we degrade to a
        # sentinel locator because cross-cloud listing is the operator's
        # concern, not the lab's.
        ns = hudi_namespace(str(namespace))
        local_path: Path | None = None
        if warehouse.startswith("file://"):
            local_path = Path(warehouse.removeprefix("file://")) / ns / str(table_name) / ".hoodie"
        elif "://" not in warehouse:
            local_path = Path(warehouse) / ns / str(table_name) / ".hoodie"
        if local_path is None:
            entry["ok"] = True
            entry["reason"] = "remote_warehouse_no_local_timeline"
            entry["warehouse_uri"] = f"{warehouse}/{ns}/{table_name}/"
            return entry
        table_path = local_path
        if not table_path.exists():
            entry["ok"] = False
            entry["reason"] = "timeline_not_found"
            return entry
        # Newest committed `.commit` / `.deltacommit` file by mtime is
        # the active instant. This avoids importing pyspark just to read
        # the timeline.
        candidates: list[tuple[float, str]] = []
        for child in table_path.iterdir():
            if not child.is_file():
                continue
            if child.suffix in {".commit", ".deltacommit", ".replacecommit"}:
                try:
                    candidates.append((child.stat().st_mtime, child.stem))
                except OSError:
                    continue
        if candidates:
            candidates.sort(reverse=True)
            entry["commit_time"] = candidates[0][1]
            entry["commit_count"] = len(candidates)
    except Exception as exc:  # noqa: BLE001
        logger.debug("hudi timeline resolve failed: %s", exc)
        entry["ok"] = False
        entry["reason"] = f"hudi_resolve_failed:{type(exc).__name__}"
    return entry


def _capture_questdb(params: dict[str, Any]) -> dict[str, Any]:
    """Hash the QuestDB partition shape so replay can detect drift.

    A QuestDB query has no snapshot concept — but ``table_partitions(...)``
    returns (partition_name, min_ts, max_ts, row_count) which is enough
    to detect "the partition I just selected has been overwritten."
    Returns a sha256 of the sorted tuple list so the JSONB blob stays
    bounded regardless of partition count.
    """
    entry: dict[str, Any] = {
        "kind": "data.questdb_query",
        "sql_hash": hashlib.sha256(
            str(params.get("sql", "")).encode("utf-8")
        ).hexdigest()[:16],
        "table": params.get("table"),
    }
    table_name = params.get("table")
    if not table_name:
        return entry
    try:
        from aqp.data.timeseries.questdb_client import QuestDBClient

        client = QuestDBClient()
        partitions = _run_async(client.partition_info(str(table_name)))
        if not isinstance(partitions, list):
            return entry
        fingerprint_input = [
            (
                str(p.get("name", "")),
                str(p.get("minTimestamp", "")),
                str(p.get("maxTimestamp", "")),
                int(p.get("rowCount", 0) or 0),
            )
            for p in partitions
        ]
        fingerprint_input.sort()
        canonical = json.dumps(
            fingerprint_input, sort_keys=True, separators=(",", ":"), default=str
        )
        entry["partition_fingerprint"] = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
        entry["partition_count"] = len(fingerprint_input)
    except Exception as exc:  # noqa: BLE001
        logger.debug("questdb partition resolve failed: %s", exc)
        entry["ok"] = False
        entry["reason"] = f"questdb_resolve_failed:{type(exc).__name__}"
    return entry


def _run_async(coro: Any) -> Any:
    """Best-effort sync wrapper around an awaitable.

    Used by ``_capture_questdb`` so the locator helper stays a single
    sync call from the route. If we're already inside an event loop
    (FastAPI request handlers run on uvloop), spin a one-shot thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result_box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result_box["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            result_box["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=5.0)
    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("value")


# ---------------------------------------------------------------------------
# Code snapshot
# ---------------------------------------------------------------------------


_CODE_SNAPSHOT_CACHE: dict[str, str] = {}
_CODE_SNAPSHOT_LOCK = threading.Lock()


def compute_code_snapshot(snippets_root: str | os.PathLike[str] | None = None) -> str:
    """Return a sha256 hex string that pins the executor code surface.

    The hash mixes two stable inputs so a "Reproduce" replay can refuse
    when either source moves:

    1. The git SHA of the ``aqp_snippets`` working tree (when present).
    2. The sorted ``settings.aqp_lab_executor_images`` digest map (per
       plan §0).

    The result lives on every :class:`aqp.persistence.models_lab.LabRun`
    and :class:`aqp.persistence.models_lab.LabGraph` so a replay can
    detect digest drift before re-dispatching.

    The call is cached for the process lifetime keyed by the snippet
    root (cheap because the inputs don't churn within a run).
    """
    root_path = _resolve_snippets_root(snippets_root)
    cache_key = str(root_path or "<no-snippets>")
    with _CODE_SNAPSHOT_LOCK:
        cached = _CODE_SNAPSHOT_CACHE.get(cache_key)
        if cached is not None:
            return cached

    git_sha = _git_head_sha(root_path)
    image_map = _executor_image_map()
    payload = {
        "snippets_sha": git_sha or "",
        "image_digests": image_map,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with _CODE_SNAPSHOT_LOCK:
        _CODE_SNAPSHOT_CACHE[cache_key] = digest
    return digest


def reset_code_snapshot_cache() -> None:
    """Drop the in-process code-snapshot cache (used by tests + reload)."""
    with _CODE_SNAPSHOT_LOCK:
        _CODE_SNAPSHOT_CACHE.clear()


def _resolve_snippets_root(
    snippets_root: str | os.PathLike[str] | None,
) -> Path | None:
    if snippets_root is not None:
        candidate = Path(snippets_root)
        return candidate if candidate.exists() else None
    # Default lookup: ../aqp_snippets/ relative to the repo root.
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "aqp_snippets"
        if candidate.exists():
            return candidate
    return None


def _git_head_sha(root: Path | None) -> str | None:
    if root is None:
        return None
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if completed.returncode != 0:
            return None
        value = (completed.stdout or "").strip()
        return value or None
    except Exception:  # noqa: BLE001
        return None


def _executor_image_map() -> dict[str, str]:
    try:
        from aqp.config import settings

        raw = dict(getattr(settings, "aqp_lab_executor_images", {}) or {})
    except Exception:  # noqa: BLE001
        return {}
    # Coerce to a deterministic sorted-key dict for hashing.
    return {str(k): str(v) for k, v in sorted(raw.items())}


__all__ = [
    "compute_code_snapshot",
    "compute_content_hash",
    "reset_code_snapshot_cache",
    "snapshot_data_locator",
]
