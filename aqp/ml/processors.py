"""Feature / label processors — ``DataHandlerLP`` pipeline steps.

Each :class:`Processor` is a callable over the handler's panel. Processors
may be fit-stateful (``fit_required = True``) in which case the handler
fits them on a designated ``fit_start_time`` / ``fit_end_time`` window
before applying.

Reference: ``inspiration/qlib-main/qlib/data/dataset/processor.py``.
"""
from __future__ import annotations

import logging
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.ml.base import Serializable

logger = logging.getLogger(__name__)


class Processor(Serializable, ABC):
    """Base processor contract."""

    fit_required: bool = False

    @abstractmethod
    def __call__(self, df: pd.DataFrame) -> pd.DataFrame: ...

    def fit(self, df: pd.DataFrame) -> None:  # pragma: no cover - optional
        """Override in subclass if the processor is stateful."""

    def to_spec(self) -> dict[str, Any]:
        """Return a ``{class, module_path, kwargs}`` dict that rebuilds this
        processor via :func:`aqp.core.registry.build_from_config`.

        Stateful processors (``fit_required = True``) are always serialised
        in-full via pickle in :class:`PreprocessingSpec`; this spec is just
        the structural description for reproducibility / UI inspection.
        """
        kwargs: dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if k.startswith("_"):
                continue
            kwargs[k] = v
        return {
            "class": type(self).__name__,
            "module_path": type(self).__module__,
            "kwargs": kwargs,
        }


# ---------------------------------------------------------------------------
# Column filters.
# ---------------------------------------------------------------------------


class FilterCol(Processor):
    """Keep only the columns whose last-level name is in ``fields``."""

    def __init__(self, fields_group: str = "feature", col_list: list[str] | None = None) -> None:
        self.fields_group = fields_group
        self.col_list = set(col_list or [])

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self.col_list:
            return df
        if not isinstance(df.columns, pd.MultiIndex):
            keep = [c for c in df.columns if c in self.col_list]
            return df[keep]
        keep = [c for c in df.columns if c[0] != self.fields_group or c[-1] in self.col_list]
        return df[keep]


class DropnaLabel(Processor):
    """Drop rows whose label column is NaN."""

    def __init__(self, fields_group: str = "label") -> None:
        self.fields_group = fields_group

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        if not isinstance(df.columns, pd.MultiIndex):
            return df.dropna()
        try:
            labels = df[self.fields_group]
        except KeyError:
            return df
        mask = labels.isna().any(axis=1)
        return df.loc[~mask]


class Fillna(Processor):
    """Fill NaN values with a constant or strategy."""

    def __init__(
        self,
        fields_group: str = "feature",
        fill_value: float | str = 0.0,
    ) -> None:
        self.fields_group = fields_group
        self.fill_value = fill_value

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        target = df
        if isinstance(df.columns, pd.MultiIndex):
            try:
                sub = df[self.fields_group]
            except KeyError:
                return df
            if self.fill_value == "ffill":
                filled = sub.ffill()
            elif self.fill_value == "bfill":
                filled = sub.bfill()
            elif self.fill_value == "mean":
                filled = sub.fillna(sub.mean())
            else:
                filled = sub.fillna(float(self.fill_value))
            target = df.copy()
            target[self.fields_group] = filled.values
            return target
        if self.fill_value == "ffill":
            return df.ffill()
        if self.fill_value == "bfill":
            return df.bfill()
        return df.fillna(float(self.fill_value))


# ---------------------------------------------------------------------------
# Cross-sectional normalisation (per-date).
# ---------------------------------------------------------------------------


class CSZScoreNorm(Processor):
    """Cross-sectional z-score per date (the qlib default for Alpha158)."""

    def __init__(self, fields_group: str = "feature") -> None:
        self.fields_group = fields_group

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        if not isinstance(df.index, pd.MultiIndex):
            raise ValueError("CSZScoreNorm expects a (datetime, vt_symbol) MultiIndex.")
        block = df
        if isinstance(df.columns, pd.MultiIndex):
            try:
                block = df[self.fields_group]
            except KeyError:
                return df
        # Z-score per timestamp level (level 0).
        grouped = block.groupby(level=0)
        mean = grouped.transform("mean")
        std = grouped.transform("std").replace(0.0, np.nan)
        z = (block - mean) / std
        z = z.fillna(0.0)
        if isinstance(df.columns, pd.MultiIndex):
            out = df.copy()
            out[self.fields_group] = z.values
            return out
        return z


