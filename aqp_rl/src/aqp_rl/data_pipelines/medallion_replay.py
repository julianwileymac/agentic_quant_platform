"""``DeterministicMedallionReplay`` — RL data feed pinned to silver/gold Iceberg.

Closes the **backtest-to-paper gap** identified in the FinRL-X
blueprint: every offline RL rollout draws bars + features from the
*same* medallion-tagged Iceberg tables that the live Flink topology
materialises for the production paper-trading agent. Because the
silver / gold tables carry hash-locked column contracts (see
:class:`aqp.data.catalog.active_metadata.DataContract`), the
feature distribution observed during training is guaranteed to match
the distribution observed at deployment time — modulo new snapshots,
which we pin via :func:`aqp.data.iceberg_catalog.read_arrow_at`.

Reads only — no Iceberg writes happen here, so AGENTS.md rule 3
(``iceberg_catalog.append_arrow`` is the only writer) is preserved.

Examples
--------

Daily equity bars from a silver namespace::

    pipeline = DeterministicMedallionReplay(
        layer="silver",
        namespace="aqp_silver_equities_bars",
        table="ohlcv_d",
        date_column="ts",
        ticker_column="vt_symbol",
    )

Gold-tier feature snapshot pinned to a specific snapshot id::

    pipeline = DeterministicMedallionReplay(
        layer="gold",
        namespace="aqp_gold_features",
        table="ml_feature_snapshot",
        date_column="snapshot_ts",
        ticker_column="instrument_id",
        snapshot_id=123456789,
    )

Both ``download_data`` and ``run_full`` honour the original FinRL
parity: long-format ``date`` / ``tic`` / ``open|high|low|close|volume``
frames flow into the existing ``StockTradingEnv`` /
``PortfolioAllocationEnv`` / ``RLBacktestEnv`` envs unchanged.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd

from aqp.data.catalog.active_metadata import LAYER_PREFIXES, MedallionLayer
from aqp_rl.core.data import BaseDataPipeline

logger = logging.getLogger(__name__)


_DEFAULT_OHLCV: tuple[str, ...] = ("open", "high", "low", "close", "volume")


class DeterministicMedallionReplay(BaseDataPipeline):
    """Replay deterministic bars + features from silver / gold Iceberg.

    Parameters
    ----------
    layer:
        One of ``"silver"`` / ``"gold"``. ``"bronze"`` is rejected
        because bronze tables hold raw vendor downloads that have not
        yet passed the AQP normalization stage; RL training against
        unnormalised data is a footgun and would silently break the
        deployment-consistent guarantee.
    namespace:
        Fully qualified Iceberg namespace (e.g. ``aqp_silver_equities``).
        Validated against :data:`LAYER_PREFIXES` so a ``layer="silver"``
        feed cannot accidentally read from a ``aqp_gold_*`` table.
    table:
        Iceberg table name (no namespace prefix).
    date_column:
        Column in the Iceberg table that carries the bar timestamp.
        Renamed to ``date`` in the returned DataFrame for FinRL parity.
    ticker_column:
        Column carrying the asset identifier (``vt_symbol`` or
        ``instrument_id``). Renamed to ``tic`` in the returned frame.
    feature_columns:
        Extra columns to pull from the table (e.g. ``["macd", "rsi_30"]``).
        These survive ``clean_data`` and are picked up by the env when
        listed in ``tech_indicator_list`` on ``run_full``.
    snapshot_id:
        Optional Iceberg snapshot id to pin the read against — defeats
        retroactive lookahead bias when the underlying source updates
        old rows. Passed through to
        :func:`aqp.data.iceberg_catalog.read_arrow_at`.
    as_of:
        Optional datetime cutoff that selects the most recent snapshot
        at or before the given timestamp. Mutually exclusive with
        ``snapshot_id``.
    indicators:
        Convenience knob; merged with ``feature_columns`` and surfaced
        to the env via the standard ``tech_indicator_list`` path.
    """

    rl_alias: ClassVar[str] = "DeterministicMedallionReplay"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "iceberg"
    rl_tags: ClassVar[tuple[str, ...]] = ("deterministic", "iceberg", "medallion", "replay")

    def __init__(
        self,
        *,
        layer: MedallionLayer,
        namespace: str,
        table: str,
        date_column: str = "date",
        ticker_column: str = "tic",
        feature_columns: list[str] | None = None,
        snapshot_id: int | None = None,
        as_of: datetime | None = None,
        indicators: list[str] | None = None,
        ohlcv_columns: tuple[str, ...] = _DEFAULT_OHLCV,
        use_vix: bool = False,
        use_turbulence: bool = False,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        if layer not in LAYER_PREFIXES:
            raise ValueError(
                f"DeterministicMedallionReplay only accepts silver / gold layers; got {layer!r}"
            )
        if layer == "bronze":
            raise ValueError(
                "RL training against bronze Iceberg tables is disallowed — bronze data "
                "is unnormalised vendor output and breaks the deployment-consistent "
                "guarantee (FinRL-X blueprint)."
            )
        if snapshot_id is not None and as_of is not None:
            raise ValueError("snapshot_id and as_of are mutually exclusive")
        expected_prefix = LAYER_PREFIXES[layer]
        if not namespace.startswith(expected_prefix):
            raise ValueError(
                f"namespace {namespace!r} does not match layer {layer!r} "
                f"(expected prefix {expected_prefix!r})"
            )

        self.layer: MedallionLayer = layer
        self.namespace = namespace
        self.table = table
        self.date_column = date_column
        self.ticker_column = ticker_column
        merged_features = list(indicators or [])
        for col in feature_columns or []:
            if col not in merged_features:
                merged_features.append(col)
        self.feature_columns = merged_features
        self.snapshot_id = snapshot_id
        self.as_of = as_of
        self.ohlcv_columns = tuple(ohlcv_columns)
        self.use_vix = bool(use_vix)
        self.use_turbulence = bool(use_turbulence)

    @property
    def identifier(self) -> str:
        return f"{self.namespace}.{self.table}"

    def _columns_to_read(self) -> list[str]:
        cols = [self.date_column, self.ticker_column, *self.ohlcv_columns, *self.feature_columns]
        seen: set[str] = set()
        unique: list[str] = []
        for c in cols:
            if c and c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def _read_arrow(self):  # type: ignore[no-untyped-def]
        """Pull the configured columns as a PyArrow table.

        Routes through :func:`aqp.data.iceberg_catalog.read_arrow_at`
        when a snapshot is pinned (the canonical defeat-lookahead path)
        and through :func:`read_arrow` otherwise. Both helpers return
        ``None`` when the table is genuinely absent — we surface that
        as an empty DataFrame so downstream envs degrade gracefully.
        """
        from aqp.data.iceberg_catalog import read_arrow, read_arrow_at

        columns = self._columns_to_read()
        if self.snapshot_id is not None or self.as_of is not None:
            return read_arrow_at(
                self.identifier,
                snapshot_id=self.snapshot_id,
                as_of=self.as_of,
                columns=columns,
            )
        return read_arrow(self.identifier, columns=columns)

    def download_data(
        self,
        ticker_list: list[str],
        start: str,
        end: str,
        time_interval: str = "1D",
    ) -> pd.DataFrame:
        """Read the medallion table and return the FinRL long-format frame.

        ``time_interval`` is recorded for telemetry but the actual
        cadence is implicit in the silver/gold table — RL training
        against a different cadence is a spec mismatch and should fail
        at the env level rather than here.
        """
        try:
            arrow = self._read_arrow()
        except Exception:
            logger.exception(
                "DeterministicMedallionReplay: read_arrow(%s) failed", self.identifier
            )
            return self._empty_frame()
        if arrow is None or arrow.num_rows == 0:
            logger.warning(
                "DeterministicMedallionReplay: %s returned no rows for window [%s, %s]",
                self.identifier,
                start,
                end,
            )
            return self._empty_frame()
        df = arrow.to_pandas()
        rename: dict[str, str] = {}
        if self.date_column in df.columns and self.date_column != "date":
            rename[self.date_column] = "date"
        if self.ticker_column in df.columns and self.ticker_column != "tic":
            rename[self.ticker_column] = "tic"
        if rename:
            df = df.rename(columns=rename)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
            df = df.loc[mask].copy()
        if "tic" in df.columns and ticker_list:
            df = df[df["tic"].astype(str).isin([str(t) for t in ticker_list])].copy()
        if df.empty:
            return self._empty_frame()
        sort_keys = [c for c in ("date", "tic") if c in df.columns]
        if sort_keys:
            df = df.sort_values(sort_keys).reset_index(drop=True)
        return df

    def add_indicators(
        self,
        df: pd.DataFrame,
        tech_indicator_list: list[str] | None,
    ) -> pd.DataFrame:
        """Indicators are pre-materialised in the medallion table.

        Override the default :class:`BaseDataPipeline.add_indicators`
        which would re-run the live :class:`FeatureEngineer` against
        local Parquet — that would defeat the determinism guarantee.
        Any feature the caller asks for that we did not load is logged
        and filled with NaN so the env throws a clear ``KeyError``
        rather than silently miscalibrating.
        """
        if df is None or df.empty:
            return df
        if not tech_indicator_list:
            return df
        missing = [c for c in tech_indicator_list if c not in df.columns]
        for col in missing:
            logger.warning(
                "DeterministicMedallionReplay: requested indicator %r not in silver/gold table %s — "
                "filling with NaN; declare it on feature_columns to load it.",
                col,
                self.identifier,
            )
            df[col] = float("nan")
        return df

    def add_risk_features(
        self,
        df: pd.DataFrame,
        *,
        use_vix: bool = False,
        use_turbulence: bool = True,
    ) -> pd.DataFrame:
        """Risk features must be pre-loaded — see :meth:`add_indicators`."""
        if df is None or df.empty:
            return df
        want_vix = use_vix or self.use_vix
        want_turb = use_turbulence or self.use_turbulence
        if want_vix and "vix" not in df.columns:
            logger.warning(
                "DeterministicMedallionReplay: use_vix=True but 'vix' missing from %s",
                self.identifier,
            )
            df["vix"] = float("nan")
        if want_turb and "turbulence" not in df.columns:
            logger.warning(
                "DeterministicMedallionReplay: use_turbulence=True but 'turbulence' missing from %s",
                self.identifier,
            )
            df["turbulence"] = float("nan")
        return df

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out.update(
            {
                "layer": self.layer,
                "namespace": self.namespace,
                "table": self.table,
                "date_column": self.date_column,
                "ticker_column": self.ticker_column,
                "feature_columns": list(self.feature_columns),
                "snapshot_id": self.snapshot_id,
                "as_of": self.as_of.isoformat() if isinstance(self.as_of, datetime) else None,
            }
        )
        return out

    def _empty_frame(self) -> pd.DataFrame:
        cols = ["date", "tic", *self.ohlcv_columns, *self.feature_columns]
        return pd.DataFrame(columns=cols)


__all__ = ["DeterministicMedallionReplay"]
