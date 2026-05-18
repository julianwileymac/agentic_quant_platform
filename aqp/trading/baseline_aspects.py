"""Baseline metadata aspects for built-in paper-trading configs."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from aqp.metadata import write_aspect
from aqp.metadata.openmetadata.models_ml import MlModel
from aqp.metadata.openmetadata.models_pipeline import Pipeline, PipelineTask
from aqp.persistence.models_aspects import EntityAspect

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaperBaselineConfig:
    """Static baseline metadata config for one paper YAML recipe."""

    config_name: str
    config_filename: str
    model_urn: str
    pipeline_urn: str
    algorithm: str
    target: str


_MODEL_DISPLAY_NAMES: dict[str, str] = {
    "alpaca_mean_rev": "Alpaca Paper — Mean Reversion",
    "ibkr_mean_rev": "IBKR Paper — Mean Reversion",
    "avellaneda_stoikov_quotes": "Paper — Avellaneda-Stoikov Quotes",
    "lucic_tse_options": "Paper — Lucic-Tse Options Portfolio",
    "tradier_rest": "Tradier Sandbox — Mean Reversion",
}


BASELINE_PAPER_CONFIGS: list[PaperBaselineConfig] = [
    PaperBaselineConfig(
        config_name="alpaca_mean_rev",
        config_filename="alpaca_mean_rev",
        model_urn="urn:aqp:mlmodel:prod:alpaca_mean_reversion_baseline_v1",
        pipeline_urn="urn:aqp:pipeline:prod:alpaca_paper_mean_reversion",
        algorithm="linear_regression",
        target="forward_return_1d",
    ),
    PaperBaselineConfig(
        config_name="ibkr_mean_rev",
        config_filename="ibkr_mean_rev",
        model_urn="urn:aqp:mlmodel:prod:ibkr_mean_reversion_baseline_v1",
        pipeline_urn="urn:aqp:pipeline:prod:ibkr_paper_mean_reversion",
        algorithm="linear_regression",
        target="forward_return_1d",
    ),
    PaperBaselineConfig(
        config_name="avellaneda_stoikov_quotes",
        config_filename="avellaneda_stoikov_quotes",
        model_urn="urn:aqp:mlmodel:prod:avellaneda_stoikov_quoter_v1",
        pipeline_urn="urn:aqp:pipeline:prod:avellaneda_stoikov_paper_quoter",
        algorithm="custom",
        target="optimal_quote_spread",
    ),
    PaperBaselineConfig(
        config_name="lucic_tse_options",
        config_filename="lucic_tse_options",
        model_urn="urn:aqp:mlmodel:prod:lucic_tse_options_quoter_v1",
        pipeline_urn="urn:aqp:pipeline:prod:lucic_tse_paper_options",
        algorithm="custom",
        target="optimal_quote_spread",
    ),
    PaperBaselineConfig(
        config_name="tradier_rest",
        config_filename="tradier_rest",
        model_urn="urn:aqp:mlmodel:prod:tradier_rest_baseline_v1",
        pipeline_urn="urn:aqp:pipeline:prod:tradier_paper_rest_router",
        algorithm="custom",
        target="intent_signal",
    ),
]


def _canonical_payload_hash(payload_model: BaseModel) -> str:
    payload = payload_model.model_dump(mode="json", by_alias=True)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_aspect_if_absent(
    session: Session,
    *,
    urn: str,
    aspect_name: str,
    payload_model: BaseModel,
) -> bool:
    payload_hash = _canonical_payload_hash(payload_model)
    existing = session.execute(
        select(EntityAspect.id).where(
            EntityAspect.urn == urn,
            EntityAspect.aspect_name == aspect_name,
            EntityAspect.payload_hash == payload_hash,
        )
    ).scalar_one_or_none()
    write_aspect(
        session,
        urn=urn,
        aspect_name=aspect_name,
        payload_model=payload_model,
        created_by="seed_paper_baseline_aspects",
        system_metadata={"source": "paper_baseline_seed"},
    )
    return existing is None


def _model_name(config_name: str) -> str:
    if config_name not in _MODEL_DISPLAY_NAMES:
        raise ValueError(f"No model display name configured for {config_name!r}")
    return _MODEL_DISPLAY_NAMES[config_name]


def _build_model_aspect(config: PaperBaselineConfig) -> MlModel:
    return MlModel(
        urn=config.model_urn,
        name=_model_name(config.config_name),
        algorithm=config.algorithm,
        target=config.target,
        status="Production",
        ml_features=[],
        ml_hyper_parameters=[],
        model_version="v1.0.0-baseline",
        mlflow_run_id=None,
    )


def _build_pipeline_aspect(config: PaperBaselineConfig) -> Pipeline:
    return Pipeline(
        urn=config.pipeline_urn,
        name=f"{config.config_name} paper pipeline",
        pipeline_location=f"configs/paper/{config.config_filename}.yaml",
        tasks=[PipelineTask(name="paper_session_run", task_type="mcp_tool")],
        start_date=None,
        end_date=None,
    )


def seed_paper_baseline_aspects(session: Session) -> dict[str, int]:
    """Idempotently write baseline model/pipeline aspects for paper configs."""
    models_written = 0
    pipelines_written = 0
    for config in BASELINE_PAPER_CONFIGS:
        if _write_aspect_if_absent(
            session,
            urn=config.model_urn,
            aspect_name=MlModel.aspect_name,
            payload_model=_build_model_aspect(config),
        ):
            models_written += 1
        if _write_aspect_if_absent(
            session,
            urn=config.pipeline_urn,
            aspect_name=Pipeline.aspect_name,
            payload_model=_build_pipeline_aspect(config),
        ):
            pipelines_written += 1
    return {"models_written": models_written, "pipelines_written": pipelines_written}


__all__ = [
    "BASELINE_PAPER_CONFIGS",
    "PaperBaselineConfig",
    "seed_paper_baseline_aspects",
]
