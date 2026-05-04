"""Walk-forward harness on top of vbt-pro's :class:`Splitter`.

This is the **per-window** integration path: agents and Python ML models
that cannot run inside Numba get to participate in the backtest because
the simulation is sliced into train/test windows and the AQP code drives
each window in pure Python via ``Splitter.apply``.

Two concrete harnesses ship:

- :class:`WalkForwardHarness` — generic over any AQP strategy (alpha or
  full :class:`IStrategy`). For each test window it instantiates the
  strategy fresh (so per-window agent / ML state is isolated), runs a
  vbt-pro signal-mode backtest on the test slice, and stitches the
  resulting equity curves end-to-end.
- :class:`PurgedWalkForwardHarness` — same but uses
  ``PurgedWalkForwardCV`` so labels that bleed across the train/test
  boundary are dropped (Lopez de Prado purging + embargo).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from aqp.backtest.engine import BacktestResult
from aqp.backtest.metrics import summarise
from aqp.backtest.vbtpro.engine import VectorbtProEngine
from aqp.backtest.vectorbt_backend import import_vectorbtpro
from aqp.core.registry import build_from_config

logger = logging.getLogger(__name__)


@dataclass
class WindowResult:
    """Result for a single WFO window."""

    window_index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_summary: dict[str, Any] = field(default_factory=dict)
    test_summary: dict[str, Any] = field(default_factory=dict)
    test_equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


@dataclass
class WalkForwardResult:
    """Aggregate result of a walk-forward harness run."""

    windows: list[WindowResult]
    stitched_equity: pd.Series
    summary: dict[str, Any]
    test_trades: pd.DataFrame = field(default_factory=pd.DataFrame)
    test_orders: pd.DataFrame = field(default_factory=pd.DataFrame)


class WalkForwardHarness:
    """Walk-forward optimiser that lets Python (agents / ML) run per window.

    The harness:

    1. Takes a ``strategy_cfg`` dict (the standard ``class`` /
       ``module_path`` / ``kwargs`` factory recipe) so it can re-instantiate
       a fresh strategy per window — important when the strategy carries
       per-window agent state, ML model weights, or any in-flight cache.
    2. Builds an OSS / vbt-pro :class:`Splitter` over the bars frame.
    3. Calls :meth:`Splitter.apply` with a Python ``apply_func`` that
       routes the train/test slice through :meth:`_run_window`.
    4. Returns a :class:`WalkForwardResult` with per-window summaries and a
       stitched equity curve so :func:`aqp.backtest.metrics.summarise`
       sees one continuous out-of-sample run.

    Parameters
    ----------
    strategy_cfg:
        Build-spec for the strategy. Re-instantiated per window.
    splitter:
        ``"rolling"`` (default), ``"expanding"``, or ``"purged"``. A custom
        ``Splitter`` instance can also be passed.
    n_splits:
        Number of rolling windows.
    train_size, test_size:
        Length of train / test windows (passed through to the splitter).
    embargo:
        Optional embargo (only honoured by ``purged``).
    engine_kwargs:
        Forwarded to :class:`VectorbtProEngine` for the per-window run.
    on_window_train:
        Optional Python hook called before the test backtest with
        ``(window_index, train_slice, fresh_strategy, context)``. This is
        where agent prompts get rebuilt or ML models fit.
    """

    def __init__(
        self,
        strategy_cfg: dict[str, Any],
        *,
        splitter: str | Any = "rolling",
        n_splits: int = 5,
        train_size: int | str | None = None,
        test_size: int | str | None = None,
        embargo: int | None = None,
        engine_kwargs: dict[str, Any] | None = None,
        on_window_train: Callable[[int, pd.DataFrame, Any, dict[str, Any]], None] | None = None,
    ) -> None:
        self.strategy_cfg = strategy_cfg
        self.splitter = splitter
        self.n_splits = int(n_splits)
        self.train_size = train_size
        self.test_size = test_size
        self.embargo = embargo
        self.engine_kwargs = dict(engine_kwargs or {})
        self.on_window_train = on_window_train

    def _build_splitter(self, index: pd.DatetimeIndex) -> Any:
        if not isinstance(self.splitter, str):
            return self.splitter

        vbt = import_vectorbtpro().module
        SplitterCls = vbt.Splitter

        kind = self.splitter.lower()
        if kind == "rolling":
            kwargs: dict[str, Any] = {"n": self.n_splits}
            if self.train_size is not None and self.test_size is not None:
                # vbt-pro's `from_n_rolling` accepts integer/string lengths
                # via the ``length`` kwarg; falls back to ``from_rolling``
                # for explicit set lengths.
                length = self.train_size + self.test_size if isinstance(
                    self.train_size, int
                ) and isinstance(self.test_size, int) else None
                if length is not None:
                    kwargs["length"] = length
            return SplitterCls.from_n_rolling(
                index,
                split=(self.train_size, self.test_size)
                if self.train_size is not None and self.test_size is not None
                else 0.7,
                **kwargs,
            )
        if kind in ("expanding", "expand"):
            return SplitterCls.from_expanding(
                index,
                split=self.test_size or 0.2,
                n=self.n_splits,
            )
        if kind == "purged":
            from vectorbtpro.generic.splitting.purged import PurgedWalkForwardCV

            cv = PurgedWalkForwardCV(
                n_test_splits=self.n_splits,
                test_size=self.test_size,
                embargo_td=self.embargo,
            )
            return SplitterCls.from_sklearn(index, splitter=cv)
        raise ValueError(f"Unknown splitter kind: {self.splitter!r}")

    def _run_window(
        self,
        window_index: int,
        train_slice: pd.DataFrame,
        test_slice: pd.DataFrame,
    ) -> WindowResult:
        strategy = build_from_config(self.strategy_cfg)
        ctx: dict[str, Any] = {"window_index": window_index}
        if self.on_window_train is not None:
            try:
                self.on_window_train(window_index, train_slice, strategy, ctx)
            except Exception:  # pragma: no cover - hook errors are surfaced but non-fatal
                logger.exception("on_window_train hook failed for window %d", window_index)

        engine_kwargs = dict(self.engine_kwargs)
        engine_kwargs.setdefault("mode", "signals")
        engine = VectorbtProEngine(**engine_kwargs)

        train_summary: dict[str, Any] = {}
        if not train_slice.empty:
            try:
                train_result = engine.run(strategy, train_slice)
                train_summary = dict(train_result.summary)
            except Exception:
                logger.exception("WFO train backtest failed for window %d", window_index)

        # Always re-instantiate before the test pass so train state does not
        # leak. Hooks fired only on the train pass.
        strategy = build_from_config(self.strategy_cfg)
        test_result = engine.run(strategy, test_slice)

        test_ts = test_slice["timestamp"]
        return WindowResult(
            window_index=window_index,
            train_start=pd.Timestamp(train_slice["timestamp"].min()) if not train_slice.empty else pd.Timestamp("NaT"),
            train_end=pd.Timestamp(train_slice["timestamp"].max()) if not train_slice.empty else pd.Timestamp("NaT"),
            test_start=pd.Timestamp(test_ts.min()),
            test_end=pd.Timestamp(test_ts.max()),
            train_summary=train_summary,
            test_summary=dict(test_result.summary),
            test_equity=test_result.equity_curve,
        )

    def run(self, bars: pd.DataFrame) -> WalkForwardResult:
        if bars.empty:
            raise ValueError("WalkForwardHarness: bars frame is empty.")

        frame = bars.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame = frame.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)

        ts_index = pd.DatetimeIndex(sorted(frame["timestamp"].unique()))
        if len(ts_index) < (self.n_splits + 1):
            raise ValueError(
                f"WalkForwardHarness: need at least {self.n_splits + 1} unique "
                f"timestamps, got {len(ts_index)}"
            )

        splitter = self._build_splitter(ts_index)

        windows: list[WindowResult] = []
        n_splits = getattr(splitter, "n_splits", self.n_splits)
        for window_index in range(n_splits):
            train_idx, test_idx = _train_test_indices(splitter, window_index, ts_index)
            train_slice = frame[frame["timestamp"].isin(train_idx)].copy()
            test_slice = frame[frame["timestamp"].isin(test_idx)].copy()
            if test_slice.empty:
                logger.warning("WFO window %d: empty test slice — skipped", window_index)
                continue
            windows.append(self._run_window(window_index, train_slice, test_slice))

        stitched = _stitch_equity([w.test_equity for w in windows])
        summary = summarise(stitched, None)
        summary["engine"] = "vectorbt-pro"
        summary["mode"] = "walk_forward"
        summary["n_windows"] = len(windows)
        summary["splitter"] = (
            self.splitter if isinstance(self.splitter, str) else type(self.splitter).__name__
        )

        return WalkForwardResult(
            windows=windows,
            stitched_equity=stitched,
            summary=summary,
        )

    def to_backtest_result(self, wfo: WalkForwardResult) -> BacktestResult:
        """Coerce a :class:`WalkForwardResult` into a :class:`BacktestResult`."""
        first_ts = wfo.stitched_equity.index[0] if len(wfo.stitched_equity) else None
        last_ts = wfo.stitched_equity.index[-1] if len(wfo.stitched_equity) else None
        return BacktestResult(
            equity_curve=wfo.stitched_equity,
            trades=wfo.test_trades,
            orders=wfo.test_orders,
            signals=pd.DataFrame(),
            tickets=[],
            summary=wfo.summary,
            start=first_ts.to_pydatetime() if first_ts is not None else None,
            end=last_ts.to_pydatetime() if last_ts is not None else None,
            initial_cash=float(self.engine_kwargs.get("initial_cash", 100000.0)),
            final_equity=(
                float(wfo.stitched_equity.iloc[-1]) if len(wfo.stitched_equity) else 0.0
            ),
        )


class PurgedWalkForwardHarness(WalkForwardHarness):
    """Convenience subclass that defaults to ``splitter="purged"``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("splitter", "purged")
        super().__init__(*args, **kwargs)


