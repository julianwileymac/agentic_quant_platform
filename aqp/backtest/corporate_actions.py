"""In-replay corporate-action application.

The bars view is already split/dividend-adjusted at load time (via
``DuckDBHistoryProvider.get_bars_normalized``). This helper handles the
other case — applying a factor file *during* replay when the engine is
consuming a raw stream.
"""
from __future__ import annotations

import logging

import pandas as pd

from aqp.core.corporate_actions import FactorFile

logger = logging.getLogger(__name__)


def apply_actions_to_slice(
    slice_df: pd.DataFrame,
    factor_files: dict[str, FactorFile],
    mode: str = "adjusted",
) -> pd.DataFrame:
    """Apply per-symbol factor files to a single-timestamp slice frame."""
    if slice_df.empty or mode == "raw" or not factor_files:
        return slice_df
    out: list[pd.DataFrame] = []
    for vt_symbol, sub in slice_df.groupby("vt_symbol", sort=False):
        ff = factor_files.get(vt_symbol)
        if ff is None:
            out.append(sub)
            continue
        try:
            out.append(ff.adjust_bars(sub, mode=mode))
        except Exception:
            logger.exception("could not apply factor file for %s", vt_symbol)
            out.append(sub)
    return pd.concat(out, ignore_index=True)
