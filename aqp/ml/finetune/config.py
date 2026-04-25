"""Pydantic configs for LoRA / QLoRA fine-tuning runs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class LoRAConfig(BaseModel):
    """LoRA adapter hyperparameters.

    Matches the FinGPT v3 defaults: rank=8, alpha=16, dropout=0.05.
    """

    r: int = Field(default=8, description="LoRA rank")
    alpha: int = Field(default=16, description="LoRA alpha scaling")
    dropout: float = Field(default=0.05)
    bias: str = Field(default="none", description="'none' | 'lora_only' | 'all'")
    target_modules: list[str] = Field(
        default_factory=lambda: ["q_proj", "v_proj"],
        description="Module suffix list to attach LoRA adapters to",
    )
    task_type: str = Field(default="CAUSAL_LM")


class QLoRAConfig(BaseModel):
    """bitsandbytes 4-bit quantization config (QLoRA)."""

    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = Field(default="bfloat16")
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_quant_type: str = Field(default="nf4")


class FinetuneJob(BaseModel):
    """Top-level fine-tuning job config."""

    name: str
    base_model: str = Field(
        description="HuggingFace id of the base model (e.g. meta-llama/Llama-2-7b-hf)"
    )
    dataset: str = Field(
        description="Dataset slug from aqp.ml.applications.sentiment.datasets "
        "(``fingpt-sentiment``, ``fingpt-headline``, ...) or an HF dataset id",
    )
    output_dir: str = Field(
        default="",
        description="Directory to write the adapter. Defaults to "
        "``settings.models_dir / finetune / <name>``",
    )
    lora: LoRAConfig = Field(default_factory=LoRAConfig)
    qlora: QLoRAConfig | None = Field(
        default=None,
        description="Set to enable 4-bit quantization. Requires bitsandbytes.",
    )

    # SFTTrainer kwargs
    learning_rate: float = 2e-4
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    num_train_epochs: float = 1.0
    max_seq_length: int = 1024
    warmup_ratio: float = 0.03
    logging_steps: int = 20
    save_steps: int = 500
    eval_steps: int = 0
    weight_decay: float = 0.0
    optim: str = Field(default="paged_adamw_8bit")
    bf16: bool = True
    fp16: bool = False
    gradient_checkpointing: bool = True
    dataloader_num_workers: int = 2

    # Optional safety / reproducibility knobs
    seed: int = 42
    max_examples: int | None = None

    # MLflow
    mlflow_experiment: str | None = None
    mlflow_run_name: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)

    def resolved_output_dir(self, default_root: Path) -> Path:
        if self.output_dir:
            return Path(self.output_dir)
        return Path(default_root) / "finetune" / self.name
