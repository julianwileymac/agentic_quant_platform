"""SEC adapter tests — exercises the catalog/xbrl layer with stubs.

The real ``edgartools`` library is optional; these tests never call it.
We inject stub objects that mimic its quack-typed API surface.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from aqp.data.sources.sec.catalog import upsert_sec_filing
from aqp.data.sources.sec.xbrl import (
    fund_holdings,
    insider_transactions,
    standardize_financials,
)


class _StubFinancials:
    def balance_sheet(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "2024-Q1": [100.0, 50.0],
                "2023-Q1": [90.0, 45.0],
            },
            index=["Assets", "Liabilities"],
        )


class _StubForm4:
    @property
    def transactions(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"insider": "CEO", "shares": 1000, "price": 150.0},
                {"insider": "CFO", "shares": -500, "price": 148.0},
            ]
        )


class _Stub13F:
    @property
    def holdings(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"cusip": "037833100", "shares": 5_000_000},
                {"cusip": "594918104", "shares": 1_200_000},
            ]
        )


def test_standardize_financials_long_form():
    df = standardize_financials(_StubFinancials(), statement="balance_sheet")
    assert not df.empty
    assert {"concept", "period", "value", "statement"}.issubset(df.columns)
    # 2 concepts × 2 periods
    assert len(df) == 4


def test_insider_transactions_coerces_to_dataframe():
    df = insider_transactions(_StubForm4())
    assert not df.empty
    assert {"insider", "shares", "price"}.issubset(df.columns)


def test_fund_holdings_returns_holdings_df():
    df = fund_holdings(_Stub13F())
    assert not df.empty
    assert {"cusip", "shares"}.issubset(df.columns)


def test_upsert_sec_filing_inserts_and_updates(patched_db, sqlite_session_factory):
    accession = "0000320193-23-000106"
    row = upsert_sec_filing(
        {
            "cik": "0000320193",
            "accession_no": accession,
            "form": "10-K",
            "filed_at": datetime(2023, 11, 3),
            "period_of_report": datetime(2023, 9, 30),
            "primary_doc_url": "https://www.sec.gov/.../aapl-20230930.htm",
            "primary_doc_type": "htm",
            "xbrl_available": True,
            "items": [],
            "meta": {"ticker": "AAPL"},
        }
    )
    assert row is not None
    assert row.accession_no == accession

    # Idempotent re-upsert — update the items list.
    row2 = upsert_sec_filing(
        {
            "cik": "0000320193",
            "accession_no": accession,
            "form": "10-K",
            "filed_at": datetime(2023, 11, 3),
            "items": ["1A", "7"],
        }
    )
    assert row2 is not None
    assert row2.accession_no == accession
    from aqp.persistence.db import get_session
    from aqp.persistence.models import SecFiling
    from sqlalchemy import select

    with get_session() as session:
        rows = session.execute(select(SecFiling)).scalars().all()
        # Only one row total — the upsert replaced the fields on the existing row.
        assert len(rows) == 1
        assert rows[0].items == ["1A", "7"]
