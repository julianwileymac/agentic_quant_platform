"""LoRA / QLoRA fine-tuning pipeline for open-source LLMs.

Mirrors the FinGPT v3 training recipe: load a base model + tokenizer,
attach a PEFT LoRA adapter (optionally with 4-bit quantization via
bitsandbytes), train with ``trl.SFTTrainer`` on an instruction-tuning
dataset, save the adapter + tokenizer into a model directory, and log
the run to MLflow.

All heavy optional deps live in the ``[fingpt]`` extras group (``peft``,
``trl``, ``transformers``, ``bitsandbytes``, ``accelerate``,
``datasets``) so the base install stays lean.
"""
from __future__ import annotations

from aqp.ml.finetune.config import (
    FinetuneJob,
    LoRAConfig,
    QLoRAConfig,
)
from aqp.ml.finetune.datasets import build_dataset, list_dataset_specs
from aqp.ml.finetune.trainer import run_finetune

__all__ = [
    "FinetuneJob",
    "LoRAConfig",
    "QLoRAConfig",
    "build_dataset",
    "list_dataset_specs",
    "run_finetune",
]
