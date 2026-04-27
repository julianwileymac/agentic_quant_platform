"""LLM-driven planner + verifier for the AQP ingestion pipeline.

The Director sits between :func:`aqp.data.pipelines.discovery.discover_datasets`
and :func:`aqp.data.pipelines.materialize.materialize_dataset`. It:

1. Builds a compact JSON brief summarising the discovered dataset
   families.
2. Asks an LLM (Nemotron via Ollama by default) to produce an
   :class:`IngestionPlan` with table/namespace decisions, row-count
   floors, domain hints, and per-member skip lists.
3. Falls back to a deterministic identity plan when the LLM is
   unreachable, returns malformed JSON, or is disabled by configuration.

A second entry-point :func:`verify_after_materialise` is called by the
runner whenever an actual row count comes in lower than the planned
floor; it asks the LLM whether to accept the result or retry with
adjusted ingestion knobs.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aqp.agents.prompts.data_director import (
    build_planner_prompt,
    build_verifier_prompt,
)
from aqp.config import settings
from aqp.data.pipelines.discovery import DiscoveredDataset, DiscoveredMember

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plan dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PlannedDataset:
    """Director's decision for a single discovered family."""

    family: str
    include: bool = True
    target_namespace: str = ""
    target_table: str = ""
    expected_min_rows: int = 1
    domain_hint: str = "user.dataset"
    member_paths: list[str] = field(default_factory=list)
    skip_member_paths: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "include": bool(self.include),
            "target_namespace": self.target_namespace,
            "target_table": self.target_table,
            "expected_min_rows": int(self.expected_min_rows),
            "domain_hint": self.domain_hint,
            "member_paths": list(self.member_paths),
            "skip_member_paths": list(self.skip_member_paths),
            "notes": self.notes,
        }

    @property
    def iceberg_identifier(self) -> str:
        return f"{self.target_namespace}.{self.target_table}"


@dataclass
class IngestionPlan:
    """Full planning output for one discovery run."""

    source_path: str
    namespace: str
    datasets: list[PlannedDataset] = field(default_factory=list)
    skipped_assets: list[dict[str, Any]] = field(default_factory=list)
    director_raw: str = ""
    director_used: bool = False
    director_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "namespace": self.namespace,
            "datasets": [d.to_dict() for d in self.datasets],
            "skipped_assets": list(self.skipped_assets),
            "director_used": bool(self.director_used),
            "director_error": self.director_error,
        }


# ---------------------------------------------------------------------------
# Member helpers
# ---------------------------------------------------------------------------


def _member_id(m: DiscoveredMember) -> str:
    """Stable single-string id for a discovered member.

    Format: ``<host_path>!<archive_path>`` when the member is inside a
    zip, otherwise just ``<host_path>``. The runner uses the same format
    when filtering so the LLM-supplied ``skip_member_paths`` round-trip
    cleanly.
    """
    if m.archive_path:
        return f"{m.path}!{m.archive_path}"
    return m.path


def _member_paths(ds: DiscoveredDataset) -> list[str]:
    return [_member_id(m) for m in ds.members]


def _safe_table_name(name: str) -> str:
    name = (name or "").strip().lower()
    name = name.replace("-", "_").replace(" ", "_")
    out = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    cleaned = "".join(out).strip("_")
    return cleaned or "dataset"


def _safe_namespace(name: str, default: str) -> str:
    name = (name or "").strip().lower()
    if not name:
        return default
    name = name.replace("-", "_").replace(" ", "_")
    out = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name).strip("_")
    return out or default


# ---------------------------------------------------------------------------
# Brief construction
# ---------------------------------------------------------------------------


