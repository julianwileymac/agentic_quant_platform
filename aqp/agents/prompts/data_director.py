"""Prompt templates for the AQP "Data Director" — the LLM that reviews a
discovery brief, decides how to consolidate / split / rename the
candidate dataset families, and emits a structured ingestion plan.

The system prompt is deliberately narrow: it forbids freeform prose and
asks for a single JSON object so :mod:`aqp.data.pipelines.director` can
parse the response without heuristics. Two helpers in this module build
the prompts shipped to the LLM:

- :func:`build_planner_prompt` — pre-materialisation planning request.
- :func:`build_verifier_prompt` — post-materialisation reconciliation
  request, used when the actual row count is much lower than the
  planned ``expected_min_rows`` floor.
"""
from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Planner system prompt
# ---------------------------------------------------------------------------

DATA_DIRECTOR_SYSTEM_PROMPT = """\
You are the AQP Data Director, an automated data engineer.

Input: a JSON brief listing candidate dataset families discovered under
a single source path (e.g. ``cfpb``, ``fda``, ``sec``, ``uspto``). Each
family entry contains the discovery family key, a member count, total
size in MB, sniffed sample columns, the immediate-parent subdirectory
name (when applicable), and discovery notes (duplicate-suffix
suppression, format hints, etc.).

Job: decide for each family:

1. ``include`` (boolean) — whether to materialise it into Iceberg.
2. ``target_namespace`` — pick from the ``allowed_namespaces`` list in
   the brief. Use the exact spelling.
3. ``target_table`` — final lower-snake-case Iceberg table name. Keep
   it short (<=48 chars), prefer human-readable nouns
   (``hmda_lar``, ``broker_dealers``, ``device_event``).
4. ``expected_min_rows`` — conservative integer lower bound for total
   rows after materialisation. Used by the verifier to spot
   under-ingestion. When unsure, use 1.
5. ``domain_hint`` — dotted, snake_case taxonomy entry (e.g.
   ``financial.regulatory.cfpb.hmda``,
   ``healthcare.regulatory.fda.devices``,
   ``government.patents.uspto``,
   ``financial.regulatory.sec.disclosures``).
6. ``skip_member_paths`` — list of fully-qualified member paths to
   exclude. Use this to drop residual duplicates the heuristic
   suppressor missed. Empty list when there is nothing to skip.
7. ``notes`` — single short sentence explaining your decision.

Output: a SINGLE JSON object (no surrounding prose, no Markdown
fences). Schema:

```json
{
  "datasets": [
    {
      "family": "<as-is from the brief>",
      "include": true,
      "target_namespace": "aqp_cfpb",
      "target_table": "hmda_lar",
      "expected_min_rows": 100000,
      "domain_hint": "financial.regulatory.cfpb.hmda",
      "skip_member_paths": [],
      "notes": "Combined HMDA LAR public files across years."
    }
  ],
  "skipped_assets": [
    { "family": "__assets__", "reason": "non-tabular inventory only" }
  ]
}
```

Rules:
- Never invent families that aren't in the brief.
- If a brief entry is ``__assets__`` (non-tabular inventory), set
  ``include`` to false and add it to ``skipped_assets`` instead.
- If two families share the same ``target_table`` AND
  ``target_namespace``, the runner will treat them as a merge — only
  do this when their schemas are clearly compatible.
- Be deterministic: same brief → same JSON.
"""


_PLANNER_USER_TEMPLATE = """\
Source path: {source_path}
Default namespace: {default_namespace}
Allowed namespaces: {allowed_namespaces}

Brief (one dict per discovered family):
{brief_json}
"""


def build_planner_prompt(
    *,
    source_path: str,
    default_namespace: str,
    allowed_namespaces: list[str],
    brief: list[dict[str, Any]],
) -> tuple[str, str]:
    """Return ``(system, user)`` strings for the planner LLM call."""
    user = _PLANNER_USER_TEMPLATE.format(
        source_path=source_path,
        default_namespace=default_namespace,
        allowed_namespaces=", ".join(allowed_namespaces),
        brief_json=json.dumps(brief, ensure_ascii=False, indent=2),
    )
    return DATA_DIRECTOR_SYSTEM_PROMPT, user


# ---------------------------------------------------------------------------
# Post-materialisation verifier prompt
# ---------------------------------------------------------------------------

VERIFIER_SYSTEM_PROMPT = """\
You are the AQP Data Director acting as a verifier.

The runner just materialised a planned dataset and the actual row count
came in below the planned ``expected_min_rows`` floor (or files were
skipped). Decide whether to accept the result or retry with adjusted
ingestion knobs. Output a SINGLE JSON object, no prose, schema:

```json
{
  "verdict": "accept",  // or "retry"
  "reason": "Short one-sentence rationale.",
  "retry_with": {
    "max_rows_per_dataset": null,
    "max_files_per_dataset": null,
    "force_string_columns": false
  }
}
```

When ``verdict == "accept"`` set ``retry_with`` to ``null``. Only ask
to retry when there is a plausible knob change that could plausibly
improve the row count (e.g. raising the row cap if the cap was hit).
"""


_VERIFIER_USER_TEMPLATE = """\
Planned dataset:
{planned_json}

Actual outcome:
{actual_json}

Current ingestion settings:
{settings_json}
"""


def build_verifier_prompt(
    *,
    planned: dict[str, Any],
    actual: dict[str, Any],
    ingestion_settings: dict[str, Any],
) -> tuple[str, str]:
    """Return ``(system, user)`` strings for the verifier LLM call."""
    user = _VERIFIER_USER_TEMPLATE.format(
        planned_json=json.dumps(planned, ensure_ascii=False, indent=2),
        actual_json=json.dumps(actual, ensure_ascii=False, indent=2),
        settings_json=json.dumps(ingestion_settings, ensure_ascii=False, indent=2),
    )
    return VERIFIER_SYSTEM_PROMPT, user


__all__ = [
    "DATA_DIRECTOR_SYSTEM_PROMPT",
    "VERIFIER_SYSTEM_PROMPT",
    "build_planner_prompt",
    "build_verifier_prompt",
]
