"""Smoke tests that the expanded persistence metadata registers all new tables.

We don't run the Alembic migration inline (the alembic helper needs a full
harness); instead we assert that ``Base.metadata`` contains every table the
migration creates, so any drift between ORM and migration is caught at test
time.
"""
from __future__ import annotations

from aqp.persistence import Base


EXPECTED_NEW_TABLES = {
    # Instrument subclass tables
    "instrument_equity",
    "instrument_etf",
    "instrument_index",
    "instrument_bond",
    "instrument_future",
    "instrument_option",
    "instrument_fx_pair",
    "instrument_crypto",
    "instrument_cfd",
    "instrument_commodity",
    "instrument_synthetic",
    "instrument_betting",
    "instrument_tokenized_asset",
    # Entity graph
    "issuers",
    "government_entities",
    "fund_issuers",
    "sectors",
    "industries",
    "industry_classifications",
    "entity_relationships",
    "locations",
    "key_executives",
    "executive_compensation",
    # Fundamentals
    "financial_statements",
    "financial_ratios",
    "key_metrics",
    "historical_market_cap",
    "revenue_breakdowns",
    "earnings_call_transcripts",
    "management_discussion_analyses",
    "reported_financials",
    # Events / calendar
    "corporate_events",
    "earnings_events",
    "dividend_events",
    "split_events",
    "ipo_events",
    "merger_events",
    "calendar_events",
    "analyst_estimates",
    "price_targets",
    "forward_estimates",
    "regulatory_events",
    "esg_events",
    # Ownership
    "insider_transactions",
    "institutional_holdings",
    "form_13f_holdings",
    "short_interest_snapshots",
    "shares_float_snapshots",
    "politician_trades",
    "fund_holdings",
    # News
    "news_items",
    "news_item_entities",
    "news_sentiments",
    # Macro / microstructure
    "economic_series",
    "economic_observations",
    "cot_reports",
    "bls_series",
    "treasury_rates",
    "yield_curves",
    "option_series",
    "option_chains_snapshots",
    "futures_curves",
    "market_holidays",
    "market_status_history",
    # Taxonomy
    "taxonomy_schemes",
    "taxonomy_nodes",
    "entity_tags",
    "entity_crosswalk",
}


def test_every_expected_table_registered():
    metadata_tables = set(Base.metadata.tables.keys())
    missing = EXPECTED_NEW_TABLES - metadata_tables
    assert not missing, f"missing tables: {sorted(missing)}"


def test_instrument_discriminator_present():
    instruments = Base.metadata.tables["instruments"]
    assert "instrument_class" in instruments.columns
    assert "issuer_id" in instruments.columns


def test_back_compat_columns_preserved():
    instruments = Base.metadata.tables["instruments"]
    for required in (
        "id",
        "vt_symbol",
        "ticker",
        "exchange",
        "asset_class",
        "security_type",
        "identifiers",
        "sector",
        "industry",
        "region",
        "currency",
        "tags",
        "meta",
        "created_at",
        "updated_at",
    ):
        assert required in instruments.columns


def test_issuers_has_full_openbb_parity_columns():
    issuers = Base.metadata.tables["issuers"]
    for col in (
        "id",
        "name",
        "legal_name",
        "cik",
        "lei",
        "cusip",
        "isin",
        "figi",
        "permid",
        "sic",
        "naics",
        "stock_exchange",
        "currency",
        "country",
        "employees",
        "ceo",
        "short_description",
        "long_description",
        "company_url",
        "latest_filing_date",
        "first_stock_price_date",
        "last_stock_price_date",
    ):
        assert col in issuers.columns, f"missing column on issuers: {col}"


def test_financial_statements_unique_key():
    fs = Base.metadata.tables["financial_statements"]
    # The ORM uses ``Index(..., unique=True)`` for the uniqueness guarantee,
    # which SQLAlchemy stores as a unique index rather than a constraint.
    unique_index_names = {i.name for i in fs.indexes if i.unique}
    assert "uq_fin_stmt" in unique_index_names


def test_corporate_events_indexed():
    ce = Base.metadata.tables["corporate_events"]
    index_names = {i.name for i in ce.indexes}
    assert any("corp_event" in name for name in index_names)


def test_entity_tags_composite_key():
    et = Base.metadata.tables["entity_tags"]
    unique_index_names = {i.name for i in et.indexes if i.unique}
    assert "uq_entity_tag" in unique_index_names
