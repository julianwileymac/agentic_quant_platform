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


class CoerceNumericColumns(Processor):
    """Coerce string/object columns into numeric columns when possible.

    Useful for CSV-driven fundamentals/panel datasets where numeric fields
    may be string-typed due to mixed/null values.
    """

    def __init__(
        self,
        columns: list[str] | None = None,
        min_success_ratio: float = 0.8,
    ) -> None:
        self.columns = list(columns or [])
        self.min_success_ratio = float(min_success_ratio)

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            return df
        out = df.copy()
        cols = self.columns or list(out.columns)
        for col in cols:
            if col not in out.columns:
                continue
            if pd.api.types.is_numeric_dtype(out[col]):
                continue
            converted = pd.to_numeric(out[col], errors="coerce")
            if converted.notna().mean() >= self.min_success_ratio:
                out[col] = converted
        return out


class PanelForwardFill(Processor):
    """Forward-fill panel features within each symbol group.

    Inspired by FinRL/quant preprocessing scripts that first sort by
    ``(symbol, timestamp)`` and then fill sparse features per symbol.
    """

    def __init__(
        self,
        symbol_col: str = "vt_symbol",
        timestamp_col: str = "timestamp",
        columns: list[str] | None = None,
        limit: int | None = None,
    ) -> None:
        self.symbol_col = str(symbol_col)
        self.timestamp_col = str(timestamp_col)
        self.columns = list(columns or [])
        self.limit = int(limit) if limit is not None else None

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        if isinstance(df.columns, pd.MultiIndex):
            return df
        out = df.copy()
        if self.symbol_col in out.columns:
            sort_cols = [self.symbol_col]
            if self.timestamp_col in out.columns:
                sort_cols.append(self.timestamp_col)
            out = out.sort_values(sort_cols)
            grouped = out.groupby(self.symbol_col, sort=False)
            cols = self.columns or [
                c
                for c in out.columns
                if c not in {self.symbol_col, self.timestamp_col}
                and pd.api.types.is_numeric_dtype(out[c])
            ]
            if cols:
                out[cols] = grouped[cols].ffill(limit=self.limit)
            return out
        return out.ffill(limit=self.limit)


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