def _build_brief_entry(ds: DiscoveredDataset) -> dict[str, Any]:
    members = ds.members[:50]  # cap for prompt size
    subdirs = sorted({m.subdir for m in ds.members if m.subdir})
    return {
        "family": ds.family,
        "file_count": ds.file_count,
        "format": ds.member_format,
        "delimiter": ds.members[0].delimiter if ds.members else None,
        "total_mb": round(ds.total_bytes / (1024 * 1024), 2),
        "subdirs": subdirs,
        "sample_columns": list(ds.sample_columns)[:64],
        "sample_member_basenames": [
            Path(m.archive_path or m.path).name for m in members
        ],
        "notes": list(ds.notes),
    }


def _identity_plan(
    datasets: list[DiscoveredDataset],
    *,
    source_path: str,
    namespace: str,
) -> IngestionPlan:
    """Deterministic fallback plan: keep every family, one Iceberg table each."""
    plan = IngestionPlan(source_path=source_path, namespace=namespace)
    for ds in datasets:
        if ds.family == "__assets__":
            plan.skipped_assets.append(
                {
                    "family": ds.family,
                    "file_count": ds.file_count,
                    "total_bytes": ds.total_bytes,
                    "reason": "non-tabular inventory",
                }
            )
            continue
        plan.datasets.append(
            PlannedDataset(
                family=ds.family,
                include=True,
                target_namespace=namespace,
                target_table=_safe_table_name(ds.family),
                expected_min_rows=1,
                domain_hint="user.dataset",
                member_paths=_member_paths(ds),
                skip_member_paths=[],
                notes="identity-plan fallback",
            )
        )
    return plan


_REQUIRED_PLAN_KEYS = ("datasets",)
_REQUIRED_VERIFIER_KEYS = ("verdict",)


def _iter_balanced_json_blocks(text: str):
    """Yield every balanced ``{...}`` substring in ``text``, longest-first.

    Reasoning models like Nemotron prefix their output with chain-of-
    thought ("We need to produce..."), then emit the JSON answer
    afterwards. The naive "first {, last }" approach in the previous
    parser would frequently span across a paraphrased system-prompt
    example AND the real answer, breaking the parse. This generator
    walks the string with a brace-depth counter and yields every
    syntactically-balanced ``{...}`` block, sorted by length descending
    (the actual answer is usually the longest object). The caller
    picks the first one that ``json.loads`` accepts.
    """
    depth = 0
    start = -1
    blocks: list[str] = []
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    blocks.append(text[start : i + 1])
                    start = -1
    blocks.sort(key=len, reverse=True)
    yield from blocks


