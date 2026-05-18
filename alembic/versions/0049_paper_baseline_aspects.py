"""Seed baseline metadata aspects for paper configs.

Revision ID: 0049_paper_baseline_aspects
Revises: 0048_metadata_aspects
Create Date: 2026-05-17
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision = "0049_paper_baseline_aspects"
down_revision = "0048_metadata_aspects"
branch_labels = None
depends_on = None

_MIGRATION_ACTOR = "migration:0049_paper_baseline_aspects"
_SYSTEM_METADATA = {"source": "alembic:0049_paper_baseline_aspects"}


class _AspectSeed:
    """Typed container for one seeded metadata aspect row."""

    __slots__ = ("urn", "entity_type", "aspect_name", "payload", "payload_hash")

    def __init__(
        self,
        *,
        urn: str,
        entity_type: str,
        aspect_name: str,
        payload: dict[str, Any],
        payload_hash: str,
    ) -> None:
        self.urn = urn
        self.entity_type = entity_type
        self.aspect_name = aspect_name
        self.payload = payload
        self.payload_hash = payload_hash


def _uuid() -> str:
    return str(uuid.uuid4())


def _to_canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


_MODEL_SEEDS: tuple[_AspectSeed, ...] = (
    _AspectSeed(
        urn="urn:aqp:mlmodel:prod:alpaca_mean_reversion_baseline_v1",
        entity_type="mlmodel",
        aspect_name="mlModelMetadata",
        payload={
            "urn": "urn:aqp:mlmodel:prod:alpaca_mean_reversion_baseline_v1",
            "name": "Alpaca Paper — Mean Reversion",
            "algorithm": "linear_regression",
            "ml_features": [],
            "ml_hyper_parameters": [],
            "target": "forward_return_1d",
            "status": "Production",
            "model_version": "v1.0.0-baseline",
            "mlflow_run_id": None,
        },
        payload_hash="75029ef1a19398abcdc18d8d99bba5dd80b7478a509ecaf53d9be04747d5f3c9",
    ),
    _AspectSeed(
        urn="urn:aqp:mlmodel:prod:ibkr_mean_reversion_baseline_v1",
        entity_type="mlmodel",
        aspect_name="mlModelMetadata",
        payload={
            "urn": "urn:aqp:mlmodel:prod:ibkr_mean_reversion_baseline_v1",
            "name": "IBKR Paper — Mean Reversion",
            "algorithm": "linear_regression",
            "ml_features": [],
            "ml_hyper_parameters": [],
            "target": "forward_return_1d",
            "status": "Production",
            "model_version": "v1.0.0-baseline",
            "mlflow_run_id": None,
        },
        payload_hash="c333737f1e294e1469cfe3c4774a26ec8ceecb5b39ccd3ef179a9056f8d876eb",
    ),
    _AspectSeed(
        urn="urn:aqp:mlmodel:prod:avellaneda_stoikov_quoter_v1",
        entity_type="mlmodel",
        aspect_name="mlModelMetadata",
        payload={
            "urn": "urn:aqp:mlmodel:prod:avellaneda_stoikov_quoter_v1",
            "name": "Paper — Avellaneda-Stoikov Quotes",
            "algorithm": "custom",
            "ml_features": [],
            "ml_hyper_parameters": [],
            "target": "optimal_quote_spread",
            "status": "Production",
            "model_version": "v1.0.0-baseline",
            "mlflow_run_id": None,
        },
        payload_hash="5ee3500dffe20beae82e5fdc6d13994d3a2b6cab6030f11031de9a9cfbecfdba",
    ),
    _AspectSeed(
        urn="urn:aqp:mlmodel:prod:lucic_tse_options_quoter_v1",
        entity_type="mlmodel",
        aspect_name="mlModelMetadata",
        payload={
            "urn": "urn:aqp:mlmodel:prod:lucic_tse_options_quoter_v1",
            "name": "Paper — Lucic-Tse Options Portfolio",
            "algorithm": "custom",
            "ml_features": [],
            "ml_hyper_parameters": [],
            "target": "optimal_quote_spread",
            "status": "Production",
            "model_version": "v1.0.0-baseline",
            "mlflow_run_id": None,
        },
        payload_hash="b8c891ad627198d048d152023269f9c78a84cecde816c6353e8c7737097e6c83",
    ),
    _AspectSeed(
        urn="urn:aqp:mlmodel:prod:tradier_rest_baseline_v1",
        entity_type="mlmodel",
        aspect_name="mlModelMetadata",
        payload={
            "urn": "urn:aqp:mlmodel:prod:tradier_rest_baseline_v1",
            "name": "Tradier Sandbox — Mean Reversion",
            "algorithm": "custom",
            "ml_features": [],
            "ml_hyper_parameters": [],
            "target": "intent_signal",
            "status": "Production",
            "model_version": "v1.0.0-baseline",
            "mlflow_run_id": None,
        },
        payload_hash="21c32994b482ce45e0f91385bd8ba270797f9adcfc4f672725ceb49c86ddb67f",
    ),
)

_PIPELINE_SEEDS: tuple[_AspectSeed, ...] = (
    _AspectSeed(
        urn="urn:aqp:pipeline:prod:alpaca_paper_mean_reversion",
        entity_type="pipeline",
        aspect_name="pipelineMetadata",
        payload={
            "urn": "urn:aqp:pipeline:prod:alpaca_paper_mean_reversion",
            "name": "alpaca_mean_rev paper pipeline",
            "pipeline_location": "configs/paper/alpaca_mean_rev.yaml",
            "tasks": [
                {
                    "name": "paper_session_run",
                    "task_type": "mcp_tool",
                    "upstream_tasks": [],
                    "description": None,
                    "start_date": None,
                    "end_date": None,
                }
            ],
            "start_date": None,
            "end_date": None,
        },
        payload_hash="b773ac2aba0a77ae7feb528a340969a78d17aee8966ecdbe866855302b9d86e8",
    ),
    _AspectSeed(
        urn="urn:aqp:pipeline:prod:ibkr_paper_mean_reversion",
        entity_type="pipeline",
        aspect_name="pipelineMetadata",
        payload={
            "urn": "urn:aqp:pipeline:prod:ibkr_paper_mean_reversion",
            "name": "ibkr_mean_rev paper pipeline",
            "pipeline_location": "configs/paper/ibkr_mean_rev.yaml",
            "tasks": [
                {
                    "name": "paper_session_run",
                    "task_type": "mcp_tool",
                    "upstream_tasks": [],
                    "description": None,
                    "start_date": None,
                    "end_date": None,
                }
            ],
            "start_date": None,
            "end_date": None,
        },
        payload_hash="213ff843ce859e62d2f29b8ea872fb5e333b7193b4bc6f57e3a1473745ed0146",
    ),
    _AspectSeed(
        urn="urn:aqp:pipeline:prod:avellaneda_stoikov_paper_quoter",
        entity_type="pipeline",
        aspect_name="pipelineMetadata",
        payload={
            "urn": "urn:aqp:pipeline:prod:avellaneda_stoikov_paper_quoter",
            "name": "avellaneda_stoikov_quotes paper pipeline",
            "pipeline_location": "configs/paper/avellaneda_stoikov_quotes.yaml",
            "tasks": [
                {
                    "name": "paper_session_run",
                    "task_type": "mcp_tool",
                    "upstream_tasks": [],
                    "description": None,
                    "start_date": None,
                    "end_date": None,
                }
            ],
            "start_date": None,
            "end_date": None,
        },
        payload_hash="5dc6d4ed27e8ac9c9e627613b6aaf9f36e916ad662242226221bd22bedc6b568",
    ),
    _AspectSeed(
        urn="urn:aqp:pipeline:prod:lucic_tse_paper_options",
        entity_type="pipeline",
        aspect_name="pipelineMetadata",
        payload={
            "urn": "urn:aqp:pipeline:prod:lucic_tse_paper_options",
            "name": "lucic_tse_options paper pipeline",
            "pipeline_location": "configs/paper/lucic_tse_options.yaml",
            "tasks": [
                {
                    "name": "paper_session_run",
                    "task_type": "mcp_tool",
                    "upstream_tasks": [],
                    "description": None,
                    "start_date": None,
                    "end_date": None,
                }
            ],
            "start_date": None,
            "end_date": None,
        },
        payload_hash="f9e5a2758fe0113bb116c52bc494e06c5ccfed8933dea6334fc1720d41837773",
    ),
    _AspectSeed(
        urn="urn:aqp:pipeline:prod:tradier_paper_rest_router",
        entity_type="pipeline",
        aspect_name="pipelineMetadata",
        payload={
            "urn": "urn:aqp:pipeline:prod:tradier_paper_rest_router",
            "name": "tradier_rest paper pipeline",
            "pipeline_location": "configs/paper/tradier_rest.yaml",
            "tasks": [
                {
                    "name": "paper_session_run",
                    "task_type": "mcp_tool",
                    "upstream_tasks": [],
                    "description": None,
                    "start_date": None,
                    "end_date": None,
                }
            ],
            "start_date": None,
            "end_date": None,
        },
        payload_hash="3a1ee0227c683a1a4a4c6da174eda15cda4b90bd92847719d3b62519e035e6ac",
    ),
)

_ALL_SEEDS: tuple[_AspectSeed, ...] = _MODEL_SEEDS + _PIPELINE_SEEDS

_INSERT_ENTITY_POSTGRES = sa.text(
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

_INSERT_ENTITY_SQLITE = sa.text(
    """
    INSERT OR IGNORE INTO metadata_entities (
        urn,
        entity_type
    )
    VALUES (
        :urn,
        :entity_type
    )
    """
)

_INSERT_ASPECT_POSTGRES = sa.text(
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

_INSERT_ASPECT_SQLITE = sa.text(
    """
    INSERT OR IGNORE INTO entity_aspects (
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
        :payload,
        :payload_hash,
        :system_metadata,
        :created_by
    WHERE NOT EXISTS (
        SELECT 1
        FROM entity_aspects
        WHERE urn = :urn
          AND aspect_name = :aspect_name
          AND payload_hash = :payload_hash
    )
    """
)

_DELETE_SEEDED_ASPECT = sa.text(
    """
    DELETE FROM entity_aspects
    WHERE urn = :urn
      AND aspect_name = :aspect_name
      AND payload_hash = :payload_hash
    """
)

_DELETE_ORPHAN_ENTITY = sa.text(
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


def _insert_metadata_entity(bind: sa.Connection, *, urn: str, entity_type: str) -> None:
    statement = (
        _INSERT_ENTITY_POSTGRES
        if bind.dialect.name == "postgresql"
        else _INSERT_ENTITY_SQLITE
    )
    bind.execute(statement, {"urn": urn, "entity_type": entity_type})


def _insert_entity_aspect(bind: sa.Connection, seed: _AspectSeed) -> None:
    statement = (
        _INSERT_ASPECT_POSTGRES
        if bind.dialect.name == "postgresql"
        else _INSERT_ASPECT_SQLITE
    )
    bind.execute(
        statement,
        {
            "id": _uuid(),
            "urn": seed.urn,
            "aspect_name": seed.aspect_name,
            "payload": _to_canonical_json(seed.payload),
            "payload_hash": seed.payload_hash,
            "system_metadata": _to_canonical_json(_SYSTEM_METADATA),
            "created_by": _MIGRATION_ACTOR,
        },
    )


def upgrade() -> None:
    bind = op.get_bind()
    for seed in _ALL_SEEDS:
        _insert_metadata_entity(bind, urn=seed.urn, entity_type=seed.entity_type)
    for seed in _ALL_SEEDS:
        _insert_entity_aspect(bind, seed)


def downgrade() -> None:
    bind = op.get_bind()
    for seed in _ALL_SEEDS:
        bind.execute(
            _DELETE_SEEDED_ASPECT,
            {
                "urn": seed.urn,
                "aspect_name": seed.aspect_name,
                "payload_hash": seed.payload_hash,
            },
        )
    for urn in sorted({seed.urn for seed in _ALL_SEEDS}):
        bind.execute(_DELETE_ORPHAN_ENTITY, {"urn": urn})
