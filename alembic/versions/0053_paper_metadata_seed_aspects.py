"""Seed strict paper-trading metadata aspects.

Revision ID: 0053_paper_metadata_seed_aspects
Revises: 0052_account_mgmt
Create Date: 2026-05-18

Renumbered from a transient ``0049_paper_metadata_seed_aspects`` slug
to resolve a parallel-branch collision with ``0049_paper_baseline_aspects``
(rule 6 chain hygiene). The chain now linearises through the parallel
``0050_terraform_iac_plus_entra`` -> ``0051_seed_wiley_tech`` ->
``0052_account_mgmt`` heads.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision = "0053_paper_metadata_seed_aspects"
down_revision = "0052_account_mgmt"
branch_labels = None
depends_on = None

_MIGRATION_ACTOR = "migration:0053_paper_metadata_seed_aspects"
_SYSTEM_METADATA = {"source": "alembic:0053_paper_metadata_seed_aspects"}

# PredictorSpec.model_kind currently allows:
# {"xgboost","lstm","transformer","linear","tcn","lightgbm","random_forest"}.
# Any paper algorithm label outside that set is intentionally normalised to
# "custom" so the payload remains valid against MlModel's algorithm validator.
_PREDICTOR_MODEL_KINDS = {
    "xgboost",
    "lstm",
    "transformer",
    "linear",
    "tcn",
    "lightgbm",
    "random_forest",
}


class _PaperSeed:
    """Seed tuple for one paper config's model and pipeline URNs."""

    __slots__ = (
        "config_filename",
        "display_name",
        "model_urn",
        "pipeline_urn",
        "algorithm",
        "target",
        "status",
    )

    def __init__(
        self,
        *,
        config_filename: str,
        display_name: str,
        model_urn: str,
        pipeline_urn: str,
        algorithm: str,
        target: str,
        status: str,
    ) -> None:
        self.config_filename = config_filename
        self.display_name = display_name
        self.model_urn = model_urn
        self.pipeline_urn = pipeline_urn
        self.algorithm = algorithm
        self.target = target
        self.status = status


_PAPER_SEEDS: tuple[_PaperSeed, ...] = (
    _PaperSeed(
        config_filename="alpaca_mean_rev.yaml",
        display_name="Alpaca Paper - Mean Reversion",
        model_urn="urn:aqp:mlmodel:prod:alpaca_mean_reversion_v1",
        pipeline_urn="urn:aqp:pipeline:prod:alpaca_mean_reversion_loop",
        algorithm="mean_reversion_z",
        target="forward_return_1d",
        status="Production",
    ),
    _PaperSeed(
        config_filename="ibkr_mean_rev.yaml",
        display_name="IBKR Paper - Mean Reversion",
        model_urn="urn:aqp:mlmodel:prod:ibkr_mean_reversion_v1",
        pipeline_urn="urn:aqp:pipeline:prod:ibkr_mean_reversion_loop",
        algorithm="mean_reversion_z",
        target="forward_return_1d",
        status="Production",
    ),
    _PaperSeed(
        config_filename="avellaneda_stoikov_quotes.yaml",
        display_name="Paper - Avellaneda Stoikov Quotes",
        model_urn="urn:aqp:mlmodel:prod:avellaneda_stoikov_v1",
        pipeline_urn="urn:aqp:pipeline:prod:avellaneda_stoikov_quotes_loop",
        algorithm="avellaneda_stoikov",
        target="optimal_bid_ask_spread",
        status="Production",
    ),
    _PaperSeed(
        config_filename="lucic_tse_options.yaml",
        display_name="Paper - Lucic Tse Options Portfolio",
        model_urn="urn:aqp:mlmodel:prod:lucic_tse_options_v1",
        pipeline_urn="urn:aqp:pipeline:prod:lucic_tse_options_loop",
        algorithm="lucic_tse",
        target="portfolio_greek_curve",
        status="Production",
    ),
    _PaperSeed(
        config_filename="tradier_rest.yaml",
        display_name="Tradier Sandbox - Mean Reversion",
        model_urn="urn:aqp:mlmodel:prod:tradier_rest_baseline_v1",
        pipeline_urn="urn:aqp:pipeline:prod:tradier_rest_loop",
        algorithm="baseline_buyhold",
        target="pnl_eod",
        status="Production",
    ),
)

_INSERT_ENTITY = sa.text(
    """
    INSERT INTO metadata_entities (
        urn,
        entity_type
    )
    VALUES (
        :urn,
        :entity_type
    )
    ON CONFLICT (urn) DO NOTHING
    """
)

