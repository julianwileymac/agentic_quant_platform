"""add flink_trading schema for streaming pipeline sinks

Revision ID: 0005_flink_trading_schema
Revises: 0004_quant_ml_planning
Create Date: 2026-04-23

Ports the SQL in
``rpi_kubernetes/kubernetes/base-services/flink/flink-postgres-init.yaml``
into a versioned migration owned by aqp. Flink's JDBC sinks write into
this schema; strategies and Dagster assets can query it alongside the
rest of the AQP ledger.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_flink_trading_schema"
down_revision = "0004_quant_ml_planning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS flink_trading")

    op.create_table(
        "market_data",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=True),
        sa.Column("volume", sa.Numeric(18, 4), nullable=True),
        sa.Column("bid", sa.Numeric(18, 8), nullable=True),
        sa.Column("ask", sa.Numeric(18, 8), nullable=True),
        sa.Column("bid_size", sa.Numeric(18, 4), nullable=True),
        sa.Column("ask_size", sa.Numeric(18, 4), nullable=True),
        sa.Column("open", sa.Numeric(18, 8), nullable=True),
        sa.Column("high", sa.Numeric(18, 8), nullable=True),
        sa.Column("low", sa.Numeric(18, 8), nullable=True),
        sa.Column("close", sa.Numeric(18, 8), nullable=True),
        sa.Column("bar_volume", sa.Numeric(18, 4), nullable=True),
        sa.Column("vwap", sa.Numeric(18, 8), nullable=True),
        sa.Column("bar_interval", sa.String(length=16), nullable=True),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingest_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        schema="flink_trading",
    )
    op.create_index(
        "idx_market_data_symbol_ts",
        "market_data",
        ["symbol", sa.text("event_timestamp DESC")],
        schema="flink_trading",
    )
    op.create_index(
        "idx_market_data_source_ts",
        "market_data",
        ["data_source", sa.text("event_timestamp DESC")],
        schema="flink_trading",
    )

    op.create_table(
        "indicators",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_size_sec", sa.Integer(), nullable=False),
        sa.Column("sma_5", sa.Numeric(18, 8)),
        sa.Column("sma_10", sa.Numeric(18, 8)),
        sa.Column("sma_20", sa.Numeric(18, 8)),
        sa.Column("sma_50", sa.Numeric(18, 8)),
        sa.Column("ema_12", sa.Numeric(18, 8)),
        sa.Column("ema_26", sa.Numeric(18, 8)),
        sa.Column("rsi_14", sa.Numeric(8, 4)),
        sa.Column("macd_line", sa.Numeric(18, 8)),
        sa.Column("macd_signal", sa.Numeric(18, 8)),
        sa.Column("macd_histogram", sa.Numeric(18, 8)),
        sa.Column("bb_upper", sa.Numeric(18, 8)),
        sa.Column("bb_middle", sa.Numeric(18, 8)),
        sa.Column("bb_lower", sa.Numeric(18, 8)),
        sa.Column("atr_14", sa.Numeric(18, 8)),
        sa.Column("vwap", sa.Numeric(18, 8)),
        sa.Column("volume_sma_20", sa.Numeric(18, 4)),
        sa.Column("obv", sa.Numeric(18, 4)),
        sa.Column("price_lag_1", sa.Numeric(18, 8)),
        sa.Column("price_lag_5", sa.Numeric(18, 8)),
        sa.Column("price_lag_10", sa.Numeric(18, 8)),
        sa.Column("volume_lag_1", sa.Numeric(18, 4)),
        sa.Column("return_1", sa.Numeric(12, 8)),
        sa.Column("return_5", sa.Numeric(12, 8)),
        sa.Column("return_10", sa.Numeric(12, 8)),
        sa.Column(
            "compute_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="flink_trading",
    )
    op.create_index(
        "idx_indicators_symbol_window",
        "indicators",
        ["symbol", sa.text("window_end DESC")],
        schema="flink_trading",
    )

    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("signal_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("norm_price", sa.Numeric(12, 8)),
        sa.Column("norm_volume", sa.Numeric(12, 8)),
        sa.Column("norm_rsi", sa.Numeric(12, 8)),
        sa.Column("norm_macd", sa.Numeric(12, 8)),
        sa.Column("norm_bb_width", sa.Numeric(12, 8)),
        sa.Column("norm_atr", sa.Numeric(12, 8)),
        sa.Column("norm_return_1", sa.Numeric(12, 8)),
        sa.Column("norm_return_5", sa.Numeric(12, 8)),
        sa.Column("feature_vector", sa.ARRAY(sa.Float()), nullable=True),
        sa.Column(
            "normalization_method", sa.String(length=32), server_default=sa.text("'zscore'")
        ),
        sa.Column(
            "emit_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="flink_trading",
    )
    op.create_index(
        "idx_signals_symbol_ts",
        "signals",
        ["symbol", sa.text("signal_timestamp DESC")],
        schema="flink_trading",
    )

    op.create_table(
        "job_metadata",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=64)),
        sa.Column("flink_job_id", sa.String(length=64)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("checkpoint_path", sa.String(length=512)),
        sa.Column("savepoint_path", sa.String(length=512)),
        sa.Column("records_in", sa.BigInteger(), server_default=sa.text("0")),
        sa.Column("records_out", sa.BigInteger(), server_default=sa.text("0")),
        sa.Column("error_message", sa.Text()),
        sa.Column("config_snapshot", sa.JSON()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="flink_trading",
    )
    op.create_index(
        "idx_job_metadata_name_status",
        "job_metadata",
        ["job_name", "status"],
        schema="flink_trading",
    )


def downgrade() -> None:
    op.drop_index("idx_job_metadata_name_status", "job_metadata", schema="flink_trading")
    op.drop_table("job_metadata", schema="flink_trading")
    op.drop_index("idx_signals_symbol_ts", "signals", schema="flink_trading")
    op.drop_table("signals", schema="flink_trading")
    op.drop_index("idx_indicators_symbol_window", "indicators", schema="flink_trading")
    op.drop_table("indicators", schema="flink_trading")
    op.drop_index("idx_market_data_source_ts", "market_data", schema="flink_trading")
    op.drop_index("idx_market_data_symbol_ts", "market_data", schema="flink_trading")
    op.drop_table("market_data", schema="flink_trading")
    op.execute("DROP SCHEMA IF EXISTS flink_trading CASCADE")
