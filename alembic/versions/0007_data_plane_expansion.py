"""data plane expansion: data_sources, identifier_links, data_links, fred_series, sec_filings, gdelt_mentions

Revision ID: 0007_data_plane_expansion
Revises: 0006_agentic_trading
Create Date: 2026-04-24

Adds the foundation for FRED, SEC EDGAR and GDelt integrations plus a
polymorphic identifier graph so every data source can tie back to the
canonical :class:`Instrument`.

New tables:

- ``data_sources`` — registry of every source AQP knows how to ingest
  from. Seeded with canonical rows for fred, sec_edgar, gdelt,
  yfinance, polygon, alpha_vantage, ibkr, local, alpaca and ccxt.
- ``identifier_links`` — polymorphic, time-versioned identifier graph
  (ticker / cik / cusip / isin / figi / lei / ...).
- ``data_links`` — "dataset version X contains data about entity Y"
  coverage rows that feed the data-availability UI.
- ``fred_series`` — FRED economic-series master (DGS10, UNRATE, ...).
- ``sec_filings`` — SEC EDGAR filing master keyed on accession_no.
- ``gdelt_mentions`` — lean subset of GDelt GKG events that match a
  registered instrument.

No existing table is modified; this migration is strictly additive.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_data_plane_expansion"
down_revision = "0006_agentic_trading"
branch_labels = None
depends_on = None


_CANONICAL_SOURCES: list[dict[str, object]] = [
    {
        "name": "fred",
        "display_name": "FRED (Federal Reserve Economic Data)",
        "kind": "rest_api",
        "vendor": "Federal Reserve Bank of St. Louis",
        "auth_type": "api_key",
        "base_url": "https://api.stlouisfed.org/fred",
        "protocol": "https/json",
        "capabilities": '{"domains":["economic.series"],"frequencies":["Daily","Weekly","Monthly","Quarterly","Annual"],"supports_historical":true}',
        "rate_limits": '{"req_per_minute":120}',
        "credentials_ref": "AQP_FRED_API_KEY",
    },
    {
        "name": "sec_edgar",
        "display_name": "SEC EDGAR filings",
        "kind": "sdk",
        "vendor": "U.S. Securities and Exchange Commission",
        "auth_type": "identity",
        "base_url": "https://www.sec.gov",
        "protocol": "https/json+xml",
        "capabilities": '{"domains":["filings.index","filings.xbrl","filings.insider","filings.ownership","filings.events"],"forms":["10-K","10-Q","8-K","4","13F-HR","DEF 14A","S-1","N-PORT","N-MFP"]}',
        "rate_limits": '{"req_per_second":10}',
        "credentials_ref": "AQP_SEC_EDGAR_IDENTITY",
    },
    {
        "name": "gdelt",
        "display_name": "GDELT Global Knowledge Graph 2.0",
        "kind": "file_manifest",
        "vendor": "The GDELT Project",
        "auth_type": "none",
        "base_url": "http://data.gdeltproject.org/gkg",
        "protocol": "https/csv.zip",
        "capabilities": '{"domains":["events.gdelt","news"],"frequencies":["15m"],"supports_bigquery":true,"bigquery_table":"gdelt-bq.gdeltv2.gkg"}',
        "rate_limits": '{}',
        "credentials_ref": None,
    },
    {
        "name": "yfinance",
        "display_name": "Yahoo Finance (yfinance)",
        "kind": "sdk",
        "vendor": "Yahoo",
        "auth_type": "none",
        "base_url": "https://finance.yahoo.com",
        "protocol": "https/json",
        "capabilities": '{"domains":["market.bars","market.fundamentals","news"],"frequencies":["1m","5m","15m","1h","1d","1w"]}',
        "rate_limits": '{"req_per_minute":60}',
        "credentials_ref": None,
    },
    {
        "name": "polygon",
        "display_name": "Polygon.io",
        "kind": "rest_api",
        "vendor": "Polygon.io",
        "auth_type": "api_key",
        "base_url": "https://api.polygon.io",
        "protocol": "https/json",
        "capabilities": '{"domains":["market.bars","market.quotes","market.ticks"],"frequencies":["1m","5m","15m","1h","1d","1w"]}',
        "rate_limits": '{"req_per_minute":5}',
        "credentials_ref": "AQP_POLYGON_API_KEY",
    },
    {
        "name": "alpha_vantage",
        "display_name": "Alpha Vantage",
        "kind": "rest_api",
        "vendor": "Alpha Vantage",
        "auth_type": "api_key",
        "base_url": "https://www.alphavantage.co",
        "protocol": "https/json",
        "capabilities": '{"domains":["market.bars","market.fundamentals"],"frequencies":["1d","1w","1mo"]}',
        "rate_limits": '{"req_per_minute":5}',
        "credentials_ref": "AQP_ALPHA_VANTAGE_API_KEY",
    },
    {
        "name": "ibkr",
        "display_name": "Interactive Brokers (TWS / IB Gateway)",
        "kind": "sdk",
        "vendor": "Interactive Brokers",
        "auth_type": "identity",
        "base_url": "tcp://127.0.0.1",
        "protocol": "tcp/ib-async",
        "capabilities": '{"domains":["market.bars","market.quotes","market.ticks"],"frequencies":["1s","1m","5m","15m","1h","1d"]}',
        "rate_limits": '{"concurrent_requests":50}',
        "credentials_ref": "AQP_IBKR_HOST",
    },
    {
        "name": "local",
        "display_name": "Local CSV / Parquet files",
        "kind": "local_file",
        "vendor": "local",
        "auth_type": "none",
        "base_url": None,
        "protocol": "file",
        "capabilities": '{"domains":["market.bars"],"frequencies":["arbitrary"]}',
        "rate_limits": '{}',
        "credentials_ref": None,
    },
    {
        "name": "alpaca",
        "display_name": "Alpaca Markets",
        "kind": "sdk",
        "vendor": "Alpaca",
        "auth_type": "api_key",
        "base_url": "https://api.alpaca.markets",
        "protocol": "https/json",
        "capabilities": '{"domains":["market.bars","market.quotes"],"frequencies":["1m","5m","15m","1h","1d"]}',
        "rate_limits": '{"req_per_minute":200}',
        "credentials_ref": "AQP_ALPACA_API_KEY",
    },
    {
        "name": "ccxt",
        "display_name": "CCXT crypto exchanges",
        "kind": "sdk",
        "vendor": "ccxt",
        "auth_type": "api_key",
        "base_url": None,
        "protocol": "https/json",
        "capabilities": '{"domains":["market.bars"],"frequencies":["1m","5m","15m","1h","1d"]}',
        "rate_limits": '{}',
        "credentials_ref": None,
    },
]


def upgrade() -> None:
    # data_sources ----------------------------------------------------------
    op.create_table(
        "data_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="rest_api"),
        sa.Column("vendor", sa.String(length=120), nullable=True),
        sa.Column("auth_type", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column("protocol", sa.String(length=64), nullable=False, server_default="https/json"),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("rate_limits", sa.JSON(), nullable=True),
        sa.Column("credentials_ref", sa.String(length=120), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_data_sources_name", "data_sources", ["name"], unique=True)

    # Seed canonical rows. ``op.execute`` with literal JSON strings keeps
    # the migration portable across Postgres + SQLite without depending on
    # dialect-specific JSON types at bulk_insert time.
    import uuid as _uuid

    connection = op.get_bind()
    for row in _CANONICAL_SOURCES:
        connection.execute(
            sa.text(
                """
                INSERT INTO data_sources (
                    id, name, display_name, kind, vendor, auth_type, base_url,
                    protocol, capabilities, rate_limits, credentials_ref, enabled
                ) VALUES (
                    :id, :name, :display_name, :kind, :vendor, :auth_type, :base_url,
                    :protocol, :capabilities, :rate_limits, :credentials_ref, TRUE
                )
                """
            ),
            {"id": str(_uuid.uuid4()), **row},
        )

    # identifier_links ------------------------------------------------------
    op.create_table(
        "identifier_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column(
            "instrument_id",
            sa.String(length=36),
            sa.ForeignKey("instruments.id"),
            nullable=True,
        ),
        sa.Column("scheme", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=240), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("data_sources.id"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_identifier_links_entity_kind", "identifier_links", ["entity_kind"])
    op.create_index("ix_identifier_links_entity_id", "identifier_links", ["entity_id"])
    op.create_index("ix_identifier_links_instrument_id", "identifier_links", ["instrument_id"])
    op.create_index("ix_identifier_links_scheme", "identifier_links", ["scheme"])
    op.create_index("ix_identifier_links_value", "identifier_links", ["value"])
    op.create_index("ix_identifier_links_source_id", "identifier_links", ["source_id"])
    op.create_index("ix_identifier_links_scheme_value", "identifier_links", ["scheme", "value"])
    op.create_index("ix_identifier_links_entity", "identifier_links", ["entity_kind", "entity_id"])
    op.create_index(
        "uq_identifier_links_unique",
        "identifier_links",
        ["entity_kind", "scheme", "value", "valid_from"],
        unique=True,
    )

    # data_links ------------------------------------------------------------
    op.create_table(
        "data_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "dataset_version_id",
            sa.String(length=36),
            sa.ForeignKey("dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("data_sources.id"),
            nullable=True,
        ),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column(
            "instrument_id",
            sa.String(length=36),
            sa.ForeignKey("instruments.id"),
            nullable=True,
        ),
        sa.Column("coverage_start", sa.DateTime(), nullable=True),
        sa.Column("coverage_end", sa.DateTime(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_data_links_dataset_version_id", "data_links", ["dataset_version_id"])
    op.create_index("ix_data_links_source_id", "data_links", ["source_id"])
    op.create_index("ix_data_links_entity_kind", "data_links", ["entity_kind"])
    op.create_index("ix_data_links_entity_id", "data_links", ["entity_id"])
    op.create_index("ix_data_links_instrument_id", "data_links", ["instrument_id"])
    op.create_index(
        "ix_data_links_instrument_kind",
        "data_links",
        ["instrument_id", "entity_kind"],
    )

    # fred_series -----------------------------------------------------------
    op.create_table(
        "fred_series",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("series_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("units", sa.String(length=120), nullable=True),
        sa.Column("units_short", sa.String(length=60), nullable=True),
        sa.Column("frequency", sa.String(length=32), nullable=True),
        sa.Column("frequency_short", sa.String(length=8), nullable=True),
        sa.Column("seasonal_adj", sa.String(length=16), nullable=True),
        sa.Column("seasonal_adj_short", sa.String(length=8), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("release_id", sa.Integer(), nullable=True),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("data_sources.id"),
            nullable=True,
        ),
        sa.Column("observation_start", sa.DateTime(), nullable=True),
        sa.Column("observation_end", sa.DateTime(), nullable=True),
        sa.Column("popularity", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fred_series_series_id", "fred_series", ["series_id"], unique=True)
    op.create_index("ix_fred_series_source_id", "fred_series", ["source_id"])

    # sec_filings -----------------------------------------------------------
    op.create_table(
        "sec_filings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("cik", sa.String(length=16), nullable=False),
        sa.Column(
            "instrument_id",
            sa.String(length=36),
            sa.ForeignKey("instruments.id"),
            nullable=True,
        ),
        sa.Column("accession_no", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=32), nullable=False),
        sa.Column("filed_at", sa.DateTime(), nullable=False),
        sa.Column("period_of_report", sa.DateTime(), nullable=True),
        sa.Column("primary_doc_url", sa.String(length=1024), nullable=True),
        sa.Column("primary_doc_type", sa.String(length=16), nullable=True),
        sa.Column("xbrl_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("text_storage_uri", sa.String(length=1024), nullable=True),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("data_sources.id"),
            nullable=True,
        ),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sec_filings_cik", "sec_filings", ["cik"])
    op.create_index("ix_sec_filings_instrument_id", "sec_filings", ["instrument_id"])
    op.create_index("ix_sec_filings_accession_no", "sec_filings", ["accession_no"], unique=True)
    op.create_index("ix_sec_filings_form", "sec_filings", ["form"])
    op.create_index("ix_sec_filings_filed_at", "sec_filings", ["filed_at"])
    op.create_index("ix_sec_filings_source_id", "sec_filings", ["source_id"])
    op.create_index("ix_sec_filings_cik_form", "sec_filings", ["cik", "form"])
    op.create_index("ix_sec_filings_cik_filed_at", "sec_filings", ["cik", "filed_at"])

    # gdelt_mentions --------------------------------------------------------
    op.create_table(
        "gdelt_mentions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("gkg_record_id", sa.String(length=64), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("source_common_name", sa.String(length=240), nullable=True),
        sa.Column("document_identifier", sa.String(length=2048), nullable=True),
        sa.Column(
            "instrument_id",
            sa.String(length=36),
            sa.ForeignKey("instruments.id"),
            nullable=True,
        ),
        sa.Column("themes", sa.JSON(), nullable=True),
        sa.Column("tone", sa.JSON(), nullable=True),
        sa.Column("organizations_match", sa.JSON(), nullable=True),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("data_sources.id"),
            nullable=True,
        ),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_gdelt_mentions_gkg_record_id",
        "gdelt_mentions",
        ["gkg_record_id"],
        unique=True,
    )
    op.create_index("ix_gdelt_mentions_date", "gdelt_mentions", ["date"])
    op.create_index("ix_gdelt_mentions_instrument_id", "gdelt_mentions", ["instrument_id"])
    op.create_index("ix_gdelt_mentions_source_id", "gdelt_mentions", ["source_id"])
    op.create_index(
        "ix_gdelt_mentions_instrument_date",
        "gdelt_mentions",
        ["instrument_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_gdelt_mentions_instrument_date", "gdelt_mentions")
    op.drop_index("ix_gdelt_mentions_source_id", "gdelt_mentions")
    op.drop_index("ix_gdelt_mentions_instrument_id", "gdelt_mentions")
    op.drop_index("ix_gdelt_mentions_date", "gdelt_mentions")
    op.drop_index("ix_gdelt_mentions_gkg_record_id", "gdelt_mentions")
    op.drop_table("gdelt_mentions")

    op.drop_index("ix_sec_filings_cik_filed_at", "sec_filings")
    op.drop_index("ix_sec_filings_cik_form", "sec_filings")
    op.drop_index("ix_sec_filings_source_id", "sec_filings")
    op.drop_index("ix_sec_filings_filed_at", "sec_filings")
    op.drop_index("ix_sec_filings_form", "sec_filings")
    op.drop_index("ix_sec_filings_accession_no", "sec_filings")
    op.drop_index("ix_sec_filings_instrument_id", "sec_filings")
    op.drop_index("ix_sec_filings_cik", "sec_filings")
    op.drop_table("sec_filings")

    op.drop_index("ix_fred_series_source_id", "fred_series")
    op.drop_index("ix_fred_series_series_id", "fred_series")
    op.drop_table("fred_series")

    op.drop_index("ix_data_links_instrument_kind", "data_links")
    op.drop_index("ix_data_links_instrument_id", "data_links")
    op.drop_index("ix_data_links_entity_id", "data_links")
    op.drop_index("ix_data_links_entity_kind", "data_links")
    op.drop_index("ix_data_links_source_id", "data_links")
    op.drop_index("ix_data_links_dataset_version_id", "data_links")
    op.drop_table("data_links")

    op.drop_index("uq_identifier_links_unique", "identifier_links")
    op.drop_index("ix_identifier_links_entity", "identifier_links")
    op.drop_index("ix_identifier_links_scheme_value", "identifier_links")
    op.drop_index("ix_identifier_links_source_id", "identifier_links")
    op.drop_index("ix_identifier_links_value", "identifier_links")
    op.drop_index("ix_identifier_links_scheme", "identifier_links")
    op.drop_index("ix_identifier_links_instrument_id", "identifier_links")
    op.drop_index("ix_identifier_links_entity_id", "identifier_links")
    op.drop_index("ix_identifier_links_entity_kind", "identifier_links")
    op.drop_table("identifier_links")

    op.drop_index("ix_data_sources_name", "data_sources")
    op.drop_table("data_sources")
