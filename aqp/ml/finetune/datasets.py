"""Dataset builders for the fine-tuning pipeline.

Reads the FinGPT-compatible datasets registered in
:mod:`aqp.ml.applications.sentiment.datasets` or an arbitrary
HuggingFace dataset id, and normalizes them into a ``text`` +
``prompt`` + ``response`` format that ``trl.SFTTrainer`` likes.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.ml.applications.sentiment.datasets import FINGPT_DATASETS, SentimentDatasetSpec

logger = logging.getLogger(__name__)


def list_dataset_specs() -> dict[str, SentimentDatasetSpec]:
    """Expose the known dataset specs — used by the UI wizard."""
    return dict(FINGPT_DATASETS)


def build_dataset(
    spec_or_id: str,
    *,
    max_examples: int | None = None,
    split: str = "train",
) -> Any:
    """Return a HuggingFace ``Dataset`` with ``text`` / ``prompt`` / ``output``.

    Accepts either a FinGPT slug (``"fingpt-sentiment"``) or a raw HF
    dataset id. Tries a handful of canonical column names before
    falling back to the first string columns.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "`datasets` is required. Install the `[fingpt]` extras group."
        ) from exc

    hf_id = FINGPT_DATASETS[spec_or_id].hf_id if spec_or_id in FINGPT_DATASETS else spec_or_id
    ds = load_dataset(hf_id, split=split)

    if max_examples:
        ds = ds.select(range(min(len(ds), int(max_examples))))

    columns = list(ds.column_names)
    prompt_col = _first_present(columns, ["instruction", "prompt", "input", "text"])
    response_col = _first_present(columns, ["output", "response", "answer", "label"])

    def _fmt(example: dict[str, Any]) -> dict[str, Any]:
        prompt = str(example.get(prompt_col, "")) if prompt_col else ""
        response = str(example.get(response_col, "")) if response_col else ""
        return {
            "prompt": prompt,
            "response": response,
            "text": (
                f"### Instruction:\n{prompt}\n\n### Response:\n{response}"
                if prompt or response
                else "\n".join(f"{k}: {v}" for k, v in example.items() if isinstance(v, str))
            ),
        }

    remove = [c for c in columns if c not in {"prompt", "response", "text"}]
    return ds.map(_fmt, remove_columns=remove)


def _first_present(cols: list[str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None
