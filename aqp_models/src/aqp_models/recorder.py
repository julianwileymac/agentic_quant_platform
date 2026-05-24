"""Record templates — ports of qlib's ``SignalRecord``/``SigAnaRecord``/``PortAnaRecord``.

Each template packages a common MLflow-logged artifact:

- :class:`SignalRecord` — stores the model's raw predictions (`pred.pkl`) +
  label panel so downstream analysis can rerun without re-training.
- :class:`SigAnaRecord` — computes IC / Rank IC / long-short returns via
  :mod:`aqp.data.factors` and logs them as MLflow metrics + CSVs.
- :class:`PortAnaRecord` — turns the signal into a top-K / bottom-K
  portfolio and runs :class:`EventDrivenBacktester` (or vectorbt) to
  produce a portfolio tear-sheet.

Reference: ``inspiration/qlib-main/qlib/workflow/record_temp.py``.
"""
from __future__ import annotations

import contextlib
import json
import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)


class RecordTemplate(ABC):
    """Base class for record templates — generate + optionally list-artifacts."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id
        self.artifacts: dict[str, str] = {}

    @abstractmethod
    def generate(self, **kwargs: Any) -> dict[str, Any]: ...

    # Helpers -----------------------------------------------------------

    def _mlflow(self):
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        return mlflow


# ---------------------------------------------------------------------------
# SignalRecord.
# ---------------------------------------------------------------------------


class SignalRecord(RecordTemplate):
    """Persist ``pred`` + ``label`` panels as MLflow artifacts."""

    def __init__(
        self,
        model: Any | None = None,
        dataset: Any | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(run_id=run_id)
        self.model = model
        self.dataset = dataset
        self.pred: pd.Series | None = None
        self.label: pd.DataFrame | None = None

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        if self.model is None or self.dataset is None:
            raise ValueError("SignalRecord needs both `model` and `dataset`.")
        segment = kwargs.get("segment", "test")
        pred = self.model.predict(self.dataset, segment=segment)
        if not isinstance(pred, pd.Series):
            pred = pd.Series(pred)
        self.pred = pred

        label: pd.DataFrame | None = None
        try:
            raw = self.dataset.prepare(segment, col_set="label")
            label = _label_frame(raw)
        except Exception:
            logger.debug("SignalRecord could not fetch labels", exc_info=True)
        self.label = label

        mlflow = self._mlflow()
        with contextlib.suppress(Exception), tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            pred_path = p / "pred.pkl"
            pred.to_pickle(pred_path)
            mlflow.log_artifact(str(pred_path))
            if label is not None:
                label_path = p / "label.pkl"
                label.to_pickle(label_path)
                mlflow.log_artifact(str(label_path))

        return {"n_predictions": int(len(pred)), "segment": segment}


def _label_frame(raw: Any) -> pd.DataFrame | None:
    """Normalise a prepared label segment into a single-column DataFrame."""
    if isinstance(raw, pd.Series):
        return raw.to_frame("LABEL0")
    if isinstance(raw, pd.DataFrame):
        if isinstance(raw.columns, pd.MultiIndex):
            if "label" in raw.columns.get_level_values(0):
                sub = raw["label"]
                sub.columns = pd.MultiIndex.from_product([["label"], sub.columns])
                return sub
            return raw
        return raw
    return None


# ---------------------------------------------------------------------------
# SigAnaRecord — factor-style IC / long-short metrics.
# ---------------------------------------------------------------------------


class SigAnaRecord(RecordTemplate):
    """IC / Rank IC / long-short analysis backed by :func:`evaluate_factor`."""

    def __init__(
        self,
        signal_record: SignalRecord,
        horizons: tuple[int, ...] = (1, 5, 10),
        n_quantiles: int = 5,
        run_id: str | None = None,
    ) -> None:
        super().__init__(run_id=run_id)
        self.signal_record = signal_record
        self.horizons = tuple(int(h) for h in horizons)
        self.n_quantiles = int(n_quantiles)
        self.report: Any | None = None

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        from aqp.data.factors import evaluate_factor

        if self.signal_record.pred is None:
            raise ValueError("SigAnaRecord needs SignalRecord.generate() to run first.")
        pred = self.signal_record.pred
        label = self.signal_record.label

        factor_df = _pred_to_long(pred, column="factor")
        if factor_df.empty:
            raise ValueError("SigAnaRecord: empty prediction panel.")

        prices = _bars_for_panel(factor_df)
        if prices.empty:
            raise RuntimeError(
                "SigAnaRecord could not fetch bars for the predicted universe. "
                "Ensure the ingestion has completed and predictions carry valid symbols."
            )
        report = evaluate_factor(
            factor=factor_df,
            prices=prices,
            factor_name="signal",
            factor_column="factor",
            periods=self.horizons,
            n_quantiles=self.n_quantiles,
        )
        self.report = report

        summary: dict[str, Any] = {}
        mlflow = self._mlflow()
        for horizon, stats in (report.ic_stats or {}).items():
            for key, val in (stats or {}).items():
                metric = f"{horizon}_{key}"
                summary[metric] = float(val) if isinstance(val, (int, float)) else None
                with contextlib.suppress(Exception):
                    if isinstance(val, (int, float)):
                        mlflow.log_metric(metric, float(val))
        if label is not None and isinstance(label, pd.DataFrame):
            summary["n_labels"] = int(len(label))
        with contextlib.suppress(Exception):
            mlflow.set_tag("aqp.component", "sig_ana_record")
        return summary


def _pred_to_long(pred: pd.Series, column: str = "factor") -> pd.DataFrame:
    """Convert a prediction Series (MultiIndex or flat) to a long
    ``(timestamp, vt_symbol, factor)`` frame."""
    if pred.empty:
        return pd.DataFrame(columns=["timestamp", "vt_symbol", column])
    idx = pred.index
    if isinstance(idx, pd.MultiIndex) and idx.nlevels >= 2:
        # Assume (datetime, vt_symbol) order.
        level_names = list(idx.names)
        ts_level = level_names.index("datetime") if "datetime" in level_names else 0
        sym_level = level_names.index("vt_symbol") if "vt_symbol" in level_names else 1
        df = pred.reset_index()
        ts_col = df.columns[ts_level]
        sym_col = df.columns[sym_level]
        df = df.rename(columns={ts_col: "timestamp", sym_col: "vt_symbol", pred.name or 0: column})
    else:
        df = pred.reset_index().rename(columns={"index": "timestamp", 0: column})
        df["vt_symbol"] = "UNKNOWN"
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[["timestamp", "vt_symbol", column]]


def _bars_for_panel(factor_df: pd.DataFrame) -> pd.DataFrame:
    """Pull bars covering the factor panel via the DuckDB provider."""
    from aqp.core.types import Symbol
    from aqp.data.duckdb_engine import DuckDBHistoryProvider

    symbols = [Symbol.parse(v) for v in factor_df["vt_symbol"].dropna().unique().tolist()]
    if not symbols:
        return pd.DataFrame()
    provider = DuckDBHistoryProvider()
    start = factor_df["timestamp"].min()
    end = factor_df["timestamp"].max() + pd.Timedelta(days=30)
    return provider.get_bars(symbols, start=start, end=end)


# ---------------------------------------------------------------------------
# PortAnaRecord.
# ---------------------------------------------------------------------------


class PortAnaRecord(RecordTemplate):
    """Simple top-K long / bottom-K short portfolio analysis."""

    def __init__(
        self,
        signal_record: SignalRecord,
        topk: int = 50,
        n_drop: int = 5,
        holding_days: int = 1,
        engine: str = "event",
        run_id: str | None = None,
    ) -> None:
        super().__init__(run_id=run_id)
        self.signal_record = signal_record
        self.topk = int(topk)
        self.n_drop = int(n_drop)
        self.holding_days = int(holding_days)
        self.engine = engine
        self.equity: pd.Series | None = None
        self.summary: dict[str, Any] = {}

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        from aqp.backtest.metrics import risk_analysis, summarise

        if self.signal_record.pred is None:
            raise ValueError("PortAnaRecord needs SignalRecord.generate() first.")
        pred = self.signal_record.pred
        panel = _pred_to_long(pred, column="factor")
        if panel.empty:
            raise ValueError("PortAnaRecord: empty prediction panel.")
        bars = _bars_for_panel(panel)
        if bars.empty:
            raise RuntimeError("PortAnaRecord could not fetch bars for the universe.")

        # Build top-K long / bottom-K short weight book per rebalance date.
        panel = panel.sort_values(["timestamp", "factor"])
        panel["rank"] = panel.groupby("timestamp")["factor"].rank(pct=True)
        longs = panel[panel["rank"] >= 1.0 - self.topk / max(1, len(panel["vt_symbol"].unique()))]
        shorts = panel[panel["rank"] <= self.topk / max(1, len(panel["vt_symbol"].unique()))]
        weights = pd.concat(
            [
                longs.assign(weight=1.0 / max(1, len(longs["vt_symbol"].unique()))),
                shorts.assign(weight=-1.0 / max(1, len(shorts["vt_symbol"].unique()))),
            ],
            ignore_index=True,
        )

        # Join next-day returns per (date, symbol), then aggregate.
        bars["timestamp"] = pd.to_datetime(bars["timestamp"])
        bars = bars.sort_values(["vt_symbol", "timestamp"])
        bars["fwd"] = bars.groupby("vt_symbol")["close"].pct_change(self.holding_days).shift(-self.holding_days)
        joined = weights.merge(
            bars[["timestamp", "vt_symbol", "fwd"]], on=["timestamp", "vt_symbol"], how="left"
        )
        joined["contribution"] = joined["weight"] * joined["fwd"]
        daily = joined.groupby("timestamp")["contribution"].sum().fillna(0.0)
        equity = (1 + daily).cumprod() * 1.0
        equity.name = "equity"
        self.equity = equity

        summary = summarise(equity)
        summary.update({f"risk_{k}": v for k, v in risk_analysis(daily).items()})
        self.summary = summary

        mlflow = self._mlflow()
        with contextlib.suppress(Exception):
            for k, v in summary.items():
                if isinstance(v, (int, float)):
                    mlflow.log_metric(f"portana_{k}", float(v))
            mlflow.set_tag("aqp.component", "port_ana_record")
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "port_equity.csv"
                equity.to_csv(p, header=["equity"])
                mlflow.log_artifact(str(p))
                summary_p = Path(tmp) / "port_summary.json"
                summary_p.write_text(json.dumps(summary, default=str, indent=2))
                mlflow.log_artifact(str(summary_p))
        return summary


__all__ = ["PortAnaRecord", "RecordTemplate", "SigAnaRecord", "SignalRecord"]