_INSERT_ASPECT = sa.text(
    """
    INSERT INTO entity_aspects (
        id,
        urn,
        aspect_name,
        version,
        payload,
        payload_hash,
        system_metadata,
        created_by
    )
    SELECT
        :id,
        :urn,
        :aspect_name,
        COALESCE(
            (
                SELECT MAX(version) + 1
                FROM entity_aspects
                WHERE urn = :urn
                  AND aspect_name = :aspect_name
            ),
            1
        ),
        CAST(:payload AS JSONB),
        :payload_hash,
        CAST(:system_metadata AS JSONB),
        :created_by
    WHERE NOT EXISTS (
        SELECT 1
        FROM entity_aspects
        WHERE urn = :urn
          AND aspect_name = :aspect_name
          AND payload_hash = :payload_hash
    )
    ON CONFLICT (urn, aspect_name, payload_hash) DO NOTHING
    """
)

_DELETE_ASPECT = sa.text(
    """
    DELETE FROM entity_aspects
    WHERE urn = :urn
      AND aspect_name = :aspect_name
      AND payload_hash = :payload_hash
    """
)

_DELETE_ENTITY_IF_ORPHAN = sa.text(
    """
    DELETE FROM metadata_entities
    WHERE urn = :urn
      AND NOT EXISTS (
          SELECT 1
          FROM entity_aspects
          WHERE entity_aspects.urn = metadata_entities.urn
      )
    """
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalise_algorithm(raw_algorithm: str) -> str:
    candidate = str(raw_algorithm).strip().lower()
    if candidate in _PREDICTOR_MODEL_KINDS:
        return candidate
    return "custom"


def _build_ml_model_payload(seed: _PaperSeed) -> dict[str, Any]:
    return {
        "urn": seed.model_urn,
        "name": seed.display_name,
        "algorithm": _normalise_algorithm(seed.algorithm),
        "ml_features": [],
        "ml_hyper_parameters": [],
        "target": seed.target,
        "status": seed.status,
        "model_version": None,
        "mlflow_run_id": None,
    }


def _build_pipeline_payload(seed: _PaperSeed) -> dict[str, Any]:
    config_stem = (
        seed.config_filename[:-5]
        if seed.config_filename.endswith(".yaml")
        else seed.config_filename
    )
    return {
        "urn": seed.pipeline_urn,
        "name": f"{config_stem} paper pipeline",
        "pipeline_location": f"configs/paper/{seed.config_filename}",
        "tasks": [],
        "start_date": None,
        "end_date": None,
    }


def _insert_entity(bind: sa.Connection, *, urn: str, entity_type: str) -> None:
    bind.execute(_INSERT_ENTITY, {"urn": urn, "entity_type": entity_type})


def _insert_aspect(
    bind: sa.Connection,
    *,
    urn: str,
    aspect_name: str,
    payload: dict[str, Any],
) -> None:
    bind.execute(
        _INSERT_ASPECT,
        {
            "id": _uuid(),
            "urn": urn,
            "aspect_name": aspect_name,
            "payload": _canonical_json(payload),
            "payload_hash": _payload_hash(payload),
            "system_metadata": _canonical_json(_SYSTEM_METADATA),
            "created_by": _MIGRATION_ACTOR,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        logger.info("Skipping 0053_paper_metadata_seed_aspects on non-Postgres dialect")
        return

    for seed in _PAPER_SEEDS:
        _insert_entity(bind, urn=seed.model_urn, entity_type="mlmodel")
        _insert_entity(bind, urn=seed.pipeline_urn, entity_type="pipeline")

    for seed in _PAPER_SEEDS:
        _insert_aspect(
            bind,
            urn=seed.model_urn,
            aspect_name="mlModelMetadata",
            payload=_build_ml_model_payload(seed),
        )
        _insert_aspect(
            bind,
            urn=seed.pipeline_urn,
            aspect_name="pipelineMetadata",
            payload=_build_pipeline_payload(seed),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    seeded_aspects: list[tuple[str, str, str]] = []
    seeded_urns: list[str] = []
    for seed in _PAPER_SEEDS:
        model_payload = _build_ml_model_payload(seed)
        pipeline_payload = _build_pipeline_payload(seed)
        seeded_aspects.append(
            (
                seed.model_urn,
                "mlModelMetadata",
                _payload_hash(model_payload),
            )
        )
        seeded_aspects.append(
            (
                seed.pipeline_urn,
                "pipelineMetadata",
                _payload_hash(pipeline_payload),
            )
        )
        seeded_urns.extend([seed.model_urn, seed.pipeline_urn])

    for urn, aspect_name, payload_hash in seeded_aspects:
        bind.execute(
            _DELETE_ASPECT,
            {
                "urn": urn,
                "aspect_name": aspect_name,
                "payload_hash": payload_hash,
            },
        )

    for urn in seeded_urns:
        bind.execute(_DELETE_ENTITY_IF_ORPHAN, {"urn": urn})
