"""domain model expansion: polymorphic instruments + issuers + fundamentals + events + ownership + news + macro + taxonomy

Revision ID: 0008_domain_model_expansion
Revises: 0007_data_plane_expansion
Create Date: 2026-04-24

Expands the platform's persistence layer to carry the full polymorphic
instrument hierarchy, corporate-entity graph, fundamentals, events,
ownership, news, macro/economic, options/futures, microstructure, and
taxonomy/tagging tables introduced alongside :mod:`aqp.core.domain`.

New things:

- ``instruments`` table gains ``instrument_class`` discriminator + richer
  columns (``issuer_id``, ``tick_size``, ``multiplier``, ``min_quantity``,
  ``max_quantity``, ``lot_size``, ``price_precision``, ``size_precision``,
  ``is_active``).
- 13 joined-table subclass tables for the :class:`Instrument` polymorphic
  hierarchy (equity / etf / index / bond / future / option / fx_pair /
  crypto / cfd / commodity / synthetic / betting / tokenized_asset).
- Corporate entity graph: ``issuers``, ``government_entities``,
  ``fund_issuers``, ``sectors``, ``industries``, ``industry_classifications``,
  ``entity_relationships``, ``locations``, ``key_executives``,
  ``executive_compensation``.
- Fundamentals: ``financial_statements``, ``financial_ratios``,
  ``key_metrics``, ``historical_market_cap``, ``revenue_breakdowns``,
  ``earnings_call_transcripts``, ``management_discussion_analyses``,
  ``reported_financials``.
- Events: ``corporate_events``, ``earnings_events``, ``dividend_events``,
  ``split_events``, ``ipo_events``, ``merger_events``, ``calendar_events``,
  ``analyst_estimates``, ``price_targets``, ``forward_estimates``,
  ``regulatory_events``, ``esg_events``.
- Ownership: ``insider_transactions``, ``institutional_holdings``,
  ``form_13f_holdings``, ``short_interest_snapshots``,
  ``shares_float_snapshots``, ``politician_trades``, ``fund_holdings``.
- News: ``news_items``, ``news_item_entities``, ``news_sentiments``.
- Macro: ``economic_series``, ``economic_observations``, ``cot_reports``,
  ``bls_series``, ``treasury_rates``, ``yield_curves``.
- Options/futures: ``option_series``, ``option_chains_snapshots``,
  ``futures_curves``.
- Microstructure: ``market_holidays``, ``market_status_history``.
- Taxonomy: ``taxonomy_schemes``, ``taxonomy_nodes``, ``entity_tags``,
  ``entity_crosswalk`` + seeded SIC / NAICS / GICS / TRBC / ICB / BICS /
  NACE roots.

Existing rows are untouched — ``instruments`` gets new nullable columns.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0008_domain_model_expansion"
down_revision = "0007_data_plane_expansion"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json():
    return sa.JSON()


def _uuid_pk():
    return sa.Column("id", sa.String(36), primary_key=True)


def _audit_cols():
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # -----------------------------------------------------------------
    # Extend instruments table
    # -----------------------------------------------------------------
    existing_cols = {c["name"] for c in inspector.get_columns("instruments")}

    def _add_col(name: str, col: sa.Column) -> None:
        if name not in existing_cols:
            op.add_column("instruments", col)

    _add_col("instrument_class", sa.Column("instrument_class", sa.String(32), nullable=True))
    _add_col("issuer_id", sa.Column("issuer_id", sa.String(36), nullable=True))
    _add_col("tick_size", sa.Column("tick_size", sa.Float(), nullable=True))
    _add_col("multiplier", sa.Column("multiplier", sa.Float(), nullable=True))
    _add_col("min_quantity", sa.Column("min_quantity", sa.Float(), nullable=True))
    _add_col("max_quantity", sa.Column("max_quantity", sa.Float(), nullable=True))
    _add_col("lot_size", sa.Column("lot_size", sa.Float(), nullable=True))
    _add_col("price_precision", sa.Column("price_precision", sa.Integer(), nullable=True))
    _add_col("size_precision", sa.Column("size_precision", sa.Integer(), nullable=True))
    _add_col(
        "is_active",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    existing_instr_indexes = {i["name"] for i in inspector.get_indexes("instruments")}
    if "ix_instruments_instrument_class" not in existing_instr_indexes:
        op.create_index(
            "ix_instruments_instrument_class",
            "instruments",
            ["instrument_class"],
        )
    if "ix_instruments_issuer_id" not in existing_instr_indexes:
        op.create_index("ix_instruments_issuer_id", "instruments", ["issuer_id"])

    # -----------------------------------------------------------------
    # Issuers + related
    # -----------------------------------------------------------------
    op.create_table(
        "issuers",
        _uuid_pk(),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("legal_name", sa.String(240), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="corporate"),
        sa.Column("cik", sa.String(16), nullable=True),
        sa.Column("lei", sa.String(20), nullable=True),
        sa.Column("cusip", sa.String(16), nullable=True),
        sa.Column("isin", sa.String(16), nullable=True),
        sa.Column("figi", sa.String(16), nullable=True),
        sa.Column("permid", sa.String(32), nullable=True),
        sa.Column("gvkey", sa.String(16), nullable=True),
        sa.Column("irs_ein", sa.String(16), nullable=True),
        sa.Column("entity_legal_form", sa.String(120), nullable=True),
        sa.Column("entity_status", sa.String(32), nullable=True),
        sa.Column("inc_state", sa.String(64), nullable=True),
        sa.Column("inc_country", sa.String(64), nullable=True),
        sa.Column("stock_exchange", sa.String(120), nullable=True),
        sa.Column("primary_listing", sa.String(64), nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("is_listed", sa.Boolean(), server_default=sa.true()),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("employees", sa.Integer(), nullable=True),
        sa.Column("sic", sa.Integer(), nullable=True),
        sa.Column("naics", sa.String(16), nullable=True),
        sa.Column("sector_id", sa.String(36), nullable=True),
        sa.Column("industry_id", sa.String(36), nullable=True),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("long_description", sa.Text(), nullable=True),
        sa.Column("company_url", sa.String(512), nullable=True),
        sa.Column("template", sa.String(120), nullable=True),
        sa.Column("ceo", sa.String(240), nullable=True),
        sa.Column("latest_filing_date", sa.Date(), nullable=True),
        sa.Column("first_fundamental_date", sa.Date(), nullable=True),
        sa.Column("last_fundamental_date", sa.Date(), nullable=True),
        sa.Column("first_stock_price_date", sa.Date(), nullable=True),
        sa.Column("last_stock_price_date", sa.Date(), nullable=True),
        sa.Column("identifiers", _json(), server_default="{}"),
        sa.Column("tags", _json(), server_default="[]"),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_issuers_name", "issuers", ["name"])
    op.create_index("ix_issuers_kind", "issuers", ["kind"])
    op.create_index("ix_issuers_cik", "issuers", ["cik"])
    op.create_unique_constraint("uq_issuers_lei", "issuers", ["lei"])
    op.create_index("ix_issuers_sector_id", "issuers", ["sector_id"])
    op.create_index("ix_issuers_industry_id", "issuers", ["industry_id"])

    op.create_table(
        "government_entities",
        sa.Column("id", sa.String(36), sa.ForeignKey("issuers.id"), primary_key=True),
        sa.Column("jurisdiction", sa.String(120), nullable=True),
        sa.Column("credit_rating_sp", sa.String(16), nullable=True),
        sa.Column("credit_rating_moodys", sa.String(16), nullable=True),
        sa.Column("credit_rating_fitch", sa.String(16), nullable=True),
    )

    op.create_table(
        "fund_issuers",
        sa.Column("id", sa.String(36), sa.ForeignKey("issuers.id"), primary_key=True),
        sa.Column("fund_family", sa.String(240), nullable=True),
        sa.Column("manager", sa.String(240), nullable=True),
        sa.Column("aum", sa.Float(), nullable=True),
        sa.Column("inception", sa.Date(), nullable=True),
        sa.Column("fund_type", sa.String(32), nullable=True),
    )

    op.create_table(
        "sectors",
        _uuid_pk(),
        sa.Column("scheme", sa.String(16), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("sectors.id"), nullable=True),
        sa.UniqueConstraint("scheme", "code", name="ix_sectors_scheme_code"),
    )

    op.create_table(
        "industries",
        _uuid_pk(),
        sa.Column("scheme", sa.String(16), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("sector_id", sa.String(36), sa.ForeignKey("sectors.id"), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("industries.id"), nullable=True),
        sa.UniqueConstraint("scheme", "code", name="ix_industries_scheme_code"),
    )

    op.create_table(
        "industry_classifications",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=False),
        sa.Column("scheme", sa.String(16), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("label", sa.String(240), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_code", sa.String(32), nullable=True),
        *_audit_cols(),
    )
    op.create_index("ix_industry_cls_issuer_scheme", "industry_classifications", ["issuer_id", "scheme"])
    op.create_index("ix_industry_cls_code", "industry_classifications", ["scheme", "code"])

    op.create_table(
        "entity_relationships",
        _uuid_pk(),
        sa.Column("from_kind", sa.String(32), nullable=False, server_default="issuer"),
        sa.Column("from_entity_id", sa.String(64), nullable=False),
        sa.Column("to_kind", sa.String(32), nullable=False, server_default="issuer"),
        sa.Column("to_entity_id", sa.String(64), nullable=False),
        sa.Column("relationship_type", sa.String(32), nullable=False),
        sa.Column("ownership_pct", sa.Float(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
    )
    op.create_index("ix_rel_from", "entity_relationships", ["from_entity_id"])
    op.create_index("ix_rel_to", "entity_relationships", ["to_entity_id"])
    op.create_index("ix_rel_type", "entity_relationships", ["relationship_type"])
    op.create_index(
        "ix_rel_from_to_type",
        "entity_relationships",
        ["from_entity_id", "to_entity_id", "relationship_type"],
    )

    op.create_table(
        "locations",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("country_iso", sa.String(8), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("postal_code", sa.String(16), nullable=True),
        sa.Column("address_line1", sa.String(240), nullable=True),
        sa.Column("address_line2", sa.String(240), nullable=True),
        sa.Column("phone", sa.String(48), nullable=True),
        sa.Column("is_headquarters", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_mailing", sa.Boolean(), server_default=sa.false()),
        sa.Column("meta", _json(), server_default="{}"),
    )

    op.create_table(
        "key_executives",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("tenure_start", sa.Date(), nullable=True),
        sa.Column("tenure_end", sa.Date(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(16), nullable=True),
        sa.Column("compensation", sa.Float(), nullable=True),
        sa.Column("compensation_currency", sa.String(16), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
    )
    op.create_index("ix_key_exec_issuer", "key_executives", ["issuer_id"])

    op.create_table(
        "executive_compensation",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=False),
        sa.Column("executive_name", sa.String(240), nullable=False),
        sa.Column("title", sa.String(240), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("salary", sa.Float(), nullable=True),
        sa.Column("bonus", sa.Float(), nullable=True),
        sa.Column("stock_awards", sa.Float(), nullable=True),
        sa.Column("option_awards", sa.Float(), nullable=True),
        sa.Column("non_equity_incentives", sa.Float(), nullable=True),
        sa.Column("pension", sa.Float(), nullable=True),
        sa.Column("other_compensation", sa.Float(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), server_default="USD"),
    )
    op.create_index("ix_exec_comp_issuer_year", "executive_compensation", ["issuer_id", "fiscal_year"])

    # -----------------------------------------------------------------
    # Instrument subclass tables (joined-table polymorphism)
    # -----------------------------------------------------------------

    op.create_table(
        "instrument_equity",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("issuer_cik", sa.String(16), nullable=True),
        sa.Column("isin", sa.String(16), nullable=True),
        sa.Column("cusip", sa.String(16), nullable=True),
        sa.Column("figi", sa.String(16), nullable=True),
        sa.Column("lei", sa.String(20), nullable=True),
        sa.Column("share_class", sa.String(16), nullable=True),
        sa.Column("primary_listing_venue", sa.String(32), nullable=True),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("delisting_date", sa.Date(), nullable=True),
        sa.Column("shares_outstanding", sa.Float(), nullable=True),
        sa.Column("float_shares", sa.Float(), nullable=True),
        sa.Column("is_adr", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("gics_sector", sa.String(120), nullable=True),
        sa.Column("gics_industry", sa.String(120), nullable=True),
    )
    op.create_index("ix_inst_eq_isin", "instrument_equity", ["isin"])
    op.create_index("ix_inst_eq_cusip", "instrument_equity", ["cusip"])

    op.create_table(
        "instrument_etf",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("issuer_fund_id", sa.String(36), nullable=True),
        sa.Column("inception_date", sa.Date(), nullable=True),
        sa.Column("aum", sa.Float(), nullable=True),
        sa.Column("expense_ratio", sa.Float(), nullable=True),
        sa.Column("underlying_index", sa.String(120), nullable=True),
        sa.Column("holdings_ref", sa.String(240), nullable=True),
        sa.Column("is_leveraged", sa.Boolean(), server_default=sa.false()),
        sa.Column("leverage", sa.Float(), nullable=True),
        sa.Column("is_inverse", sa.Boolean(), server_default=sa.false()),
        sa.Column("replication", sa.String(32), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
    )

    op.create_table(
        "instrument_index",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("administrator", sa.String(120), nullable=True),
        sa.Column("methodology", sa.Text(), nullable=True),
        sa.Column("constituent_count", sa.Integer(), nullable=True),
        sa.Column("base_date", sa.Date(), nullable=True),
        sa.Column("base_value", sa.Float(), nullable=True),
    )

    op.create_table(
        "instrument_bond",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("coupon", sa.Float(), nullable=True),
        sa.Column("coupon_frequency", sa.String(24), nullable=True),
        sa.Column("maturity", sa.Date(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("face_value", sa.Float(), nullable=True),
        sa.Column("day_count", sa.String(16), nullable=True),
        sa.Column("seniority", sa.String(32), nullable=True),
        sa.Column("rating_sp", sa.String(16), nullable=True),
        sa.Column("rating_moodys", sa.String(16), nullable=True),
        sa.Column("rating_fitch", sa.String(16), nullable=True),
        sa.Column("callable", sa.Boolean(), server_default=sa.false()),
        sa.Column("putable", sa.Boolean(), server_default=sa.false()),
        sa.Column("convertible", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_inflation_linked", sa.Boolean(), server_default=sa.false()),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("bond_class", sa.String(32), nullable=True),
    )

    op.create_table(
        "instrument_future",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("underlying", sa.String(64), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=True),
        sa.Column("first_trade", sa.Date(), nullable=True),
        sa.Column("last_trade", sa.Date(), nullable=True),
        sa.Column("contract_size", sa.Float(), nullable=True),
        sa.Column("settlement_type", sa.String(16), nullable=True),
        sa.Column("cycle", sa.String(32), nullable=True),
        sa.Column("exchange_product_code", sa.String(32), nullable=True),
        sa.Column("delivery_month", sa.String(16), nullable=True),
    )
    op.create_index("ix_inst_fut_underlying", "instrument_future", ["underlying"])
    op.create_index("ix_inst_fut_expiry", "instrument_future", ["expiry"])

    op.create_table(
        "instrument_option",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("underlying", sa.String(64), nullable=True),
        sa.Column("strike", sa.Float(), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="call"),
        sa.Column("style", sa.String(16), nullable=True),
        sa.Column("contract_size", sa.Float(), nullable=True, server_default="100"),
        sa.Column("settlement_type", sa.String(16), nullable=True),
        sa.Column("exercise_price", sa.Float(), nullable=True),
        sa.Column("occ_symbol", sa.String(32), nullable=True),
        sa.Column("option_portfolio", sa.String(64), nullable=True),
    )
    op.create_index("ix_inst_opt_underlying", "instrument_option", ["underlying"])
    op.create_index("ix_inst_opt_expiry", "instrument_option", ["expiry"])
    op.create_index("ix_inst_opt_strike", "instrument_option", ["strike"])

    op.create_table(
        "instrument_fx_pair",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("base_currency", sa.String(16), nullable=False),
        sa.Column("quote_currency", sa.String(16), nullable=False),
        sa.Column("pip_size", sa.Float(), nullable=True),
        sa.Column("contract_size", sa.Float(), nullable=True),
    )

    op.create_table(
        "instrument_crypto",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("subtype", sa.String(16), nullable=True),
        sa.Column("underlying", sa.String(64), nullable=True),
        sa.Column("chain", sa.String(64), nullable=True),
        sa.Column("contract_address", sa.String(128), nullable=True),
        sa.Column("decimals", sa.Integer(), nullable=True),
        sa.Column("settlement_currency", sa.String(16), nullable=True),
        sa.Column("expiry", sa.DateTime(), nullable=True),
        sa.Column("funding_interval", sa.String(16), nullable=True),
        sa.Column("max_leverage", sa.Float(), nullable=True),
        sa.Column("maker_fee", sa.Float(), nullable=True),
        sa.Column("taker_fee", sa.Float(), nullable=True),
        sa.Column("is_inverse", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_native", sa.Boolean(), server_default=sa.false()),
        sa.Column("cmc_id", sa.Integer(), nullable=True),
        sa.Column("coingecko_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_inst_crypto_subtype", "instrument_crypto", ["subtype"])

    op.create_table(
        "instrument_cfd",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("underlying", sa.String(64), nullable=True),
        sa.Column("contract_size", sa.Float(), nullable=True),
        sa.Column("margin_rate", sa.Float(), nullable=True),
        sa.Column("financing_rate", sa.Float(), nullable=True),
    )

    op.create_table(
        "instrument_commodity",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("grade", sa.String(64), nullable=True),
        sa.Column("unit_of_measure", sa.String(32), nullable=True),
        sa.Column("delivery", sa.String(64), nullable=True),
    )

    op.create_table(
        "instrument_synthetic",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("legs", _json(), server_default="[]"),
        sa.Column("leg_weights", _json(), server_default="{}"),
        sa.Column("formula", sa.Text(), nullable=True),
    )

    op.create_table(
        "instrument_betting",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=True),
        sa.Column("event_name", sa.String(240), nullable=True),
        sa.Column("event_open", sa.DateTime(), nullable=True),
        sa.Column("market_id", sa.String(64), nullable=True),
        sa.Column("market_name", sa.String(240), nullable=True),
        sa.Column("market_type", sa.String(64), nullable=True),
        sa.Column("market_start", sa.DateTime(), nullable=True),
        sa.Column("selection_id", sa.String(64), nullable=True),
        sa.Column("selection_name", sa.String(240), nullable=True),
        sa.Column("selection_handicap", sa.Float(), nullable=True),
        sa.Column("competition", sa.String(120), nullable=True),
        sa.Column("country_code", sa.String(8), nullable=True),
    )

    op.create_table(
        "instrument_tokenized_asset",
        sa.Column("id", sa.String(36), sa.ForeignKey("instruments.id"), primary_key=True),
        sa.Column("chain", sa.String(64), nullable=True),
        sa.Column("contract_address", sa.String(128), nullable=True),
        sa.Column("token_standard", sa.String(32), nullable=True),
        sa.Column("supply", sa.Integer(), nullable=True),
        sa.Column("reference_asset", sa.String(240), nullable=True),
    )

    # -----------------------------------------------------------------
    # Fundamentals
    # -----------------------------------------------------------------
    op.create_table(
        "financial_statements",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("statement_type", sa.String(32), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False, server_default="annual"),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(8), nullable=True),
        sa.Column("currency", sa.String(16), server_default="USD"),
        sa.Column("reporting_currency", sa.String(16), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("gross_profit", sa.Float(), nullable=True),
        sa.Column("operating_income", sa.Float(), nullable=True),
        sa.Column("net_income", sa.Float(), nullable=True),
        sa.Column("ebitda", sa.Float(), nullable=True),
        sa.Column("total_assets", sa.Float(), nullable=True),
        sa.Column("total_liabilities", sa.Float(), nullable=True),
        sa.Column("total_equity", sa.Float(), nullable=True),
        sa.Column("cash_and_equivalents", sa.Float(), nullable=True),
        sa.Column("operating_cash_flow", sa.Float(), nullable=True),
        sa.Column("free_cash_flow", sa.Float(), nullable=True),
        sa.Column("capital_expenditure", sa.Float(), nullable=True),
        sa.Column("rows", _json(), server_default="{}"),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("source_filing_accession", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("issuer_id", "period", "period_type", "statement_type", name="uq_fin_stmt"),
    )
    op.create_index("ix_fin_stmt_symbol_period", "financial_statements", ["symbol", "period"])
    op.create_index("ix_fin_stmt_type", "financial_statements", ["statement_type"])

    op.create_table(
        "financial_ratios",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False, server_default="annual"),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("current_ratio", sa.Float(), nullable=True),
        sa.Column("quick_ratio", sa.Float(), nullable=True),
        sa.Column("cash_ratio", sa.Float(), nullable=True),
        sa.Column("gross_profit_margin", sa.Float(), nullable=True),
        sa.Column("operating_profit_margin", sa.Float(), nullable=True),
        sa.Column("net_profit_margin", sa.Float(), nullable=True),
        sa.Column("return_on_assets", sa.Float(), nullable=True),
        sa.Column("return_on_equity", sa.Float(), nullable=True),
        sa.Column("return_on_invested_capital", sa.Float(), nullable=True),
        sa.Column("debt_ratio", sa.Float(), nullable=True),
        sa.Column("debt_equity_ratio", sa.Float(), nullable=True),
        sa.Column("interest_coverage", sa.Float(), nullable=True),
        sa.Column("asset_turnover", sa.Float(), nullable=True),
        sa.Column("inventory_turnover", sa.Float(), nullable=True),
        sa.Column("dividend_yield", sa.Float(), nullable=True),
        sa.Column("payout_ratio", sa.Float(), nullable=True),
        sa.Column("extra", _json(), server_default="{}"),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("issuer_id", "period", "period_type", name="uq_fin_ratios"),
    )

    op.create_table(
        "key_metrics",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False, server_default="annual"),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("enterprise_value", sa.Float(), nullable=True),
        sa.Column("pe_ratio", sa.Float(), nullable=True),
        sa.Column("pb_ratio", sa.Float(), nullable=True),
        sa.Column("price_to_sales", sa.Float(), nullable=True),
        sa.Column("ev_to_ebitda", sa.Float(), nullable=True),
        sa.Column("ev_to_free_cash_flow", sa.Float(), nullable=True),
        sa.Column("earnings_yield", sa.Float(), nullable=True),
        sa.Column("free_cash_flow_yield", sa.Float(), nullable=True),
        sa.Column("revenue_per_share", sa.Float(), nullable=True),
        sa.Column("book_value_per_share", sa.Float(), nullable=True),
        sa.Column("free_cash_flow_per_share", sa.Float(), nullable=True),
        sa.Column("debt_to_equity", sa.Float(), nullable=True),
        sa.Column("net_debt_to_ebitda", sa.Float(), nullable=True),
        sa.Column("working_capital", sa.Float(), nullable=True),
        sa.Column("extra", _json(), server_default="{}"),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("issuer_id", "period", "period_type", name="uq_key_metrics"),
    )

    op.create_table(
        "historical_market_cap",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("market_cap", sa.Float(), nullable=False),
        sa.Column("enterprise_value", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("issuer_id", "date", name="uq_hist_mcap"),
    )

    op.create_table(
        "revenue_breakdowns",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("breakdown_type", sa.String(16), nullable=False),
        sa.Column("segment", sa.String(240), nullable=False),
        sa.Column("region", sa.String(120), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("percent_of_total", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )
    op.create_index(
        "ix_rev_breakdown_issuer_period",
        "revenue_breakdowns",
        ["issuer_id", "period", "breakdown_type"],
    )

    op.create_table(
        "earnings_call_transcripts",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.String(8), nullable=True),
        sa.Column("call_ts", sa.DateTime(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("participants", _json(), server_default="[]"),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("sentiment", _json(), server_default="{}"),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint(
            "issuer_id", "fiscal_year", "fiscal_quarter",
            name="uq_earnings_transcript",
        ),
    )

    op.create_table(
        "management_discussion_analyses",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("period", sa.Date(), nullable=True),
        sa.Column("period_type", sa.String(16), nullable=False, server_default="annual"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("source_filing_accession", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "reported_financials",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False, server_default="annual"),
        sa.Column("template", sa.String(120), nullable=True),
        sa.Column("rows", _json(), server_default="{}"),
        sa.Column("source_filing_accession", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )

    # -----------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------
    op.create_table(
        "corporate_events",
        _uuid_pk(),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("vt_symbol", sa.String(64), nullable=True),
        sa.Column("ex_date", sa.Date(), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("declaration_date", sa.Date(), nullable=True),
        sa.Column("announcement_text", sa.Text(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("ratio", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), nullable=True),
        sa.Column("new_symbol", sa.String(64), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("source_filing_accession", sa.String(32), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
    )
    op.create_index("ix_corp_event_instrument_kind", "corporate_events", ["instrument_id", "kind"])
    op.create_index("ix_corp_event_ex_date", "corporate_events", ["ex_date"])
    op.create_index("ix_corp_event_vt_symbol", "corporate_events", ["vt_symbol"])

    op.create_table(
        "earnings_events",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("fiscal_period", sa.String(16), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("announcement_ts", sa.DateTime(), nullable=True),
        sa.Column("call_start_ts", sa.DateTime(), nullable=True),
        sa.Column("eps_estimate", sa.Float(), nullable=True),
        sa.Column("eps_actual", sa.Float(), nullable=True),
        sa.Column("eps_surprise", sa.Float(), nullable=True),
        sa.Column("eps_surprise_pct", sa.Float(), nullable=True),
        sa.Column("revenue_estimate", sa.Float(), nullable=True),
        sa.Column("revenue_actual", sa.Float(), nullable=True),
        sa.Column("revenue_surprise", sa.Float(), nullable=True),
        sa.Column("transcript_id", sa.String(36), sa.ForeignKey("earnings_call_transcripts.id"), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("issuer_id", "fiscal_year", "fiscal_period", name="uq_earnings_event"),
    )

    op.create_table(
        "dividend_events",
        _uuid_pk(),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(16), server_default="USD"),
        sa.Column("ex_date", sa.Date(), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("declaration_date", sa.Date(), nullable=True),
        sa.Column("frequency", sa.String(32), nullable=True),
        sa.Column("is_special", sa.Boolean(), server_default=sa.false()),
        *_audit_cols(),
    )

    op.create_table(
        "split_events",
        _uuid_pk(),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("numerator", sa.Float(), nullable=True),
        sa.Column("denominator", sa.Float(), nullable=True),
        sa.Column("ratio", sa.String(32), nullable=True),
        sa.Column("ex_date", sa.Date(), nullable=True),
        sa.Column("record_date", sa.Date(), nullable=True),
        sa.Column("pay_date", sa.Date(), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "ipo_events",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("pricing_date", sa.Date(), nullable=True),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("offer_price_low", sa.Float(), nullable=True),
        sa.Column("offer_price_high", sa.Float(), nullable=True),
        sa.Column("offer_price_final", sa.Float(), nullable=True),
        sa.Column("shares_offered", sa.Float(), nullable=True),
        sa.Column("exchange", sa.String(32), nullable=True),
        sa.Column("underwriters", _json(), server_default="[]"),
        *_audit_cols(),
    )

    op.create_table(
        "merger_events",
        _uuid_pk(),
        sa.Column("acquirer_issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("target_issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("announced_date", sa.Date(), nullable=True),
        sa.Column("expected_close", sa.Date(), nullable=True),
        sa.Column("actual_close", sa.Date(), nullable=True),
        sa.Column("deal_value", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), server_default="USD"),
        sa.Column("consideration_cash", sa.Float(), nullable=True),
        sa.Column("consideration_stock_ratio", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
    )

    op.create_table(
        "calendar_events",
        _uuid_pk(),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("event_ts", sa.DateTime(), nullable=True),
        sa.Column("title", sa.String(480), nullable=True),
        sa.Column("country", sa.String(32), nullable=True),
        sa.Column("country_iso", sa.String(8), nullable=True),
        sa.Column("importance", sa.Integer(), nullable=True),
        sa.Column("actual", sa.Float(), nullable=True),
        sa.Column("consensus", sa.Float(), nullable=True),
        sa.Column("previous", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("frequency", sa.String(32), nullable=True),
        sa.Column("payload", _json(), server_default="{}"),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )
    op.create_index("ix_cal_event_type_date", "calendar_events", ["event_type", "event_date"])

    op.create_table(
        "analyst_estimates",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("period_ending", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(8), nullable=True),
        sa.Column("metric", sa.String(32), nullable=False, server_default="eps"),
        sa.Column("avg", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("analyst_count", sa.Integer(), nullable=True),
        sa.Column("revision_up", sa.Integer(), nullable=True),
        sa.Column("revision_down", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("issuer_id", "period_ending", "metric", name="uq_analyst_est"),
    )

    op.create_table(
        "price_targets",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("analyst_firm", sa.String(240), nullable=True),
        sa.Column("analyst_name", sa.String(240), nullable=True),
        sa.Column("rating", sa.String(32), nullable=True),
        sa.Column("previous_rating", sa.String(32), nullable=True),
        sa.Column("action", sa.String(32), nullable=True),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("previous_target", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), server_default="USD"),
        sa.Column("published_ts", sa.DateTime(), nullable=True),
        sa.Column("news_url", sa.String(1024), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )
    op.create_index("ix_price_target_published", "price_targets", ["published_ts"])

    op.create_table(
        "forward_estimates",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("fiscal_period", sa.String(8), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("calendar_year", sa.Integer(), nullable=True),
        sa.Column("consensus", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("analyst_count", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )
    op.create_index("ix_fwd_est_symbol_metric", "forward_estimates", ["symbol", "metric"])

    op.create_table(
        "regulatory_events",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("jurisdiction", sa.String(64), nullable=True),
        sa.Column("agency", sa.String(120), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("docket_number", sa.String(64), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), server_default="USD"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("published_ts", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
    )
    op.create_index("ix_reg_event_issuer_action", "regulatory_events", ["issuer_id", "action"])

    op.create_table(
        "esg_events",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("pillar", sa.String(4), nullable=True),
        sa.Column("sub_score", sa.Float(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("controversy_level", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("published_ts", sa.DateTime(), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
    )

    # -----------------------------------------------------------------
    # Ownership
    # -----------------------------------------------------------------
    op.create_table(
        "insider_transactions",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("company_cik", sa.String(16), nullable=True),
        sa.Column("filing_date", sa.DateTime(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("owner_cik", sa.String(16), nullable=True),
        sa.Column("owner_name", sa.String(240), nullable=True),
        sa.Column("owner_title", sa.String(240), nullable=True),
        sa.Column("ownership_type", sa.String(32), nullable=True),
        sa.Column("transaction_type", sa.String(32), nullable=True),
        sa.Column("acquisition_or_disposition", sa.String(8), nullable=True),
        sa.Column("security_type", sa.String(32), nullable=True),
        sa.Column("securities_owned", sa.Float(), nullable=True),
        sa.Column("securities_transacted", sa.Float(), nullable=True),
        sa.Column("transaction_price", sa.Float(), nullable=True),
        sa.Column("filing_url", sa.String(1024), nullable=True),
        sa.Column("source_filing_accession", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )
    op.create_index("ix_insider_symbol_date", "insider_transactions", ["symbol", "transaction_date"])

    op.create_table(
        "institutional_holdings",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("filer_cik", sa.String(16), nullable=True),
        sa.Column("filer_name", sa.String(240), nullable=True),
        sa.Column("shares_held", sa.Float(), nullable=True),
        sa.Column("market_value", sa.Float(), nullable=True),
        sa.Column("percent_of_portfolio", sa.Float(), nullable=True),
        sa.Column("change_shares", sa.Float(), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("ownership_type", sa.String(32), nullable=True),
        sa.Column("investor_classification", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "form_13f_holdings",
        _uuid_pk(),
        sa.Column("filer_cik", sa.String(16), nullable=False),
        sa.Column("filer_name", sa.String(240), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("accession_no", sa.String(32), nullable=False),
        sa.Column("cusip", sa.String(16), nullable=True),
        sa.Column("issuer_name", sa.String(240), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("class_title", sa.String(64), nullable=True),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("value_usd", sa.Float(), nullable=True),
        sa.Column("put_call", sa.String(8), nullable=True),
        sa.Column("investment_discretion", sa.String(32), nullable=True),
        sa.Column("voting_authority_sole", sa.Float(), nullable=True),
        sa.Column("voting_authority_shared", sa.Float(), nullable=True),
        sa.Column("voting_authority_none", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(64), server_default="SEC"),
        *_audit_cols(),
    )
    op.create_index("ix_13f_filer_report", "form_13f_holdings", ["filer_cik", "report_date"])
    op.create_index("ix_13f_cusip_report", "form_13f_holdings", ["cusip", "report_date"])

    op.create_table(
        "short_interest_snapshots",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("short_interest_shares", sa.Float(), nullable=True),
        sa.Column("average_daily_volume", sa.Float(), nullable=True),
        sa.Column("days_to_cover", sa.Float(), nullable=True),
        sa.Column("short_percent_float", sa.Float(), nullable=True),
        sa.Column("short_percent_outstanding", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("symbol", "settlement_date", name="uq_short_interest"),
    )

    op.create_table(
        "shares_float_snapshots",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("shares_outstanding", sa.Float(), nullable=True),
        sa.Column("float_shares", sa.Float(), nullable=True),
        sa.Column("restricted_shares", sa.Float(), nullable=True),
        sa.Column("percent_insiders", sa.Float(), nullable=True),
        sa.Column("percent_institutions", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "politician_trades",
        _uuid_pk(),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("representative", sa.String(240), nullable=False),
        sa.Column("chamber", sa.String(16), nullable=True),
        sa.Column("party", sa.String(16), nullable=True),
        sa.Column("district", sa.String(16), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("disclosure_date", sa.Date(), nullable=True),
        sa.Column("transaction_type", sa.String(32), nullable=True),
        sa.Column("amount_low", sa.Float(), nullable=True),
        sa.Column("amount_high", sa.Float(), nullable=True),
        sa.Column("ownership", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("source_url", sa.String(1024), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "fund_holdings",
        _uuid_pk(),
        sa.Column("fund_issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("fund_symbol", sa.String(64), nullable=True),
        sa.Column("holding_issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("holding_symbol", sa.String(64), nullable=True),
        sa.Column("holding_cusip", sa.String(16), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("shares_held", sa.Float(), nullable=True),
        sa.Column("market_value", sa.Float(), nullable=True),
        sa.Column("sector", sa.String(120), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("asset_class", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
    )
    op.create_index("ix_fund_holdings_fund_date", "fund_holdings", ["fund_symbol", "as_of"])

    # -----------------------------------------------------------------
    # News
    # -----------------------------------------------------------------
    op.create_table(
        "news_items",
        _uuid_pk(),
        sa.Column("news_id", sa.String(120), nullable=True),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("publisher", sa.String(120), nullable=True),
        sa.Column("author", sa.String(240), nullable=True),
        sa.Column("language", sa.String(16), server_default="en"),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("image_url", sa.String(1024), nullable=True),
        sa.Column("published_ts", sa.DateTime(), nullable=True),
        sa.Column("collected_ts", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("tags", _json(), server_default="[]"),
        sa.Column("categories", _json(), server_default="[]"),
        sa.Column("event_type", sa.String(32), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("sentiment_label", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        sa.UniqueConstraint("news_id", name="uq_news_id"),
    )
    op.create_index("ix_news_pub_ts", "news_items", ["published_ts"])

    op.create_table(
        "news_item_entities",
        _uuid_pk(),
        sa.Column("news_item_id", sa.String(36), sa.ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_kind", sa.String(32), nullable=False, server_default="instrument"),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("issuer_id", sa.String(36), sa.ForeignKey("issuers.id"), nullable=True),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.UniqueConstraint("news_item_id", "entity_kind", "entity_id", name="uq_news_entity"),
    )
    op.create_index("ix_news_entity_symbol", "news_item_entities", ["symbol"])

    op.create_table(
        "news_sentiments",
        _uuid_pk(),
        sa.Column("news_item_id", sa.String(36), sa.ForeignKey("news_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("label", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("raw", _json(), server_default="{}"),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_news_sent_item_model", "news_sentiments", ["news_item_id", "model"])

    # -----------------------------------------------------------------
    # Macro / microstructure
    # -----------------------------------------------------------------
    op.create_table(
        "economic_series",
        _uuid_pk(),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("country_iso", sa.String(8), nullable=True),
        sa.Column("frequency", sa.String(32), nullable=True),
        sa.Column("frequency_short", sa.String(8), nullable=True),
        sa.Column("units", sa.String(120), nullable=True),
        sa.Column("units_short", sa.String(60), nullable=True),
        sa.Column("seasonal_adjustment", sa.String(16), nullable=True),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("release", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("popularity", sa.Integer(), nullable=True),
        sa.Column("observation_start", sa.Date(), nullable=True),
        sa.Column("observation_end", sa.Date(), nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        sa.UniqueConstraint("source", "series_id", name="uq_economic_series_source_id"),
    )

    op.create_table(
        "economic_observations",
        _uuid_pk(),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("prior", sa.Float(), nullable=True),
        sa.Column("revised", sa.Float(), nullable=True),
        sa.Column("vintage_date", sa.Date(), nullable=True),
        sa.Column("release_ts", sa.DateTime(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
        sa.UniqueConstraint("source", "series_id", "date", "vintage_date", name="uq_econ_obs"),
    )

    op.create_table(
        "cot_reports",
        _uuid_pk(),
        sa.Column("report_type", sa.String(24), nullable=True),
        sa.Column("commodity", sa.String(120), nullable=False),
        sa.Column("commodity_code", sa.String(32), nullable=True),
        sa.Column("market", sa.String(120), nullable=True),
        sa.Column("exchange", sa.String(32), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("open_interest", sa.Float(), nullable=True),
        sa.Column("noncommercial_long", sa.Float(), nullable=True),
        sa.Column("noncommercial_short", sa.Float(), nullable=True),
        sa.Column("noncommercial_spreading", sa.Float(), nullable=True),
        sa.Column("commercial_long", sa.Float(), nullable=True),
        sa.Column("commercial_short", sa.Float(), nullable=True),
        sa.Column("nonreportable_long", sa.Float(), nullable=True),
        sa.Column("nonreportable_short", sa.Float(), nullable=True),
        sa.Column("trader_count", sa.Integer(), nullable=True),
        sa.Column("concentration_4_long", sa.Float(), nullable=True),
        sa.Column("concentration_4_short", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), server_default="CFTC"),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
        sa.UniqueConstraint("commodity_code", "report_date", "report_type", name="uq_cot_commodity_date"),
    )

    op.create_table(
        "bls_series",
        _uuid_pk(),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("survey", sa.String(120), nullable=True),
        sa.Column("measure_data_type", sa.String(120), nullable=True),
        sa.Column("seasonal_adjustment", sa.String(16), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("units", sa.String(120), nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        sa.UniqueConstraint("series_id", name="uq_bls_series_id"),
    )

    op.create_table(
        "treasury_rates",
        _uuid_pk(),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("tenor", sa.String(8), nullable=False),
        sa.Column("nominal_rate", sa.Float(), nullable=True),
        sa.Column("real_rate", sa.Float(), nullable=True),
        sa.Column("is_constant_maturity", sa.Boolean(), server_default=sa.true()),
        sa.Column("source", sa.String(32), server_default="UST"),
        *_audit_cols(),
        sa.UniqueConstraint("date", "tenor", name="uq_treasury_rate"),
    )

    op.create_table(
        "yield_curves",
        _uuid_pk(),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("curve_name", sa.String(64), nullable=True),
        sa.Column("points", _json(), server_default="[]"),
        sa.Column("source", sa.String(32), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("date", "country", "curve_name", name="uq_yield_curve"),
    )

    op.create_table(
        "option_series",
        _uuid_pk(),
        sa.Column("underlying", sa.String(64), nullable=False),
        sa.Column("underlying_instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("contract_count", sa.Integer(), nullable=True),
        sa.Column("first_listed", sa.Date(), nullable=True),
        sa.Column("last_traded", sa.DateTime(), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        sa.UniqueConstraint("underlying", "expiry", name="uq_option_series"),
    )

    op.create_table(
        "option_chains_snapshots",
        _uuid_pk(),
        sa.Column("underlying", sa.String(64), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("snapshot_ts", sa.DateTime(), nullable=False),
        sa.Column("underlying_price", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("payload", _json(), server_default="[]"),
        *_audit_cols(),
    )
    op.create_index("ix_opt_chain_underlying_ts", "option_chains_snapshots", ["underlying", "snapshot_ts"])

    op.create_table(
        "futures_curves",
        _uuid_pk(),
        sa.Column("root_symbol", sa.String(32), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("open_interest", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        *_audit_cols(),
        sa.UniqueConstraint("root_symbol", "expiry", "snapshot_date", name="uq_futures_curve"),
    )

    op.create_table(
        "market_holidays",
        _uuid_pk(),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(240), nullable=True),
        sa.Column("is_half_day", sa.Boolean(), server_default=sa.false()),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("is_observed", sa.Boolean(), server_default=sa.true()),
        sa.Column("meta", _json(), server_default="{}"),
        sa.UniqueConstraint("exchange", "date", name="uq_market_holiday"),
    )

    op.create_table(
        "market_status_history",
        _uuid_pk(),
        sa.Column("exchange", sa.String(32), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(240), nullable=True),
        sa.Column("halt_code", sa.String(32), nullable=True),
        sa.Column("ts_event", sa.DateTime(), nullable=False),
        sa.Column("ts_init", sa.DateTime(), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
    )
    op.create_index("ix_mkt_status_exchange_ts", "market_status_history", ["exchange", "ts_event"])

    # -----------------------------------------------------------------
    # Taxonomy / tagging graph
    # -----------------------------------------------------------------
    op.create_table(
        "taxonomy_schemes",
        _uuid_pk(),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level_labels", _json(), server_default="[]"),
        sa.Column("is_user_defined", sa.Integer(), server_default="0"),
        *_audit_cols(),
        sa.UniqueConstraint("code", name="uq_taxonomy_scheme_code"),
    )

    op.create_table(
        "taxonomy_nodes",
        _uuid_pk(),
        sa.Column("scheme_id", sa.String(36), sa.ForeignKey("taxonomy_schemes.id"), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("taxonomy_nodes.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("label", sa.String(240), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("path", sa.String(1024), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
        sa.UniqueConstraint("scheme_id", "code", name="uq_tax_node_scheme_code"),
    )
    op.create_index("ix_tax_node_path", "taxonomy_nodes", ["path"])

    op.create_table(
        "entity_tags",
        _uuid_pk(),
        sa.Column("entity_kind", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("taxonomy_node_id", sa.String(36), sa.ForeignKey("taxonomy_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheme_code", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
        sa.UniqueConstraint(
            "entity_kind", "entity_id", "taxonomy_node_id",
            name="uq_entity_tag",
        ),
    )
    op.create_index("ix_tag_scheme", "entity_tags", ["scheme_code"])
    op.create_index("ix_tag_entity", "entity_tags", ["entity_kind", "entity_id"])

    op.create_table(
        "entity_crosswalk",
        _uuid_pk(),
        sa.Column("from_kind", sa.String(32), nullable=False),
        sa.Column("from_value", sa.String(240), nullable=False),
        sa.Column("to_kind", sa.String(32), nullable=False),
        sa.Column("to_value", sa.String(240), nullable=False),
        sa.Column("relationship", sa.String(32), nullable=False, server_default="equivalent"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("meta", _json(), server_default="{}"),
        *_audit_cols(),
        sa.UniqueConstraint(
            "from_kind", "from_value", "to_kind", "to_value", "relationship",
            name="uq_crosswalk",
        ),
    )

    # -----------------------------------------------------------------
    # Seed taxonomy schemes
    # -----------------------------------------------------------------
    _seed_taxonomy_schemes()

    # -----------------------------------------------------------------
    # Back-compat view: instruments_flat
    # -----------------------------------------------------------------
    try:
        op.execute(
            "CREATE OR REPLACE VIEW instruments_flat AS "
            "SELECT id, vt_symbol, ticker, exchange, asset_class, security_type, "
            "instrument_class, issuer_id, identifiers, sector, industry, region, "
            "currency, tags, meta, created_at, updated_at FROM instruments"
        )
    except Exception:
        # SQLite and some engines don't support CREATE OR REPLACE VIEW — drop + create.
        try:
            op.execute("DROP VIEW IF EXISTS instruments_flat")
            op.execute(
                "CREATE VIEW instruments_flat AS "
                "SELECT id, vt_symbol, ticker, exchange, asset_class, security_type, "
                "instrument_class, issuer_id, identifiers, sector, industry, region, "
                "currency, tags, meta, created_at, updated_at FROM instruments"
            )
        except Exception:
            # Last resort: skip the view (still functional DB).
            pass


def _seed_taxonomy_schemes() -> None:
    """Insert canonical scheme rows for SIC / NAICS / GICS / TRBC / ICB / BICS / NACE."""
    scheme_table = sa.sql.table(
        "taxonomy_schemes",
        sa.sql.column("id", sa.String),
        sa.sql.column("code", sa.String),
        sa.sql.column("name", sa.String),
        sa.sql.column("description", sa.Text),
        sa.sql.column("level_labels", sa.JSON),
        sa.sql.column("is_user_defined", sa.Integer),
        sa.sql.column("created_at", sa.DateTime),
    )

    import uuid
    from datetime import datetime

    def row(code: str, name: str, description: str, level_labels: list[str]) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "code": code,
            "name": name,
            "description": description,
            "level_labels": level_labels,
            "is_user_defined": 0,
            "created_at": datetime.utcnow(),
        }

    op.bulk_insert(
        scheme_table,
        [
            row(
                "sic",
                "Standard Industrial Classification",
                "US SEC SIC 4-digit hierarchy.",
                ["division", "major_group", "industry_group", "industry"],
            ),
            row(
                "naics",
                "North American Industry Classification System",
                "NAICS 2-6 digit taxonomy used by US/Canada/Mexico.",
                ["sector", "subsector", "industry_group", "industry", "national_industry"],
            ),
            row(
                "gics",
                "Global Industry Classification Standard",
                "MSCI/S&P 4-level GICS taxonomy.",
                ["sector", "industry_group", "industry", "sub_industry"],
            ),
            row(
                "trbc",
                "Refinitiv Business Classification",
                "Refinitiv 4-level taxonomy.",
                ["economic_sector", "business_sector", "industry_group", "industry"],
            ),
            row(
                "icb",
                "Industry Classification Benchmark",
                "FTSE Russell ICB 4-level taxonomy.",
                ["industry", "supersector", "sector", "subsector"],
            ),
            row(
                "bics",
                "Bloomberg Industry Classification System",
                "Bloomberg 5-level BICS taxonomy.",
                ["sector", "industry_group", "industry", "sub_industry", "sub_sub_industry"],
            ),
            row(
                "nace",
                "Statistical Classification of Economic Activities (EU)",
                "EU NACE Rev. 2 taxonomy.",
                ["section", "division", "group", "class"],
            ),
            row(
                "thematic",
                "Thematic tags",
                "User-defined thematic tags (e.g. ai, defense, reshoring, energy_transition).",
                ["theme"],
            ),
            row(
                "region",
                "Regional tags",
                "Regional / country-group tags (e.g. apac, eu27, emea, latam).",
                ["region"],
            ),
            row(
                "risk",
                "Risk tags",
                "Risk/style tags (e.g. carbon_heavy, supply_chain_risk, cyber_exposed).",
                ["category", "tag"],
            ),
        ],
    )


def downgrade() -> None:
    """Best-effort reverse migration.

    We drop everything in roughly reverse-dependency order. Some engines
    won't auto-drop views via ``op.execute``; ignore errors there.
    """
    try:
        op.execute("DROP VIEW IF EXISTS instruments_flat")
    except Exception:
        pass

    # Taxonomy / crosswalk
    op.drop_table("entity_crosswalk")
    op.drop_table("entity_tags")
    op.drop_table("taxonomy_nodes")
    op.drop_table("taxonomy_schemes")

    # Microstructure / macro
    op.drop_table("market_status_history")
    op.drop_table("market_holidays")
    op.drop_table("futures_curves")
    op.drop_table("option_chains_snapshots")
    op.drop_table("option_series")
    op.drop_table("yield_curves")
    op.drop_table("treasury_rates")
    op.drop_table("bls_series")
    op.drop_table("cot_reports")
    op.drop_table("economic_observations")
    op.drop_table("economic_series")

    # News
    op.drop_table("news_sentiments")
    op.drop_table("news_item_entities")
    op.drop_table("news_items")

    # Ownership
    op.drop_table("fund_holdings")
    op.drop_table("politician_trades")
    op.drop_table("shares_float_snapshots")
    op.drop_table("short_interest_snapshots")
    op.drop_table("form_13f_holdings")
    op.drop_table("institutional_holdings")
    op.drop_table("insider_transactions")

    # Events
    op.drop_table("esg_events")
    op.drop_table("regulatory_events")
    op.drop_table("forward_estimates")
    op.drop_table("price_targets")
    op.drop_table("analyst_estimates")
    op.drop_table("calendar_events")
    op.drop_table("merger_events")
    op.drop_table("ipo_events")
    op.drop_table("split_events")
    op.drop_table("dividend_events")
    op.drop_table("earnings_events")
    op.drop_table("corporate_events")

    # Fundamentals
    op.drop_table("reported_financials")
    op.drop_table("management_discussion_analyses")
    op.drop_table("earnings_call_transcripts")
    op.drop_table("revenue_breakdowns")
    op.drop_table("historical_market_cap")
    op.drop_table("key_metrics")
    op.drop_table("financial_ratios")
    op.drop_table("financial_statements")

    # Instrument subclass tables
    op.drop_table("instrument_tokenized_asset")
    op.drop_table("instrument_betting")
    op.drop_table("instrument_synthetic")
    op.drop_table("instrument_commodity")
    op.drop_table("instrument_cfd")
    op.drop_table("instrument_crypto")
    op.drop_table("instrument_fx_pair")
    op.drop_table("instrument_option")
    op.drop_table("instrument_future")
    op.drop_table("instrument_bond")
    op.drop_table("instrument_index")
    op.drop_table("instrument_etf")
    op.drop_table("instrument_equity")

    # Entity graph
    op.drop_table("executive_compensation")
    op.drop_table("key_executives")
    op.drop_table("locations")
    op.drop_table("entity_relationships")
    op.drop_table("industry_classifications")
    op.drop_table("industries")
    op.drop_table("sectors")
    op.drop_table("fund_issuers")
    op.drop_table("government_entities")
    op.drop_table("issuers")

    # Instruments — reverse column additions (best-effort; some dialects
    # don't allow dropping all of these cleanly in a single transaction).
    for col in (
        "is_active",
        "size_precision",
        "price_precision",
        "lot_size",
        "max_quantity",
        "min_quantity",
        "multiplier",
        "tick_size",
        "issuer_id",
        "instrument_class",
    ):
        try:
            op.drop_column("instruments", col)
        except Exception:
            pass
