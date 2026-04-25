"""Feature / label handlers — native port of ``qlib.data.dataset.handler``.

A ``DataHandler`` owns the transformation from raw bars into a feature /
label panel keyed on ``(datetime, vt_symbol)``. Three data "keys" let
training code reach raw, learn-time, or inference-time views of the same
underlying panel, mirroring qlib's ``DataHandlerLP``:

- ``DK_R`` ("raw")      — raw features / labels before processing.
- ``DK_I`` ("infer")    — the view used at prediction time (no label drops).
- ``DK_L`` ("learn")    — the view used during fit (label NaN rows dropped, etc.).

Reference: ``inspiration/qlib-main/qlib/data/dataset/handler.py``.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from aqp.ml.base import Serializable
from aqp.ml.loader import DataLoader
from aqp.ml.processors import Processor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data-key constants (mirror qlib).
# ---------------------------------------------------------------------------

DK_R = "raw"
DK_I = "infer"
DK_L = "learn"

CS_ALL = "__all__"
CS_RAW = "__raw__"
CS_FEATURE = "feature"
CS_LABEL = "label"


# ---------------------------------------------------------------------------
# Abstract contract.
# ---------------------------------------------------------------------------


class DataHandlerABC(Serializable, ABC):
    """Root handler ABC — implementations must provide ``fetch``."""

    @abstractmethod
    def fetch(
        self,
        selector: Any = slice(None, None),
        level: str | int = "datetime",
        col_set: str | list[str] = CS_ALL,
        data_key: str = DK_I,
    ) -> pd.DataFrame:
        """Return a panel slice. ``col_set`` may be ``CS_ALL`` / ``CS_FEATURE``
        / ``CS_LABEL`` / a list of column names."""


# ---------------------------------------------------------------------------
# Concrete DataHandler — single-view (no learn/infer split).
# ---------------------------------------------------------------------------


class DataHandler(DataHandlerABC):
    """Handler that holds one flat feature/label panel.

    The panel index is ``(datetime, vt_symbol)`` and columns are
    ``MultiIndex((level0 ∈ {'feature','label'}, name))``.
    """

    # Columns that are always added after raw load.
    ADDITIONAL_COLS: tuple[str, ...] = ()
    CS_ALL = CS_ALL
    CS_RAW = CS_RAW

    def __init__(
        self,
        instruments: list[str] | None = None,
        start_time: str | pd.Timestamp | None = None,
        end_time: str | pd.Timestamp | None = None,
        data_loader: DataLoader | dict[str, Any] | None = None,
        fit_start_time: str | pd.Timestamp | None = None,
        fit_end_time: str | pd.Timestamp | None = None,
    ) -> None:
        self.instruments = list(instruments) if instruments else []
        self.start_time = pd.Timestamp(start_time) if start_time else None
        self.end_time = pd.Timestamp(end_time) if end_time else None
        self.fit_start_time = pd.Timestamp(fit_start_time) if fit_start_time else self.start_time
        self.fit_end_time = pd.Timestamp(fit_end_time) if fit_end_time else self.end_time
        self.data_loader = _maybe_build_loader(data_loader)
        self._data: pd.DataFrame | None = None

    # ---- setup ---------------------------------------------------------

    def setup_data(self, init_type: str = "all") -> pd.DataFrame:
        """Eager-load the panel (idempotent)."""
        if self._data is not None:
            return self._data
        if self.data_loader is None:
            raise RuntimeError("DataHandler has no data_loader; cannot setup.")
        df = self.data_loader.load(
            self.instruments,
            start_time=self.start_time,
            end_time=self.end_time,
        )
        self._data = _ensure_panel(df)
        return self._data

    # ---- fetching ------------------------------------------------------

    def fetch(
        self,
        selector: Any = slice(None, None),
        level: str | int = "datetime",
        col_set: str | list[str] = CS_ALL,
        data_key: str = DK_I,
    ) -> pd.DataFrame:
        panel = self.setup_data()
        sliced = _select_rows(panel, selector, level=level)
        return _select_cols(sliced, col_set)


# ---------------------------------------------------------------------------
# DataHandlerLP — holds raw / infer / learn views of the same panel.
# ---------------------------------------------------------------------------


class DataHandlerLP(DataHandler):
    """Learn-Infer-Raw data handler.

    ``infer_processors`` are applied before inference; ``learn_processors``
    are additionally applied during training. ``drop_raw`` discards the
    ``DK_R`` copy once the derived views are built (saves RAM).
    """

    DK_R = DK_R
    DK_I = DK_I
    DK_L = DK_L

    def __init__(
        self,
        instruments: list[str] | None = None,
        start_time: str | pd.Timestamp | None = None,
        end_time: str | pd.Timestamp | None = None,
        data_loader: DataLoader | dict[str, Any] | None = None,
        infer_processors: list[Processor] | list[dict[str, Any]] | None = None,
        learn_processors: list[Processor] | list[dict[str, Any]] | None = None,
        shared_processors: list[Processor] | list[dict[str, Any]] | None = None,
        process_type: str = "append",  # or "independent"
        drop_raw: bool = False,
        fit_start_time: str | pd.Timestamp | None = None,
        fit_end_time: str | pd.Timestamp | None = None,
    ) -> None:
        super().__init__(
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            data_loader=data_loader,
            fit_start_time=fit_start_time,
            fit_end_time=fit_end_time,
        )
        self.infer_processors = [_maybe_build_processor(p) for p in infer_processors or []]
        self.learn_processors = [_maybe_build_processor(p) for p in learn_processors or []]
        self.shared_processors = [_maybe_build_processor(p) for p in shared_processors or []]
        self.process_type = process_type
        self.drop_raw = drop_raw
        self._raw: pd.DataFrame | None = None
        self._infer: pd.DataFrame | None = None
        self._learn: pd.DataFrame | None = None

    def setup_data(self, init_type: str = "all") -> pd.DataFrame:
        if self._infer is not None:
            return self._infer
        raw = super().setup_data(init_type=init_type)
        self._raw = raw

        # Shared processors (run before per-view chains).
        shared = raw.copy()
        shared = _apply_processors(shared, self.shared_processors, fit_window=self._fit_window())

        infer = shared.copy()
        infer = _apply_processors(infer, self.infer_processors, fit_window=self._fit_window())
        self._infer = infer

        if self.process_type == "append":
            learn = infer.copy()
        else:
            learn = shared.copy()
        learn = _apply_processors(learn, self.learn_processors, fit_window=self._fit_window())
        self._learn = learn

        if self.drop_raw:
            self._raw = None
        return self._infer

    def _fit_window(self) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
        return self.fit_start_time, self.fit_end_time

    def fetch(
        self,
        selector: Any = slice(None, None),
        level: str | int = "datetime",
        col_set: str | list[str] = CS_ALL,
        data_key: str = DK_I,
        squeeze: bool = False,
        proc_func: Any | None = None,
    ) -> pd.DataFrame:
        self.setup_data()
        target = {DK_R: self._raw, DK_I: self._infer, DK_L: self._learn}.get(data_key, self._infer)
        if target is None:
            if data_key == DK_R and self.drop_raw:
                raise RuntimeError("drop_raw=True — DK_R view is unavailable.")
            raise RuntimeError(f"No cached view for data_key={data_key!r}.")
        sliced = _select_rows(target, selector, level=level)
        out = _select_cols(sliced, col_set)
        if proc_func is not None:
            out = proc_func(out)
        if squeeze and out.shape[1] == 1:
            return out.iloc[:, 0]
        return out


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------


def _maybe_build_loader(loader: DataLoader | dict[str, Any] | None) -> DataLoader | None:
    if loader is None:
        return None
    if isinstance(loader, DataLoader):
        return loader
    if isinstance(loader, dict) and "class" in loader:
        from aqp.core.registry import build_from_config

        built = build_from_config(loader)
        if not isinstance(built, DataLoader):
            raise TypeError(f"Expected DataLoader, got {type(built).__name__}")
        return built
    raise TypeError(f"Unsupported data_loader spec: {type(loader).__name__}")


def _maybe_build_processor(spec: Processor | dict[str, Any]) -> Processor:
    if isinstance(spec, Processor):
        return spec
    if isinstance(spec, dict) and "class" in spec:
        from aqp.core.registry import build_from_config

        built = build_from_config(spec)
        if not isinstance(built, Processor):
            raise TypeError(f"Expected Processor, got {type(built).__name__}")
        return built
    raise TypeError(f"Unsupported processor spec: {type(spec).__name__}")


def _ensure_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a long bars frame (or already-wide panel) into a
    ``(datetime, vt_symbol) × MultiIndex(feature|label, name)`` panel.
    """
    if df.empty:
        return df
    if isinstance(df.index, pd.MultiIndex) and isinstance(df.columns, pd.MultiIndex):
        return df
    # Long (tidy) -> panel.
    frame = df.copy()
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    idx_cols = [c for c in ("timestamp", "vt_symbol") if c in frame.columns]
    if len(idx_cols) == 2:
        frame = frame.set_index(idx_cols).sort_index()
    elif isinstance(frame.index, pd.MultiIndex):
        frame = frame.sort_index()
    else:
        raise ValueError("Cannot infer a (datetime, vt_symbol) index from the frame.")

    if not isinstance(frame.columns, pd.MultiIndex):
        # Promote every column under the ``feature`` group.
        tuples: list[tuple[str, str]] = []
        for c in frame.columns:
            group = "label" if str(c).lower().startswith("label") else "feature"
            tuples.append((group, str(c)))
        frame.columns = pd.MultiIndex.from_tuples(tuples)
    return frame


