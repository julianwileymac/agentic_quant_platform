"""``ReplayRLDataPipeline`` — offline-RL pipeline reading from rl.trajectories.

Uses the DuckDB views over the Iceberg ``rl.trajectories`` /
``rl.equity_curves`` tables (created by
:mod:`aqp.rl.trajectories.duckdb_views`) to feed offline / batch RL
algorithms with previously-observed (state, action, reward) tuples.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import pandas as pd

from aqp.rl.core.data import BaseDataPipeline

logger = logging.getLogger(__name__)


class ReplayRLDataPipeline(BaseDataPipeline):
    """Reads recorded trajectories for offline / batch RL training."""

    rl_alias: ClassVar[str] = "ReplayRLDataPipeline"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "replay"
    rl_tags: ClassVar[tuple[str, ...]] = ("offline", "iceberg", "duckdb")

    def __init__(
        self,
        *,
        run_id: str | None = None,
        episode: int | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.run_id = run_id
        self.episode = episode

    def download_data(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        time_interval: str = "1D",
    ) -> pd.DataFrame:
        """Return the recorded equity-curve frame as a DataFrame.

        ``ticker_list`` is ignored — the replay pipeline has no concept
        of universes (you replay a specific run / episode).
        """
        try:
            from aqp.rl.trajectories.duckdb_views import ensure_duckdb_views
            import duckdb
        except Exception:  # pragma: no cover
            return pd.DataFrame()
        conn = duckdb.connect(":memory:")
        views = ensure_duckdb_views(conn)
        if "equity_curves" not in views:
            return pd.DataFrame()
        view = views["equity_curves"]
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if self.run_id:
            clauses.append("run_id = $run_id")
            params["run_id"] = self.run_id
        if self.episode is not None:
            clauses.append("episode = $episode")
            params["episode"] = int(self.episode)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM {view}{where} ORDER BY episode, step"
        try:
            df = conn.execute(sql, params).fetch_df()
        except Exception:  # noqa: BLE001
            logger.exception("replay query failed")
            return pd.DataFrame()
        return df


__all__ = ["ReplayRLDataPipeline"]
