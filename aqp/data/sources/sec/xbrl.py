"""Utility helpers that coerce edgartools output into tidy DataFrames.

edgartools exposes very different shapes depending on form type — our
job is to normalise the common subset (balance sheet, income statement,
cash flow, insider transactions, 13F holdings) into long tidy frames
we can write to the parquet lake.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _as_dataframe(obj: Any) -> pd.DataFrame:
    """Coerce an edgartools object into a :class:`pandas.DataFrame`.

    edgartools typically offers ``.to_pandas()`` or exposes ``.df`` — we
    try both and fall back to ``pd.DataFrame(obj)`` as a last resort.
    """
    if obj is None:
        return pd.DataFrame()
    if isinstance(obj, pd.DataFrame):
        return obj.copy()
    for attr in ("to_pandas", "to_dataframe"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                result = fn()
                if isinstance(result, pd.DataFrame):
                    return result
            except Exception:
                logger.debug("%s() failed", attr, exc_info=True)
    for attr in ("df", "dataframe"):
        val = getattr(obj, attr, None)
        if isinstance(val, pd.DataFrame):
            return val.copy()
    try:
        return pd.DataFrame(obj)
    except Exception:
        logger.debug("could not coerce %s to DataFrame", type(obj).__name__, exc_info=True)
        return pd.DataFrame()


def standardize_financials(financials: Any, *, statement: str) -> pd.DataFrame:
    """Turn a ``Financials.{balance_sheet,income_statement,cash_flow}()``
    object into a long tidy frame of ``(concept, period, value, unit)``.
    """
    try:
        getter = getattr(financials, statement)
        raw = getter() if callable(getter) else getter
    except Exception:
        logger.debug("standardize_financials: no %s on %s", statement, type(financials))
        return pd.DataFrame()
    df = _as_dataframe(raw)
    if df.empty:
        return df
    # If it's a wide period-keyed frame, melt into long form.
    if df.index.name is None and "concept" not in df.columns:
        df = df.reset_index().rename(columns={df.index.name or "index": "concept"})
    if "concept" not in df.columns:
        df.insert(0, "concept", [f"line_{i}" for i in range(len(df))])
    # Everything besides concept is a period → melt.
    id_vars = [c for c in df.columns if c == "concept"]
    value_vars = [c for c in df.columns if c != "concept"]
    if not value_vars:
        return df
    long_df = df.melt(id_vars=id_vars, value_vars=value_vars, var_name="period", value_name="value")
    long_df["statement"] = statement
    long_df["period"] = long_df["period"].astype(str)
    return long_df


def insider_transactions(form4_obj: Any) -> pd.DataFrame:
    """Return a tidy frame of insider transactions from a Form 4 object."""
    if form4_obj is None:
        return pd.DataFrame()
    for attr in ("transactions", "get_transactions", "transaction_table"):
        val = getattr(form4_obj, attr, None)
        df = _as_dataframe(val() if callable(val) else val)
        if not df.empty:
            return df
    return pd.DataFrame()


def fund_holdings(thirteenf_obj: Any) -> pd.DataFrame:
    """Return the ``holdings`` table from a 13F/N-PORT object."""
    if thirteenf_obj is None:
        return pd.DataFrame()
    for attr in ("holdings", "positions", "get_holdings"):
        val = getattr(thirteenf_obj, attr, None)
        df = _as_dataframe(val() if callable(val) else val)
        if not df.empty:
            return df
    return pd.DataFrame()