def _parse_director_response(raw: str, *, required_keys: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Tolerantly extract a JSON object from a possibly-noisy LLM reply.

    The parser handles three common output shapes:

    1. Pure JSON.
    2. JSON wrapped in triple-backtick ``json`` fences.
    3. Reasoning-model output where the JSON is buried in chain-of-
       thought prose. We scan every balanced ``{...}`` block,
       longest-first, and accept the first one that parses to a dict
       and (optionally) contains the required top-level keys.
    """
    if not raw or not raw.strip():
        return {}
    text = raw.strip()

    # Strip surrounding ```json fences cleanly.
    if text.startswith("```"):
        stripped = text.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
        text = stripped

    # Try the whole text first (covers the pure-JSON case).
    try:
        whole = json.loads(text)
        if isinstance(whole, dict):
            if not required_keys or any(k in whole for k in required_keys):
                return whole
    except json.JSONDecodeError:
        pass

    # Walk every balanced {...} block, longest-first.
    for block in _iter_balanced_json_blocks(text):
        try:
            obj = json.loads(block)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if required_keys and not any(k in obj for k in required_keys):
            continue
        return obj

    return {}


def _coerce_plan_dict(
    payload: dict[str, Any],
    discovered: list[DiscoveredDataset],
    *,
    source_path: str,
    namespace: str,
    raw_response: str,
) -> IngestionPlan:
    """Map the LLM JSON payload onto an :class:`IngestionPlan`.

    Anything missing in the payload falls back to the identity plan's
    defaults so the runner always has enough data to materialise.
    """
    plan = IngestionPlan(
        source_path=source_path,
        namespace=namespace,
        director_raw=raw_response[:32_000],
        director_used=True,
    )
    by_family = {ds.family: ds for ds in discovered}

    director_entries = payload.get("datasets") or []
    seen_families: set[str] = set()
    for entry in director_entries:
        if not isinstance(entry, dict):
            continue
        family = str(entry.get("family") or "").strip()
        if not family or family not in by_family:
            continue
        seen_families.add(family)
        ds = by_family[family]
        include = bool(entry.get("include", True))
        if not include:
            plan.skipped_assets.append(
                {
                    "family": family,
                    "reason": str(entry.get("notes") or "director excluded"),
                }
            )
            continue
        target_ns = _safe_namespace(
            str(entry.get("target_namespace") or ""), namespace
        )
        target_table = _safe_table_name(
            str(entry.get("target_table") or family)
        )
        try:
            expected = int(entry.get("expected_min_rows") or 1)
        except (TypeError, ValueError):
            expected = 1
        skip_raw = entry.get("skip_member_paths") or []
        if not isinstance(skip_raw, list):
            skip_raw = []
        skip_paths = [str(p) for p in skip_raw if str(p).strip()]
        plan.datasets.append(
            PlannedDataset(
                family=family,
                include=True,
                target_namespace=target_ns,
                target_table=target_table,
                expected_min_rows=max(1, expected),
                domain_hint=str(entry.get("domain_hint") or "user.dataset"),
                member_paths=[
                    mid for mid in _member_paths(ds) if mid not in skip_paths
                ],
                skip_member_paths=skip_paths,
                notes=str(entry.get("notes") or ""),
            )
        )

    # Anything the Director didn't mention falls back to the identity row.
    for family, ds in by_family.items():
        if family in seen_families or family == "__assets__":
            continue
        plan.datasets.append(
            PlannedDataset(
                family=family,
                include=True,
                target_namespace=namespace,
                target_table=_safe_table_name(family),
                expected_min_rows=1,
                domain_hint="user.dataset",
                member_paths=_member_paths(ds),
                skip_member_paths=[],
                notes="director-omitted; identity fallback",
            )
        )

    # Always carry the __assets__ inventory through to skipped_assets.
    skipped_payload = payload.get("skipped_assets") or []
    if isinstance(skipped_payload, list):
        for entry in skipped_payload:
            if isinstance(entry, dict):
                plan.skipped_assets.append(entry)

    if "__assets__" in by_family:
        ds = by_family["__assets__"]
        plan.skipped_assets.append(
            {
                "family": "__assets__",
                "file_count": ds.file_count,
                "total_bytes": ds.total_bytes,
                "reason": "non-tabular inventory",
                "notes": list(ds.notes),
            }
        )

    return plan


# ---------------------------------------------------------------------------
# LLM round-trip
# ---------------------------------------------------------------------------


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Invoke the Director LLM via the AQP router. Returns raw text."""
    from aqp.llm.providers.router import router_complete

    provider = (
        getattr(settings, "llm_director_provider", "")
        or settings.llm_provider_quick
        or settings.llm_provider
        or "ollama"
    )
    model = (
        getattr(settings, "llm_director_model", "")
        or settings.llm_quick_model
        or settings.llm_model
        or ""
    )
    temperature = float(getattr(settings, "llm_director_temperature", 0.1) or 0.1)
    max_tokens = int(getattr(settings, "llm_director_max_tokens", 4096) or 4096)

    result = router_complete(
        provider=provider,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = (
        getattr(result, "content", None)
        or (result if isinstance(result, str) else "")
        or ""
    )
    if not text and isinstance(result, dict):
        text = result.get("content") or result.get("text") or ""
    return str(text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def plan_ingestion(
    datasets: list[DiscoveredDataset],
    *,
    source_path: str,
    namespace: str,
    allowed_namespaces: list[str] | None = None,
) -> IngestionPlan:
    """Build an :class:`IngestionPlan` for ``datasets`` via the LLM.

    Falls back to a deterministic identity plan when:

    - ``llm_director_enabled`` is false in settings.
    - The LLM call raises or returns malformed JSON.
    """
    enabled = bool(getattr(settings, "llm_director_enabled", True))
    if not datasets:
        return IngestionPlan(source_path=source_path, namespace=namespace)

    if not enabled:
        plan = _identity_plan(datasets, source_path=source_path, namespace=namespace)
        plan.director_used = False
        return plan

    brief = [
        _build_brief_entry(ds) for ds in datasets if ds.family != "__assets__"
    ]
    if not brief:
        # Only the __assets__ synthetic group exists; no work to plan.
        plan = _identity_plan(datasets, source_path=source_path, namespace=namespace)
        plan.director_used = False
        return plan

    allowed = list(allowed_namespaces or [namespace])
    system_prompt, user_prompt = build_planner_prompt(
        source_path=source_path,
        default_namespace=namespace,
        allowed_namespaces=allowed,
        brief=brief,
    )

    raw_response = ""
    try:
        raw_response = _call_llm(system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("director LLM call failed: %s — using identity plan", exc)
        plan = _identity_plan(datasets, source_path=source_path, namespace=namespace)
        plan.director_used = False
        plan.director_error = f"llm_call_failed: {exc}"
        return plan

    payload = _parse_director_response(raw_response, required_keys=_REQUIRED_PLAN_KEYS)
    if not payload:
        logger.info(
            "director response parse failed; falling back to identity plan "
            "(raw[:200]=%s)",
            (raw_response or "")[:200],
        )
        plan = _identity_plan(datasets, source_path=source_path, namespace=namespace)
        plan.director_used = False
        plan.director_error = "director_response_unparseable"
        plan.director_raw = (raw_response or "")[:32_000]
        return plan

    return _coerce_plan_dict(
        payload,
        datasets,
        source_path=source_path,
        namespace=namespace,
        raw_response=raw_response,
    )


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


@dataclass
class VerifierVerdict:
    """Structured outcome of the post-materialisation verifier call."""

    verdict: str = "accept"  # "accept" | "retry"
    reason: str = ""
    retry_with: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "retry_with": dict(self.retry_with),
            "error": self.error,
        }


def verify_after_materialise(
    *,
    planned: PlannedDataset,
    actual: dict[str, Any],
    ingestion_settings: dict[str, Any],
) -> VerifierVerdict:
    """Ask the Director whether to accept or retry an under-row materialisation."""
    enabled = bool(getattr(settings, "llm_director_enabled", True))
    if not enabled:
        return VerifierVerdict(
            verdict="accept",
            reason="director disabled — auto-accepting",
        )

    system_prompt, user_prompt = build_verifier_prompt(
        planned=planned.to_dict(),
        actual=actual,
        ingestion_settings=ingestion_settings,
    )
    try:
        raw = _call_llm(system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("verifier LLM call failed: %s", exc)
        return VerifierVerdict(
            verdict="accept",
            reason="verifier LLM unavailable; defaulting to accept",
            error=f"llm_call_failed: {exc}",
        )

    payload = _parse_director_response(raw, required_keys=_REQUIRED_VERIFIER_KEYS)
    if not payload:
        return VerifierVerdict(
            verdict="accept",
            reason="verifier response unparseable; defaulting to accept",
            raw=raw[:8000],
            error="verifier_response_unparseable",
        )

    verdict_str = str(payload.get("verdict") or "accept").lower().strip()
    if verdict_str not in ("accept", "retry"):
        verdict_str = "accept"
    retry_payload = payload.get("retry_with") or {}
    if not isinstance(retry_payload, dict):
        retry_payload = {}
    return VerifierVerdict(
        verdict=verdict_str,
        reason=str(payload.get("reason") or ""),
        retry_with={k: v for k, v in retry_payload.items() if v is not None},
        raw=raw[:8000],
    )


__all__ = [
    "IngestionPlan",
    "PlannedDataset",
    "VerifierVerdict",
    "plan_ingestion",
    "verify_after_materialise",
]
