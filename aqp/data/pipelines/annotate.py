"""LLM-driven annotation of an Iceberg table.

Given a table identifier we:

1. Pull a small head sample (default 50 rows) from the Iceberg table.
2. Build a structured prompt covering filename hints, column dtypes,
   and the sample rows.
3. Ask the configured quick-tier LLM for a JSON payload describing the
   table (description, tags, domain, pii_flags, column_docs).
4. Parse and persist the result via :func:`register_iceberg_dataset`
   and push the freeform description into ChromaDB so the existing
   semantic search continues to surface new datasets.

Failures are best-effort — the runner logs and continues so a flaky LLM
backend never blocks materialization.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from aqp.config import settings
from aqp.data import iceberg_catalog
from aqp.data.catalog import register_iceberg_dataset

logger = logging.getLogger(__name__)


_PROMPT = """\
You are a data catalog annotator. The user has just materialized a tabular
dataset into Apache Iceberg. Your job is to produce a *concise* JSON
description that downstream agents can use to discover, document, and
search this dataset.

Dataset identifier: {identifier}
Source filename hints: {hints}
Row count: {row_count}
Truncated during ingest: {truncated}

Columns ({n_columns}):
{columns}

Sample rows (up to {sample_rows}; values may be JSON-stringified):
{sample}