def _train_test_indices(
    splitter: Any,
    i: int,
    index: pd.DatetimeIndex,
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    """Pull the train+test ``DatetimeIndex`` for split ``i`` from a vbt Splitter.

    Tolerant of multiple splitter shapes — vbt-pro v1 returns ``(train, test)``
    via ``select_indices``, while older versions iterate over ``(train, test)``
    tuples directly. We defensively handle both.
    """
    if hasattr(splitter, "select_indices"):
        try:
            sel = splitter.select_indices(i)
            train_pos, test_pos = sel[0], sel[1]
            return index[train_pos], index[test_pos]
        except Exception:
            pass
    if hasattr(splitter, "iter_split_arrays"):
        try:
            for j, (train_pos, test_pos) in enumerate(splitter.iter_split_arrays()):
                if j == i:
                    return index[train_pos], index[test_pos]
        except Exception:
            pass
    if hasattr(splitter, "splits_arr"):
        try:
            sets = splitter.splits_arr[i]
            return index[sets[0]], index[sets[1]]
        except Exception:
            pass
    raise RuntimeError(
        "Could not pull (train, test) indices from splitter — "
        "API may have changed; consider passing a custom splitter instance."
    )


def _stitch_equity(curves: list[pd.Series]) -> pd.Series:
    """Concatenate per-window equity curves into one stitched out-of-sample series.

    Each curve is rebased so the first point equals the previous curve's last
    point, eliminating the cosmetic step at window boundaries.
    """
    cleaned = [c for c in curves if c is not None and len(c) > 0]
    if not cleaned:
        return pd.Series(dtype=float, name="equity")
    pieces: list[pd.Series] = []
    base = float(cleaned[0].iloc[0])
    running = base
    for curve in cleaned:
        c = curve.copy()
        first = float(c.iloc[0])
        if first == 0:
            continue
        scale = running / first
        c = c * scale
        if pieces:
            c = c.iloc[1:]  # drop overlap with previous tail
        pieces.append(c)
        running = float(c.iloc[-1]) if len(c) else running
    out = pd.concat(pieces).sort_index()
    out.name = "equity"
    return out


__all__ = [
    "WalkForwardHarness",
    "PurgedWalkForwardHarness",
    "WalkForwardResult",
    "WindowResult",
]
