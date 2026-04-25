"""FinGPT instruction-tuning dataset registry.

A lightweight catalogue that lets the fine-tuning pipeline resolve a
friendly name (``"fingpt-sentiment"``) to a HuggingFace dataset id +
metadata. We don't load the datasets here; loading happens on demand
inside :mod:`aqp.ml.finetune.datasets`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SentimentDatasetSpec:
    """Descriptor for a FinGPT-compatible instruction dataset."""

    slug: str
    hf_id: str
    task: str
    description: str
    n_train: int | None = None
    n_test: int | None = None
    languages: tuple[str, ...] = ("en",)


FINGPT_DATASETS: dict[str, SentimentDatasetSpec] = {
    "fingpt-sentiment": SentimentDatasetSpec(
        slug="fingpt-sentiment",
        hf_id="FinGPT/fingpt-sentiment-train",
        task="sentiment",
        description="Sentiment-analysis instructions curated for FinGPT",
        n_train=76800,
    ),
    "fingpt-headline": SentimentDatasetSpec(
        slug="fingpt-headline",
        hf_id="FinGPT/fingpt-headline",
        task="headline",
        description="Financial-headline classification instructions",
        n_train=82200,
        n_test=20500,
    ),
    "fingpt-finred": SentimentDatasetSpec(
        slug="fingpt-finred",
        hf_id="FinGPT/fingpt-finred",
        task="relation",
        description="Financial relation extraction instructions",
        n_train=27600,
        n_test=5110,
    ),
    "fingpt-ner": SentimentDatasetSpec(
        slug="fingpt-ner",
        hf_id="FinGPT/fingpt-ner",
        task="ner",
        description="Financial named-entity recognition instructions",
        n_train=511,
        n_test=98,
    ),
    "fingpt-fiqa-qa": SentimentDatasetSpec(
        slug="fingpt-fiqa-qa",
        hf_id="FinGPT/fingpt-fiqa_qa",
        task="qa",
        description="Financial Q&A instructions (FiQA)",
        n_train=17100,
    ),
    "fingpt-fineval": SentimentDatasetSpec(
        slug="fingpt-fineval",
        hf_id="FinGPT/fingpt-fineval",
        task="choice",
        description="Chinese multiple-choice financial exam instructions",
        languages=("zh",),
        n_train=1060,
        n_test=265,
    ),
    "fingpt-forecaster-dow30": SentimentDatasetSpec(
        slug="fingpt-forecaster-dow30",
        hf_id="FinGPT/fingpt-forecaster-dow30-202305-202405",
        task="forecaster",
        description="Dow 30 forecaster instructions with news + basic financials",
    ),
}


def register_datasets() -> dict[str, SentimentDatasetSpec]:
    """Return the catalogue (identity; preserved for wizard-side imports)."""
    return FINGPT_DATASETS