Respond with ONLY a single JSON object, no surrounding prose, in this shape:
{{
  "description": "1-3 sentence plain-English description of what this dataset is and what's in it",
  "tags": ["lowercase-kebab", "tags", "max-8"],
  "domain": "snake_case high-level domain bucket (e.g. financial.regulatory, healthcare.devices, government.patents)",
  "pii_flags": ["column_a", "column_b"],
  "column_docs": [
    {{ "name": "col1", "description": "short, factual description", "pii": false }},
    ...
  ]
}}
Use null fields rather than fabricating values you can't infer.
"""


@dataclass
class AnnotationResult:
    identifier: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    domain: str = ""
    pii_flags: list[str] = field(default_factory=list)
    column_docs: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "tags": list(self.tags),
            "domain": self.domain,
            "pii_flags": list(self.pii_flags),
            "column_docs": list(self.column_docs),
            "raw_response": self.raw_response[:8000],
            "error": self.error,
        }


def _sample_to_text(arrow_sample: Any, max_rows: int) -> str:
    if arrow_sample is None or arrow_sample.num_rows == 0:
        return "(no sample available)"
    try:
        df = arrow_sample.slice(0, max_rows).to_pandas()
    except Exception:  # noqa: BLE001
        return "(failed to materialize sample)"
    out_rows: list[str] = []
    for _, row in df.iterrows():
        snippet = {}
        for col, val in row.items():
            sval = "" if pd.isna(val) else str(val)
            if len(sval) > 240:
                sval = sval[:240] + "…"
            snippet[col] = sval
        out_rows.append(json.dumps(snippet, ensure_ascii=False))
    return "\n".join(out_rows)


def _columns_summary(metadata: dict[str, Any]) -> str:
    fields = metadata.get("fields") or []
    if not fields:
        return "(unknown)"
    lines = [f"- {f['name']} ({f['type']})" for f in fields[:200]]
    if len(fields) > 200:
        lines.append(f"… and {len(fields) - 200} more columns")
    return "\n".join(lines)


def _parse_response(raw: str) -> dict[str, Any]:
    """Extract a JSON dict from a possibly-noisy LLM response."""
    text = raw.strip()
    if not text:
        return {}
    if text.startswith("```"):
        # Strip first fence + optional language hint.
        text = text.split("```", 2)[-2 if text.count("```") >= 2 else -1]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        # Find first { ... last } pair.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:  # noqa: BLE001
                return {}
    return {}


def annotate_table(
    iceberg_identifier: str,
    *,
    source_uri: str | None = None,
    truncated: bool = False,
    row_count: int | None = None,
    sample_rows: int = 25,
    persist: bool = True,
    extra_meta: dict[str, Any] | None = None,
) -> AnnotationResult:
    """Annotate ``iceberg_identifier`` and (optionally) persist the result."""
    result = AnnotationResult(identifier=iceberg_identifier)
    metadata = iceberg_catalog.table_metadata(iceberg_identifier)
    arrow_sample = iceberg_catalog.read_arrow(iceberg_identifier, limit=max(5, sample_rows))

    if not metadata.get("fields"):
        result.error = "no metadata available"
        return result

    columns_block = _columns_summary(metadata)
    sample_block = _sample_to_text(arrow_sample, sample_rows)
    hints = source_uri or "(unknown)"

    prompt = _PROMPT.format(
        identifier=iceberg_identifier,
        hints=hints,
        row_count=row_count if row_count is not None else "(unknown)",
        truncated=str(bool(truncated)).lower(),
        columns=columns_block,
        n_columns=len(metadata.get("fields") or []),
        sample_rows=sample_rows,
        sample=sample_block,
    )

    response_text = ""
    try:
        from aqp.llm.providers.router import router_complete

        provider = (settings.llm_provider_quick or settings.llm_provider or "ollama").strip().lower()
        model = (settings.llm_quick_model or settings.llm_model or "").strip()
        completion = router_complete(
            provider=provider,
            model=model,
            prompt=prompt,
            temperature=float(settings.llm_temperature_quick or 0.2),
            max_tokens=2048,
        )
        response_text = (
            getattr(completion, "text", None)
            or getattr(completion, "content", None)
            or (completion if isinstance(completion, str) else "")
            or ""
        )
        if not response_text and isinstance(completion, dict):
            response_text = (
                completion.get("text")
                or completion.get("content")
                or completion.get("output_text")
                or ""
            )
    except Exception as exc:  # noqa: BLE001
        logger.info("annotation LLM call failed for %s: %s", iceberg_identifier, exc)
        result.error = f"llm_call_failed: {exc}"
        response_text = ""

    result.raw_response = str(response_text or "")
    parsed = _parse_response(result.raw_response) if response_text else {}
    if parsed:
        result.description = str(parsed.get("description") or "").strip()
        result.tags = [str(t).strip().lower() for t in (parsed.get("tags") or []) if str(t).strip()][:8]
        result.domain = str(parsed.get("domain") or "").strip()
        result.pii_flags = [str(p).strip() for p in (parsed.get("pii_flags") or []) if str(p).strip()]
        col_docs = parsed.get("column_docs") or []
        cleaned: list[dict[str, Any]] = []
        for entry in col_docs:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            cleaned.append(
                {
                    "name": name,
                    "description": str(entry.get("description") or "").strip(),
                    "pii": bool(entry.get("pii")),
                }
            )
        result.column_docs = cleaned

    if persist:
        try:
            sample_df = (
                arrow_sample.slice(0, sample_rows).to_pandas()
                if arrow_sample is not None
                else pd.DataFrame()
            )
            register_iceberg_dataset(
                iceberg_identifier=iceberg_identifier,
                provider="iceberg",
                domain=result.domain or "user.dataset",
                sample_df=sample_df,
                source_uri=source_uri,
                storage_uri=metadata.get("location") or None,
                load_mode="managed",
                llm_annotations=result.to_dict(),
                column_docs=result.column_docs,
                tags=result.tags,
                meta={
                    "iceberg_identifier": iceberg_identifier,
                    "annotation_error": result.error,
                    **(extra_meta or {}),
                },
                row_count=row_count,
                truncated=truncated,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("annotation persistence failed: %s", exc, exc_info=True)
            result.error = f"persist_failed: {exc}"
        # Best-effort push into ChromaStore so the existing dataset
        # search surfaces new tables immediately.
        try:
            from aqp.data.chroma_store import ChromaStore

            store = ChromaStore()
            description = (
                result.description
                or f"Iceberg table {iceberg_identifier} with {len(metadata.get('fields') or [])} columns."
            )
            store.datasets.upsert(
                ids=[iceberg_identifier],
                documents=[description],
                metadatas=[
                    {
                        "iceberg_identifier": iceberg_identifier,
                        "domain": result.domain or "",
                        "tags": ",".join(result.tags),
                        "row_count": int(row_count or 0),
                        "truncated": bool(truncated),
                        "source_uri": source_uri or "",
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("ChromaStore upsert failed for %s: %s", iceberg_identifier, exc)

    return result
