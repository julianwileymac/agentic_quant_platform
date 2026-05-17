"""Extended instrument taxonomy: REIT / mutual fund / OTC derivative / ADR / GDR
plus the ``instrument_measures`` registry.

Revision ID: 0039_extended_instrument_taxonomy
Revises: 0038_polymorphic_resources
Create Date: 2026-05-16

Adds five new joined-table subclasses of :class:`aqp.persistence.models.Instrument`
and an ``instrument_measures`` registry table so agents can introspect which
metrics are available for an entity before generating ad-hoc queries.

The new subclasses lift previously string-typed shapes (REIT was an
``InstrumentEquity`` row with ``is_adr=False`` and a sector hint; ADR was an
``InstrumentEquity`` row with ``is_adr=True`` and no FK back to the underlying)
into first-class polymorphic rows with the columns the report mandates:

* ``instrument_reit`` — property portfolio, FFO, distribution yield, REIT class
* ``instrument_mutual_fund`` — expense ratio, NAV currency, minimum investment,
  fund family, share class
* ``instrument_otc_derivative`` — counterparty LEI, ISDA master agreement id,
  notional/settlement currency, instrument kind
* ``instrument_adr``  — ``underlying_entity_id`` FK back to the foreign
  equity, conversion ratio, depository bank, sponsorship level
* ``instrument_gdr`` — same shape, different polymorphic identity

``instrument_measures`` carries one row per ``(entity_id, measure_type,
frequency)`` tuple, with the source dataset and the ``dataset_field`` the
measure lands in. The active metadata registry already covers dataset-level
contracts (``data_owner``, ``semantic_definition``); ``instrument_measures``
makes a measure addressable from the agent surface so an LLM can answer
"what daily metrics exist for AAPL?" before drafting a query.

AGENTS.md rule 6: this migration is **immutable** once shipped.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0039_extended_instrument_taxonomy"
down_revision = "0038_polymorphic_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # instrument_reit
    # ---------------------------------------------------------------
    op.create_table(
        "instrument_reit",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issuer_cik", sa.String(length=16), nullable=True),
        sa.Column("isin", sa.String(length=16), nullable=True),
        sa.Column("cusip", sa.String(length=16), nullable=True),
        sa.Column("figi", sa.String(length=16), nullable=True),
        sa.Column("lei", sa.String(length=20), nullable=True),
        sa.Column("reit_class", sa.String(length=32), nullable=True),
        # equity | mortgage | hybrid | public_non_listed | private
        sa.Column("property_sector", sa.String(length=64), nullable=True),
        # residential | commercial | industrial | healthcare | data_center |
        # retail | hospitality | diversified | infrastructure | timber
        sa.Column("property_portfolio_json", sa.JSON(), nullable=True),
        sa.Column("distribution_yield", sa.Float(), nullable=True),
        sa.Column("ffo_per_share", sa.Float(), nullable=True),
        sa.Column("nav_per_share", sa.Float(), nullable=True),
        sa.Column("payout_ratio", sa.Float(), nullable=True),
        sa.Column("debt_to_equity", sa.Float(), nullable=True),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_instrument_reit_isin", "instrument_reit", ["isin"])
    op.create_index("ix_instrument_reit_cusip", "instrument_reit", ["cusip"])
    op.create_index("ix_instrument_reit_property_sector", "instrument_reit", ["property_sector"])

    # ---------------------------------------------------------------
    # instrument_mutual_fund
    # ---------------------------------------------------------------
    op.create_table(
        "instrument_mutual_fund",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issuer_fund_id", sa.String(length=36), nullable=True),
        sa.Column("fund_family", sa.String(length=120), nullable=True),
        sa.Column("share_class", sa.String(length=16), nullable=True),
        # A | B | C | I | R | Z | retail | institutional | inv | adv
        sa.Column("inception_date", sa.Date(), nullable=True),
        sa.Column("aum", sa.Float(), nullable=True),
        sa.Column("expense_ratio", sa.Float(), nullable=True),
        sa.Column("management_fee", sa.Float(), nullable=True),
        sa.Column("nav_currency", sa.String(length=16), nullable=True),
        sa.Column("minimum_investment", sa.Float(), nullable=True),
        sa.Column("minimum_subsequent_investment", sa.Float(), nullable=True),
        sa.Column("fund_kind", sa.String(length=32), nullable=True),
        # open_end | closed_end | money_market | target_date | ucits | sicav
        sa.Column("investment_strategy", sa.String(length=64), nullable=True),
        sa.Column("benchmark_index", sa.String(length=120), nullable=True),
        sa.Column("is_index_fund", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_actively_managed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("distribution_frequency", sa.String(length=24), nullable=True),
        # daily | monthly | quarterly | semi_annual | annual
        sa.Column("country", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_instrument_mutual_fund_family", "instrument_mutual_fund", ["fund_family"])
    op.create_index("ix_instrument_mutual_fund_kind", "instrument_mutual_fund", ["fund_kind"])
    op.create_index(
        "ix_instrument_mutual_fund_benchmark",
        "instrument_mutual_fund",
        ["benchmark_index"],
    )

    # ---------------------------------------------------------------
    # instrument_otc_derivative
    # ---------------------------------------------------------------
    op.create_table(
        "instrument_otc_derivative",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("instrument_kind", sa.String(length=32), nullable=False),
        # swap | swaption | cap_floor | forward | exotic | variance_swap |
        # credit_default_swap | total_return_swap | basket_swap
        sa.Column("counterparty_lei", sa.String(length=20), nullable=True),
        sa.Column("counterparty_name", sa.String(length=240), nullable=True),
        sa.Column("isda_master_agreement_id", sa.String(length=64), nullable=True),
        sa.Column("isda_schedule_version", sa.String(length=16), nullable=True),
        sa.Column("notional_currency", sa.String(length=16), nullable=True),
        sa.Column("notional_amount", sa.Float(), nullable=True),
        sa.Column("settlement_currency", sa.String(length=16), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("payment_frequency", sa.String(length=24), nullable=True),
        # monthly | quarterly | semi_annual | annual | bullet | irregular
        sa.Column("collateral_type", sa.String(length=32), nullable=True),
        # csa_full | csa_partial | uncollateralized | initial_margin
        sa.Column("cleared", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ccp_name", sa.String(length=120), nullable=True),
        sa.Column("legs_json", sa.JSON(), nullable=True),
        # list of {pay_receive, leg_type, currency, rate_type, rate_index, fixed_rate}
        sa.Column("payoff_formula", sa.Text(), nullable=True),
        # symbolic payoff expression for exotic / variance swap legs
        sa.ForeignKeyConstraint(["id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instrument_otc_derivative_kind",
        "instrument_otc_derivative",
        ["instrument_kind"],
    )
    op.create_index(
        "ix_instrument_otc_derivative_counterparty",
        "instrument_otc_derivative",
        ["counterparty_lei"],
    )
    op.create_index(
        "ix_instrument_otc_derivative_termination",
        "instrument_otc_derivative",
        ["termination_date"],
    )

    # ---------------------------------------------------------------
    # instrument_adr
    # ---------------------------------------------------------------
    op.create_table(
        "instrument_adr",
        sa.Column("id", sa.String(length=36), nullable=False),
        # FK back to the foreign equity row (an InstrumentEquity row living
        # in the underlying's home venue). NULL during onboarding when the
        # underlying hasn't been resolved yet.
        sa.Column("underlying_instrument_id", sa.String(length=36), nullable=True),
        sa.Column("underlying_ticker", sa.String(length=64), nullable=True),
        sa.Column("underlying_venue", sa.String(length=32), nullable=True),
        sa.Column("underlying_isin", sa.String(length=16), nullable=True),
        sa.Column("conversion_ratio", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        # Number of underlying foreign shares represented by one ADR
        sa.Column("depository_bank_name", sa.String(length=120), nullable=True),
        sa.Column("depository_bank_lei", sa.String(length=20), nullable=True),
        sa.Column("sponsorship_level", sa.String(length=16), nullable=True),
        # I | II | III | 144A | Reg_S | unsponsored
        sa.Column("listing_venue", sa.String(length=32), nullable=True),
        sa.Column("custodian_country", sa.String(length=64), nullable=True),
        sa.Column("home_country", sa.String(length=64), nullable=True),
        sa.Column("annual_dr_fee", sa.Float(), nullable=True),
        sa.Column("created_date", sa.Date(), nullable=True),
        # Equity-shared columns kept here so the ADR row stands alone.
        sa.Column("issuer_cik", sa.String(length=16), nullable=True),
        sa.Column("isin", sa.String(length=16), nullable=True),
        sa.Column("cusip", sa.String(length=16), nullable=True),
        sa.Column("figi", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(
            ["underlying_instrument_id"],
            ["instruments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instrument_adr_underlying_instrument_id",
        "instrument_adr",
        ["underlying_instrument_id"],
    )
    op.create_index("ix_instrument_adr_underlying_isin", "instrument_adr", ["underlying_isin"])
    op.create_index("ix_instrument_adr_isin", "instrument_adr", ["isin"])
    op.create_index(
        "ix_instrument_adr_sponsorship_level",
        "instrument_adr",
        ["sponsorship_level"],
    )

    # ---------------------------------------------------------------
    # instrument_gdr — identical shape to ADR, distinct polymorphic identity
    # ---------------------------------------------------------------
    op.create_table(
        "instrument_gdr",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("underlying_instrument_id", sa.String(length=36), nullable=True),
        sa.Column("underlying_ticker", sa.String(length=64), nullable=True),
        sa.Column("underlying_venue", sa.String(length=32), nullable=True),
        sa.Column("underlying_isin", sa.String(length=16), nullable=True),
        sa.Column("conversion_ratio", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("depository_bank_name", sa.String(length=120), nullable=True),
        sa.Column("depository_bank_lei", sa.String(length=20), nullable=True),
        sa.Column("listing_venue", sa.String(length=32), nullable=True),
        # LSE | LuxSE | Frankfurt | SIX | Singapore | Dubai
        sa.Column("regulatory_regime", sa.String(length=32), nullable=True),
        # Reg_S | Rule_144A | Reg_S_144A | full_listing
        sa.Column("custodian_country", sa.String(length=64), nullable=True),
        sa.Column("home_country", sa.String(length=64), nullable=True),
        sa.Column("annual_dr_fee", sa.Float(), nullable=True),
        sa.Column("created_date", sa.Date(), nullable=True),
        sa.Column("issuer_cik", sa.String(length=16), nullable=True),
        sa.Column("isin", sa.String(length=16), nullable=True),
        sa.Column("cusip", sa.String(length=16), nullable=True),
        sa.Column("figi", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["instruments.id"]),
        sa.ForeignKeyConstraint(
            ["underlying_instrument_id"],
            ["instruments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instrument_gdr_underlying_instrument_id",
        "instrument_gdr",
        ["underlying_instrument_id"],
    )
    op.create_index("ix_instrument_gdr_underlying_isin", "instrument_gdr", ["underlying_isin"])
    op.create_index("ix_instrument_gdr_isin", "instrument_gdr", ["isin"])
    op.create_index(
        "ix_instrument_gdr_regulatory_regime",
        "instrument_gdr",
        ["regulatory_regime"],
    )

    # ---------------------------------------------------------------
    # instrument_measures registry
    # ---------------------------------------------------------------
    op.create_table(
        "instrument_measures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("measure_type", sa.String(length=64), nullable=False),
        # price | volume | open_interest | implied_volatility | dividend_yield |
        # earnings_yield | book_value | ffo | nav | distribution | greek_delta |
        # greek_gamma | basis | spread | turnover | bid_ask_spread | ...
        sa.Column("frequency", sa.String(length=32), nullable=False),
        # tick | second | minute | hour | day | week | month | quarter | annual |
        # event_driven | adhoc
        sa.Column("dataset_field", sa.String(length=120), nullable=False),
        # Column / field name where the measure lands in the source dataset
        sa.Column("source_dataset_id", sa.String(length=36), nullable=True),
        # FK to dataset_catalogs.id (NULL for synthetic / computed measures)
        sa.Column("unit", sa.String(length=32), nullable=True),
        # USD | basis_points | percent | shares | contracts | abs | ratio
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("first_available", sa.DateTime(), nullable=True),
        sa.Column("last_available", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_dataset_id"],
            ["dataset_catalogs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "measure_type",
            "frequency",
            "dataset_field",
            name="uq_instrument_measures_address",
        ),
    )
    op.create_index(
        "ix_instrument_measures_instrument_id",
        "instrument_measures",
        ["instrument_id"],
    )
    op.create_index(
        "ix_instrument_measures_measure_type",
        "instrument_measures",
        ["measure_type"],
    )
    op.create_index(
        "ix_instrument_measures_frequency",
        "instrument_measures",
        ["frequency"],
    )
    op.create_index(
        "ix_instrument_measures_source_dataset_id",
        "instrument_measures",
        ["source_dataset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_instrument_measures_source_dataset_id", table_name="instrument_measures")
    op.drop_index("ix_instrument_measures_frequency", table_name="instrument_measures")
    op.drop_index("ix_instrument_measures_measure_type", table_name="instrument_measures")
    op.drop_index("ix_instrument_measures_instrument_id", table_name="instrument_measures")
    op.drop_table("instrument_measures")

    op.drop_index("ix_instrument_gdr_regulatory_regime", table_name="instrument_gdr")
    op.drop_index("ix_instrument_gdr_isin", table_name="instrument_gdr")
    op.drop_index("ix_instrument_gdr_underlying_isin", table_name="instrument_gdr")
    op.drop_index(
        "ix_instrument_gdr_underlying_instrument_id",
        table_name="instrument_gdr",
    )
    op.drop_table("instrument_gdr")

    op.drop_index("ix_instrument_adr_sponsorship_level", table_name="instrument_adr")
    op.drop_index("ix_instrument_adr_isin", table_name="instrument_adr")
    op.drop_index("ix_instrument_adr_underlying_isin", table_name="instrument_adr")
    op.drop_index(
        "ix_instrument_adr_underlying_instrument_id",
        table_name="instrument_adr",
    )
    op.drop_table("instrument_adr")

    op.drop_index(
        "ix_instrument_otc_derivative_termination",
        table_name="instrument_otc_derivative",
    )
    op.drop_index(
        "ix_instrument_otc_derivative_counterparty",
        table_name="instrument_otc_derivative",
    )
    op.drop_index(
        "ix_instrument_otc_derivative_kind",
        table_name="instrument_otc_derivative",
    )
    op.drop_table("instrument_otc_derivative")

    op.drop_index(
        "ix_instrument_mutual_fund_benchmark",
        table_name="instrument_mutual_fund",
    )
    op.drop_index("ix_instrument_mutual_fund_kind", table_name="instrument_mutual_fund")
    op.drop_index("ix_instrument_mutual_fund_family", table_name="instrument_mutual_fund")
    op.drop_table("instrument_mutual_fund")

    op.drop_index("ix_instrument_reit_property_sector", table_name="instrument_reit")
    op.drop_index("ix_instrument_reit_cusip", table_name="instrument_reit")
    op.drop_index("ix_instrument_reit_isin", table_name="instrument_reit")
    op.drop_table("instrument_reit")