class WinsorizeByQuantile(Processor):
    """Fit-stateful quantile clipping for heavy-tailed numeric features."""

    fit_required = True

    def __init__(
        self,
        columns: list[str] | None = None,
        fields_group: str = "feature",
        lower_q: float = 0.01,
        upper_q: float = 0.99,
    ) -> None:
        self.columns = list(columns or [])
        self.fields_group = fields_group
        self.lower_q = float(lower_q)
        self.upper_q = float(upper_q)
        self._lower: pd.Series | None = None
        self._upper: pd.Series | None = None

    def _select_block(self, df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
        block, is_multi = _flat_block(df, self.fields_group)
        if self.columns:
            keep = [c for c in self.columns if c in block.columns]
            if keep:
                return block[keep], is_multi
        return block, is_multi

    def fit(self, df: pd.DataFrame) -> None:
        block, _ = self._select_block(df)
        if block.empty:
            return
        numeric = block.select_dtypes(include=["number"])
        if numeric.empty:
            return
        self._lower = numeric.quantile(self.lower_q)
        self._upper = numeric.quantile(self.upper_q)

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self._lower is None or self._upper is None:
            return df
        block, is_multi = self._select_block(df)
        if block.empty:
            return df
        clipped = block.copy()
        numeric_cols = [c for c in clipped.columns if c in self._lower.index]
        if not numeric_cols:
            return df
        clipped[numeric_cols] = clipped[numeric_cols].clip(
            lower=self._lower[numeric_cols],
            upper=self._upper[numeric_cols],
            axis=1,
        )
        return _restore_block(df, clipped, self.fields_group, is_multi)


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
# Feature generation / sklearn transformer bridges.
# ---------------------------------------------------------------------------


class SklearnTransformerProcessor(Processor):
    """Fit/apply a sklearn transformer against the feature block."""

    fit_required = True

    def __init__(
        self,
        transformer: str = "standard_scaler",
        transformer_cfg: dict[str, Any] | None = None,
        columns: list[str] | None = None,
        fields_group: str = "feature",
        output_prefix: str | None = None,
    ) -> None:
        self.transformer = str(transformer)
        self.transformer_cfg = dict(transformer_cfg or {})
        self.columns = list(columns or [])
        self.fields_group = fields_group
        self.output_prefix = output_prefix
        self._transformer: Any = None
        self._columns: list[str] = []

    def _make_transformer(self) -> Any:
        if self.transformer_cfg:
            from aqp.core.registry import build_from_config

            return build_from_config(self.transformer_cfg)
        try:
            if self.transformer == "standard_scaler":
                from sklearn.preprocessing import StandardScaler

                return StandardScaler()
            if self.transformer == "minmax_scaler":
                from sklearn.preprocessing import MinMaxScaler

                return MinMaxScaler()
            if self.transformer == "robust_scaler":
                from sklearn.preprocessing import RobustScaler as _RobustScaler

                return _RobustScaler()
            if self.transformer == "power_transformer":
                from sklearn.preprocessing import PowerTransformer

                return PowerTransformer()
            if self.transformer == "pca":
                from sklearn.decomposition import PCA

                return PCA()
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError("scikit-learn is not installed. Install the `ml` extra.") from exc
        raise ValueError(f"Unknown sklearn transformer {self.transformer!r}")

    def _select(self, df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
        block, is_multi = _flat_block(df, self.fields_group)
        numeric = block.select_dtypes(include=["number"])
        if self.columns:
            keep = [c for c in self.columns if c in numeric.columns]
            return numeric[keep], is_multi
        return numeric, is_multi

    def fit(self, df: pd.DataFrame) -> None:
        block, _ = self._select(df)
        if block.empty:
            return
        self._columns = [str(c) for c in block.columns]
        self._transformer = self._make_transformer()
        self._transformer.fit(block.fillna(0.0).to_numpy(dtype=float))

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self._transformer is None:
            return df
        block, is_multi = self._select(df)
        if block.empty:
            return df
        arr = self._transformer.transform(block.fillna(0.0).to_numpy(dtype=float))
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.shape[1] == len(block.columns):
            names = [str(c) for c in block.columns]
        else:
            prefix = self.output_prefix or self.transformer
            names = [f"{prefix}_{i}" for i in range(arr.shape[1])]
        out_block = pd.DataFrame(arr, index=block.index, columns=names)
        return _restore_block(df, out_block, self.fields_group, is_multi, drop_cols=list(block.columns))


class LagFeatureGenerator(Processor):
    """Add per-symbol lagged versions of numeric feature columns."""

    def __init__(
        self,
        columns: list[str] | None = None,
        lags: list[int] | None = None,
        fields_group: str = "feature",
        symbol_level: str = "vt_symbol",
    ) -> None:
        self.columns = list(columns or [])
        self.lags = [int(x) for x in (lags or [1, 5, 10])]
        self.fields_group = fields_group
        self.symbol_level = symbol_level

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        block, is_multi = _flat_block(df, self.fields_group)
        numeric = block.select_dtypes(include=["number"])
        cols = [c for c in (self.columns or list(numeric.columns)) if c in numeric.columns]
        if not cols:
            return df
        generated = pd.DataFrame(index=block.index)
        group_level = self.symbol_level if isinstance(block.index, pd.MultiIndex) and self.symbol_level in block.index.names else None
        for col in cols:
            series = numeric[col]
            for lag in self.lags:
                name = f"{col}_lag_{lag}"
                if group_level:
                    generated[name] = series.groupby(level=group_level).shift(lag)
                else:
                    generated[name] = series.shift(lag)
        merged = pd.concat([block, generated.fillna(0.0)], axis=1)
        return _restore_block(df, merged, self.fields_group, is_multi)


class RollingFeatureGenerator(Processor):
    """Add rolling mean/std/min/max features per symbol."""

    def __init__(
        self,
        columns: list[str] | None = None,
        windows: list[int] | None = None,
        stats: list[str] | None = None,
        fields_group: str = "feature",
        symbol_level: str = "vt_symbol",
    ) -> None:
        self.columns = list(columns or [])
        self.windows = [int(x) for x in (windows or [5, 20])]
        self.stats = list(stats or ["mean", "std"])
        self.fields_group = fields_group
        self.symbol_level = symbol_level

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        block, is_multi = _flat_block(df, self.fields_group)
        numeric = block.select_dtypes(include=["number"])
        cols = [c for c in (self.columns or list(numeric.columns)) if c in numeric.columns]
        if not cols:
            return df
        generated = pd.DataFrame(index=block.index)
        group_level = self.symbol_level if isinstance(block.index, pd.MultiIndex) and self.symbol_level in block.index.names else None

        def _rolling(series: pd.Series, window: int, stat: str) -> pd.Series:
            roll = series.rolling(window=window, min_periods=1)
            if stat == "mean":
                return roll.mean()
            if stat == "std":
                return roll.std().fillna(0.0)
            if stat == "min":
                return roll.min()
            if stat == "max":
                return roll.max()
            if stat == "median":
                return roll.median()
            raise ValueError(f"Unsupported rolling stat {stat!r}")

        for col in cols:
            series = numeric[col]
            for window in self.windows:
                for stat in self.stats:
                    name = f"{col}_roll_{stat}_{window}"
                    if group_level:
                        generated[name] = series.groupby(level=group_level, group_keys=False).apply(
                            lambda s, w=window, st=stat: _rolling(s, w, st)
                        )
                    else:
                        generated[name] = _rolling(series, window, stat)
        merged = pd.concat([block, generated.fillna(0.0)], axis=1)
        return _restore_block(df, merged, self.fields_group, is_multi)


class SeasonalDecomposeFeatures(Processor):
    """Add STL trend/seasonal/residual components for selected columns."""

    def __init__(
        self,
        columns: list[str] | None = None,
        period: int = 20,
        fields_group: str = "feature",
        symbol_level: str = "vt_symbol",
    ) -> None:
        self.columns = list(columns or [])
        self.period = int(period)
        self.fields_group = fields_group
        self.symbol_level = symbol_level

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        try:
            from statsmodels.tsa.seasonal import STL
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError("statsmodels is not installed. Install the `ml` extra.") from exc
        block, is_multi = _flat_block(df, self.fields_group)
        numeric = block.select_dtypes(include=["number"])
        cols = [c for c in (self.columns or list(numeric.columns[:3])) if c in numeric.columns]
        generated = pd.DataFrame(index=block.index)
        group_level = self.symbol_level if isinstance(block.index, pd.MultiIndex) and self.symbol_level in block.index.names else None

        def _components(s: pd.Series) -> pd.DataFrame:
            clean = s.astype(float).replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
            if len(clean) < max(3, self.period * 2):
                return pd.DataFrame(
                    {"trend": clean, "seasonal": 0.0, "resid": 0.0},
                    index=s.index,
                )
            res = STL(clean, period=self.period, robust=True).fit()
            return pd.DataFrame(
                {"trend": res.trend, "seasonal": res.seasonal, "resid": res.resid},
                index=s.index,
            )

        for col in cols:
            if group_level:
                comps = numeric[col].groupby(level=group_level, group_keys=False).apply(_components)
            else:
                comps = _components(numeric[col])
            for component in ("trend", "seasonal", "resid"):
                generated[f"{col}_stl_{component}_{self.period}"] = comps[component].values
        merged = pd.concat([block, generated.fillna(0.0)], axis=1)
        return _restore_block(df, merged, self.fields_group, is_multi)


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
    "CoerceNumericColumns",
    "DropnaLabel",
    "FilterCol",
    "Fillna",
    "FrequencyEncode",
    "HashEncode",
    "MinMaxNorm",
    "OneHotEncode",
    "OrdinalEncode",
    "PanelForwardFill",
    "PreprocessingSpec",
    "Processor",
    "PyODOutlierFilter",
    "RobustScaler",
    "LagFeatureGenerator",
    "RollingFeatureGenerator",
    "SeasonalDecomposeFeatures",
    "SklearnTransformerProcessor",
    "TargetEncode",
    "WinsorizeByQuantile",
]
