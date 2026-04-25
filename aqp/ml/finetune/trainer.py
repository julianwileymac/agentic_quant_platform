"""LoRA / QLoRA trainer wrapping HF + PEFT + TRL.

Executes one :class:`FinetuneJob` and writes the resulting adapter to
disk. Logs every knob + final metrics to MLflow when available.

This module imports heavy deps (peft, trl, transformers, bitsandbytes,
accelerate, datasets) lazily inside :func:`run_finetune` so the
platform's base install doesn't require GPU-class wheels.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.ml.finetune.config import FinetuneJob
from aqp.ml.finetune.datasets import build_dataset

logger = logging.getLogger(__name__)


def run_finetune(job: FinetuneJob) -> dict[str, Any]:
    """Run one fine-tuning job end-to-end.

    Returns a summary dict with the output directory, final training
    metrics, and (when available) the MLflow ``run_id``.
    """
    try:
        import torch  # noqa: F401  -- required by every path below
        from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from trl import SFTTrainer
    except ImportError as exc:
        raise RuntimeError(
            "Fine-tuning requires the `[fingpt]` optional extras: "
            "peft, trl, transformers, bitsandbytes, accelerate, datasets."
        ) from exc

    out_dir: Path = job.resolved_output_dir(settings.models_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(job.base_model, use_fast=True, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    bnb_config = None
    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
    }
    if job.qlora is not None and job.qlora.load_in_4bit:
        import torch  # local import keeps the module-level torch import clean

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=(
                torch.bfloat16 if job.qlora.bnb_4bit_compute_dtype == "bfloat16" else torch.float16
            ),
            bnb_4bit_use_double_quant=job.qlora.bnb_4bit_use_double_quant,
            bnb_4bit_quant_type=job.qlora.bnb_4bit_quant_type,
        )
        model_kwargs["quantization_config"] = bnb_config
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(job.base_model, **model_kwargs)
    if bnb_config is not None:
        model = prepare_model_for_kbit_training(model)

    lora_cfg = LoraConfig(
        r=job.lora.r,
        lora_alpha=job.lora.alpha,
        lora_dropout=job.lora.dropout,
        bias=job.lora.bias,
        task_type=job.lora.task_type,
        target_modules=list(job.lora.target_modules or []) or None,
    )
    model = get_peft_model(model, lora_cfg)

    train_ds = build_dataset(job.dataset, max_examples=job.max_examples, split="train")

    args = TrainingArguments(
        output_dir=str(out_dir),
        per_device_train_batch_size=job.batch_size,
        gradient_accumulation_steps=job.gradient_accumulation_steps,
        num_train_epochs=job.num_train_epochs,
        learning_rate=job.learning_rate,
        warmup_ratio=job.warmup_ratio,
        logging_steps=job.logging_steps,
        save_steps=job.save_steps,
        bf16=job.bf16,
        fp16=job.fp16,
        gradient_checkpointing=job.gradient_checkpointing,
        weight_decay=job.weight_decay,
        optim=job.optim,
        dataloader_num_workers=job.dataloader_num_workers,
        seed=job.seed,
        report_to=[],
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        args=args,
        dataset_text_field="text",
        max_seq_length=job.max_seq_length,
        packing=False,
    )

    mlflow_run_id = None
    try:
        import mlflow

        if job.mlflow_experiment:
            mlflow.set_experiment(job.mlflow_experiment)
        with mlflow.start_run(run_name=job.mlflow_run_name or job.name) as active:
            mlflow_run_id = active.info.run_id
            mlflow.log_params(
                {
                    "base_model": job.base_model,
                    "dataset": job.dataset,
                    "lora_r": job.lora.r,
                    "lora_alpha": job.lora.alpha,
                    "qlora": bool(job.qlora),
                    "epochs": job.num_train_epochs,
                    "batch_size": job.batch_size,
                    "grad_accum": job.gradient_accumulation_steps,
                }
            )
            trainer.train()
            mlflow.log_metrics(
                {
                    "train_loss": float(getattr(trainer.state, "log_history", [{}])[-1].get("loss", 0.0)),
                }
            )
    except Exception as exc:
        logger.info("MLflow logging skipped: %s", exc)
        trainer.train()

    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    return {
        "output_dir": str(out_dir),
        "base_model": job.base_model,
        "dataset": job.dataset,
        "mlflow_run_id": mlflow_run_id,
        "log_history": list(getattr(trainer.state, "log_history", [])),
    }