class CSRankNorm(Processor):
    """Cross-sectional rank transform (percentile), scaled to ``[-1, 1]``."""

    def __init__(self, fields_group: str = "feature") -> None:
        self.fields_group = fields_group

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        block = df
        if isinstance(df.columns, pd.MultiIndex):
            try:
                block = df[self.fields_group]
            except KeyError:
                return df
        ranked = block.groupby(level=0).rank(pct=True) * 2.0 - 1.0
        ranked = ranked.fillna(0.0)
        if isinstance(df.columns, pd.MultiIndex):
            out = df.copy()
            out[self.fields_group] = ranked.values
            return out
        return ranked


class MinMaxNorm(Processor):
    """Fit-stateful min/max rescaling to ``[0, 1]`` per feature column."""

    fit_required = True

    def __init__(self, fields_group: str = "feature") -> None:
        self.fields_group = fields_group
        self._min: pd.Series | None = None
        self._max: pd.Series | None = None

    def fit(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        block = df
        if isinstance(df.columns, pd.MultiIndex):
            try:
                block = df[self.fields_group]
            except KeyError:
                return
        self._min = block.min()
        self._max = block.max()

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self._min is None or self._max is None:
            return df
        block = df
        if isinstance(df.columns, pd.MultiIndex):
            try:
                block = df[self.fields_group]
            except KeyError:
                return df
        rng = (self._max - self._min).replace(0.0, np.nan)
        out_block = (block - self._min) / rng
        out_block = out_block.fillna(0.0)
        if isinstance(df.columns, pd.MultiIndex):
            out = df.copy()
            out[self.fields_group] = out_block.values
            return out
        return out_block


class RobustScaler(Processor):
    """Fit-stateful robust scaler — (x - median) / IQR per feature column.

    Outlier-resistant alternative to :class:`MinMaxNorm` / standard z-score;
    useful for return-based features that have heavy tails.
    """

    fit_required = True

    def __init__(
        self,
        columns: list[str] | None = None,
        fields_group: str = "feature",
        quantile_range: tuple[float, float] = (0.25, 0.75),
    ) -> None:
        self.columns = list(columns or [])
        self.fields_group = fields_group
        self.quantile_range = (float(quantile_range[0]), float(quantile_range[1]))
        self._center: pd.Series | None = None
        self._scale: pd.Series | None = None

    def _select_block(self, df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            try:
                block = df[self.fields_group]
            except KeyError:
                return df
        else:
            block = df
        if self.columns:
            keep = [c for c in self.columns if c in block.columns]
            return block[keep] if keep else block
        return block

    def fit(self, df: pd.DataFrame) -> None:
        block = self._select_block(df)
        if block.empty:
            return
        self._center = block.median()
        q_lo, q_hi = block.quantile(self.quantile_range[0]), block.quantile(self.quantile_range[1])
        self._scale = (q_hi - q_lo).replace(0.0, np.nan)

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self._center is None or self._scale is None:
            return df
        block = self._select_block(df)
        scaled = ((block - self._center) / self._scale).fillna(0.0)
        if isinstance(df.columns, pd.MultiIndex):
            out = df.copy()
            for col in scaled.columns:
                out[(self.fields_group, col)] = scaled[col].values
            return out
        out = df.copy()
        out[scaled.columns] = scaled.values
        return out


# ---------------------------------------------------------------------------
# Categorical encoders.
# ---------------------------------------------------------------------------


def _flat_block(df: pd.DataFrame, fields_group: str) -> tuple[pd.DataFrame, bool]:
    """Return (block, is_multi). Block is the ``feature`` slice when df has a
    MultiIndex column layout, else the frame itself.
    """
    if isinstance(df.columns, pd.MultiIndex):
        try:
            return df[fields_group], True
        except KeyError:
            return df, False
    return df, False


def _restore_block(
    df: pd.DataFrame,
    new_block: pd.DataFrame,
    fields_group: str,
    is_multi: bool,
    drop_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Return a frame with ``new_block`` replacing the old feature slice."""
    if is_multi:
        out = df.copy()
        if drop_cols:
            existing = [(fields_group, c) for c in drop_cols if (fields_group, c) in out.columns]
            if existing:
                out = out.drop(columns=existing)
        for col in new_block.columns:
            out[(fields_group, col)] = new_block[col].values
        return out
    out = df.copy()
    if drop_cols:
        out = out.drop(columns=[c for c in drop_cols if c in out.columns])
    for col in new_block.columns:
        out[col] = new_block[col].values
    return out


class OneHotEncode(Processor):
    """Fit-stateful one-hot encoder for low-cardinality categorical columns.

    Falls back to keeping the original column unchanged when the cardinality
    exceeds ``max_cardinality`` (use :class:`HashEncode` for those instead).
    """

    fit_required = True

    def __init__(
        self,
        columns: list[str],
        fields_group: str = "feature",
        drop_first: bool = True,
        max_cardinality: int = 64,
    ) -> None:
        self.columns = list(columns)
        self.fields_group = fields_group
        self.drop_first = bool(drop_first)
        self.max_cardinality = int(max_cardinality)
        self._categories: dict[str, list[Any]] = {}

    def fit(self, df: pd.DataFrame) -> None:
        block, _ = _flat_block(df, self.fields_group)
        for col in self.columns:
            if col not in block.columns:
                continue
            cats = sorted([c for c in block[col].dropna().unique()])
            if len(cats) > self.max_cardinality:
                logger.warning(
                    "OneHotEncode: %s has %d categories > %d; skipped",
                    col, len(cats), self.max_cardinality,
                )
                continue
            self._categories[col] = cats

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self._categories:
            return df
        block, is_multi = _flat_block(df, self.fields_group)
        new_cols: dict[str, pd.Series] = {}
        for col, cats in self._categories.items():
            if col not in block.columns:
                continue
            iter_cats = cats[1:] if self.drop_first else cats
            for cat in iter_cats:
                new_cols[f"{col}__{cat}"] = (block[col] == cat).astype("float32")
        if not new_cols:
            return df
        encoded = pd.DataFrame(new_cols, index=block.index)
        return _restore_block(df, encoded, self.fields_group, is_multi, drop_cols=list(self._categories))


class OrdinalEncode(Processor):
    """Map categorical values to integer codes.

    Accepts either an explicit ``mapping`` (dict-of-dicts keyed by column)
    or fits one at fit time using the sorted unique values seen in the
    training panel.
    """

    fit_required = True

    def __init__(
        self,
        columns: list[str],
        fields_group: str = "feature",
        mapping: dict[str, dict[Any, int]] | None = None,
        unknown_value: int = -1,
    ) -> None:
        self.columns = list(columns)
        self.fields_group = fields_group
        self.mapping = {k: dict(v) for k, v in (mapping or {}).items()}
        self.unknown_value = int(unknown_value)
        self._fitted: dict[str, dict[Any, int]] = dict(self.mapping)

    def fit(self, df: pd.DataFrame) -> None:
        block, _ = _flat_block(df, self.fields_group)
        for col in self.columns:
            if col in self.mapping or col not in block.columns:
                continue
            cats = sorted([c for c in block[col].dropna().unique()])
            self._fitted[col] = {cat: i for i, cat in enumerate(cats)}

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self._fitted:
            return df
        block, is_multi = _flat_block(df, self.fields_group)
        new_block = pd.DataFrame(index=block.index)
        for col, m in self._fitted.items():
            if col not in block.columns:
                continue
            new_block[col] = block[col].map(m).fillna(self.unknown_value).astype("int32")
        return _restore_block(df, new_block, self.fields_group, is_multi)


class TargetEncode(Processor):
    """Smoothed target (mean-of-y) encoding.

    Replaces a categorical column with the smoothed conditional mean of
    the label, computed at fit time. ``smoothing`` blends between the
    category-specific mean and the global mean to reduce leakage on rare
    categories.
    """

    fit_required = True

    def __init__(
        self,
        columns: list[str],
        fields_group: str = "feature",
        label_column: str = "label",
        smoothing: float = 10.0,
    ) -> None:
        self.columns = list(columns)
        self.fields_group = fields_group
        self.label_column = str(label_column)
        self.smoothing = float(smoothing)
        self._global_mean: float = 0.0
        self._maps: dict[str, dict[Any, float]] = {}

    def _label_series(self, df: pd.DataFrame) -> pd.Series | None:
        if isinstance(df.columns, pd.MultiIndex):
            for top in ("label", "labels"):
                if top in df.columns.get_level_values(0):
                    sub = df[top]
                    if isinstance(sub, pd.DataFrame) and self.label_column in sub.columns:
                        return sub[self.label_column]
                    if isinstance(sub, pd.DataFrame) and not sub.empty:
                        return sub.iloc[:, 0]
                    if isinstance(sub, pd.Series):
                        return sub
        if self.label_column in df.columns:
            return df[self.label_column]
        return None

    def fit(self, df: pd.DataFrame) -> None:
        block, _ = _flat_block(df, self.fields_group)
        y = self._label_series(df)
        if y is None or block.empty:
            return
        self._global_mean = float(y.mean())
        for col in self.columns:
            if col not in block.columns:
                continue
            counts = block[col].value_counts()
            sums = y.groupby(block[col]).sum()
            means = sums / counts
            smoothed = (counts * means + self.smoothing * self._global_mean) / (counts + self.smoothing)
            self._maps[col] = smoothed.to_dict()

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self._maps:
            return df
        block, is_multi = _flat_block(df, self.fields_group)
        new_block = pd.DataFrame(index=block.index)
        for col, m in self._maps.items():
            if col not in block.columns:
                continue
            new_block[col] = block[col].map(m).fillna(self._global_mean).astype("float32")
        return _restore_block(df, new_block, self.fields_group, is_multi)


class HashEncode(Processor):
    """Stateless feature hashing for high-cardinality categoricals.

    Uses :func:`hash` modulo ``n_features`` so the encoding is stable
    across processes. Each input column expands into ``n_features``
    hashed indicator columns.
    """

    def __init__(
        self,
        columns: list[str],
        fields_group: str = "feature",
        n_features: int = 64,
    ) -> None:
        self.columns = list(columns)
        self.fields_group = fields_group
        self.n_features = max(1, int(n_features))

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self.columns:
            return df
        block, is_multi = _flat_block(df, self.fields_group)
        new_block = pd.DataFrame(index=block.index)
        for col in self.columns:
            if col not in block.columns:
                continue
            buckets = block[col].astype(str).map(lambda v: hash(v) % self.n_features)
            for i in range(self.n_features):
                new_block[f"{col}__h{i}"] = (buckets == i).astype("float32")
        if new_block.empty:
            return df
        return _restore_block(df, new_block, self.fields_group, is_multi, drop_cols=list(self.columns))


class FrequencyEncode(Processor):
    """Replace categorical values with their training-set frequency."""

    fit_required = True

    def __init__(
        self,
        columns: list[str],
        fields_group: str = "feature",
    ) -> None:
        self.columns = list(columns)
        self.fields_group = fields_group
        self._freq: dict[str, dict[Any, float]] = {}

    def fit(self, df: pd.DataFrame) -> None:
        block, _ = _flat_block(df, self.fields_group)
        n = max(1, len(block))
        for col in self.columns:
            if col not in block.columns:
                continue
            counts = block[col].value_counts() / n
            self._freq[col] = counts.to_dict()

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self._freq:
            return df
        block, is_multi = _flat_block(df, self.fields_group)
        new_block = pd.DataFrame(index=block.index)
        for col, m in self._freq.items():
            if col not in block.columns:
                continue
            new_block[col] = block[col].map(m).fillna(0.0).astype("float32")
        return _restore_block(df, new_block, self.fields_group, is_multi)


# ---------------------------------------------------------------------------
# Outlier / anomaly filtering — PyOD-backed.
# ---------------------------------------------------------------------------


class PyODOutlierFilter(Processor):
    """Drop rows flagged as outliers by a PyOD detector.

    Handy both for feature cleaning (KNN on numerical features) and as a
    risk-gating step (IsolationForest / ECOD over recent returns + vol).
    """

    fit_required = True

    def __init__(
        self,
        detector: str = "iforest",
        fields_group: str = "feature",
        contamination: float = 0.02,
        drop: bool = True,
        detector_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.detector_name = detector.lower()
        self.fields_group = fields_group
        self.contamination = float(contamination)
        self.drop = bool(drop)
        self.detector_kwargs = dict(detector_kwargs or {})
        self._detector: Any = None

    def _make_detector(self) -> Any:
        try:
            if self.detector_name == "iforest":
                from pyod.models.iforest import IForest

                return IForest(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "knn":
                from pyod.models.knn import KNN

                return KNN(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "ecod":
                from pyod.models.ecod import ECOD

                return ECOD(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "copod":
                from pyod.models.copod import COPOD

                return COPOD(contamination=self.contamination, **self.detector_kwargs)
            if self.detector_name == "lof":
                from pyod.models.lof import LOF

                return LOF(contamination=self.contamination, **self.detector_kwargs)
            raise ValueError(f"Unknown PyOD detector {self.detector_name!r}")
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "pyod is not installed. Install the `ml-anomaly` extra."
            ) from exc

    def _select_block(self, df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            try:
                return df[self.fields_group]
            except KeyError:
                return df
        return df

    def fit(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        block = self._select_block(df).fillna(0.0)
        self._detector = self._make_detector()
        self._detector.fit(block.values)

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self._detector is None:
            return df
        block = self._select_block(df).fillna(0.0)
        try:
            labels = self._detector.predict(block.values)  # 0 normal / 1 outlier
        except Exception:
            logger.exception("pyod predict failed; leaving data unchanged")
            return df
        mask = np.asarray(labels) == 1
        if not mask.any():
            return df
        if self.drop:
            return df.loc[~mask]
        out = df.copy()
        extra_col = ("feature", "_pyod_outlier") if isinstance(df.columns, pd.MultiIndex) else "_pyod_outlier"
        out[extra_col] = mask.astype(int)
        return out


# ---------------------------------------------------------------------------
# PreprocessingSpec — travels with a trained Model artifact so inference
# code can replay the exact preprocessing chain on new data.
# ---------------------------------------------------------------------------


@dataclass
class PreprocessingSpec:
    """Serialisable record of the preprocessing chain that produced a model.

    A ``PreprocessingSpec`` captures:

    * ``processors`` — the ordered list of fitted :class:`Processor` objects
      that must be applied to new data before inference. Stored as pickled
      bytes so fit state travels with the spec.
    * ``processor_specs`` — a parallel list of ``{class, module_path,
      kwargs}`` dicts from :meth:`Processor.to_spec` so a human (or a UI
      catalog) can inspect the chain without unpickling.
    * ``feature_columns`` / ``label_column`` — the column layout the model
      was trained against, used to validate / reshape new panels.
    * ``handler_cfg`` — optional serialised ``DataHandler`` build spec so a
      caller with only the model artifact can reconstruct the full data
      pipeline.
    * ``metadata`` — free-form bag (e.g. ``fit_start_time``, ``fit_end_time``,
      ``dataset_hash``).

    Persist alongside the ``Model`` pickle via :meth:`save` / :meth:`load`;
    :class:`aqp.ml.base.Model` also supports embedding a spec with
    :meth:`aqp.ml.base.Model.with_preprocessing`.
    """

    processors_pickle: bytes = b""
    processor_specs: list[dict[str, Any]] = field(default_factory=list)
    feature_columns: list[str] = field(default_factory=list)
    label_column: str | None = None
    handler_cfg: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ---- construction --------------------------------------------------

    @classmethod
    def from_processors(
        cls,
        processors: list[Processor],
        *,
        feature_columns: list[str] | None = None,
        label_column: str | None = None,
        handler_cfg: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PreprocessingSpec:
        """Capture a fitted processor chain into a ``PreprocessingSpec``."""
        specs = [p.to_spec() for p in processors]
        blob = pickle.dumps(list(processors))
        return cls(
            processors_pickle=blob,
            processor_specs=specs,
            feature_columns=list(feature_columns or []),
            label_column=label_column,
            handler_cfg=handler_cfg,
            metadata=dict(metadata or {}),
        )

    # ---- replay at inference time --------------------------------------

    def load_processors(self) -> list[Processor]:
        """Unpickle and return the fitted processor chain."""
        if not self.processors_pickle:
            return []
        return pickle.loads(self.processors_pickle)

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run the stored processor chain on ``df`` (read-only, no re-fit)."""
        out = df
        for proc in self.load_processors():
            try:
                out = proc(out)
            except Exception:
                logger.exception(
                    "preprocessing-spec processor %s failed during apply",
                    type(proc).__name__,
                )
        return out

    # ---- persistence ---------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Pickle the whole spec to ``path``."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh)

    @classmethod
    def load(cls, path: str | Path) -> PreprocessingSpec:
        with open(path, "rb") as fh:
            obj = pickle.load(fh)
        if not isinstance(obj, cls):
            raise TypeError(f"{path} does not contain a PreprocessingSpec")
        return obj

    # ---- summary for MLflow / UI --------------------------------------

    def summary(self) -> dict[str, Any]:
        """Compact, JSON-safe summary used for MLflow tag logging / UI."""
        return {
            "n_processors": len(self.processor_specs),
            "processor_classes": [s.get("class") for s in self.processor_specs],
            "n_features": len(self.feature_columns),
            "label": self.label_column,
            "metadata": {k: str(v)[:256] for k, v in self.metadata.items()},
        }


__all__ = [
    "CSRankNorm",
    "CSZScoreNorm",
    "DropnaLabel",
    "FilterCol",
    "Fillna",
    "FrequencyEncode",
    "HashEncode",
    "MinMaxNorm",
    "OneHotEncode",
    "OrdinalEncode",
    "PreprocessingSpec",
    "Processor",
    "PyODOutlierFilter",
    "RobustScaler",
    "TargetEncode",
]