def _select_rows(panel: pd.DataFrame, selector: Any, level: str | int = "datetime") -> pd.DataFrame:
    if panel.empty:
        return panel
    if isinstance(selector, slice) and selector.start is None and selector.stop is None:
        return panel
    try:
        return panel.loc[(selector, slice(None))] if level == "datetime" else panel.loc[(slice(None), selector)]
    except Exception:
        return panel.loc[selector]


def _select_cols(panel: pd.DataFrame, col_set: str | list[str]) -> pd.DataFrame:
    if panel.empty:
        return panel
    if col_set == CS_ALL:
        return panel
    if col_set == CS_RAW:
        return panel
    if col_set in (CS_FEATURE, CS_LABEL) and isinstance(panel.columns, pd.MultiIndex):
        if col_set in panel.columns.get_level_values(0):
            sub = panel[col_set]
            sub.columns = pd.MultiIndex.from_product([[col_set], sub.columns])
            return sub
    if isinstance(col_set, list):
        if isinstance(panel.columns, pd.MultiIndex):
            mask = [c for c in panel.columns if c[-1] in col_set]
            return panel[mask]
        return panel[[c for c in col_set if c in panel.columns]]
    return panel


def _apply_processors(
    df: pd.DataFrame,
    procs: list[Processor],
    fit_window: tuple[pd.Timestamp | None, pd.Timestamp | None],
) -> pd.DataFrame:
    out = df
    for proc in procs:
        try:
            if getattr(proc, "fit_required", False) and hasattr(proc, "fit"):
                fit_start, fit_end = fit_window
                fit_data = out
                if isinstance(out.index, pd.MultiIndex) and fit_start is not None and fit_end is not None:
                    fit_data = out.loc[(slice(fit_start, fit_end), slice(None))]
                proc.fit(fit_data)
            out = proc(out)
        except Exception:
            logger.exception("processor %s failed", type(proc).__name__)
    return out


__all__ = [
    "CS_ALL",
    "CS_FEATURE",
    "CS_LABEL",
    "CS_RAW",
    "DK_I",
    "DK_L",
    "DK_R",
    "DataHandler",
    "DataHandlerABC",
    "DataHandlerLP",
]
