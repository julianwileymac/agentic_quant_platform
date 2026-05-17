"""Dagster TA ops for the Phase 5 feature materializer.

The canonical backend is ``vectorbtpro``. When ``vectorbtpro`` is not
available, these ops fall back to ``pandas_ta`` (or
``pandas_ta_classic``) so local sandboxes can still execute.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pyarrow as pa

from aqp.data.fabric.schema_registry import FeatureSchema, OHLCVSchema
from aqp.dagster.asset_factory import DagsterAssetFactory

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

logger = logging.getLogger(__name__)


def _empty_feature_table() -> pa.Table:
    return pa.Table.from_pylist([], schema=FeatureSchema.CANONICAL_SCHEMA)


def _ohlcv_to_pandas(table: pa.Table) -> "pd.DataFrame":
    """Convert an OHLCV Arrow table into a normalized pandas frame."""
    import pandas as pd

    validated = OHLCVSchema.validate_table(table)
    df = validated.to_pandas()
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp", "symbol", "close"])
    return df.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _emit_feature_table(
    df_long: "pd.DataFrame",
    *,
    feature_name: str,
    pipeline_version: str,
) -> pa.Table:
    """Emit a FeatureSchema-conforming Arrow table from long-format rows."""
    import pandas as pd

    if df_long.empty:
        return _empty_feature_table()

    frame = df_long.copy()
    frame["symbol"] = frame["symbol"].astype(str)
    frame["feature_value"] = pd.to_numeric(frame["feature_value"], errors="coerce")
    frame = frame.dropna(subset=["symbol", "feature_value"])
    if frame.empty:
        return _empty_feature_table()

    row_count = int(len(frame))
    computation_ts = datetime.now(timezone.utc)
    out = pa.table(
        {
            "symbol": pa.array(frame["symbol"].tolist(), type=pa.string()),
            "feature_name": pa.array([feature_name] * row_count, type=pa.string()),
            "computation_ts": pa.array(
                [computation_ts] * row_count,
                type=pa.timestamp("us", tz="UTC"),
            ),
            "pipeline_version": pa.array(
                [str(pipeline_version)] * row_count,
                type=pa.string(),
            ),
            "feature_value": pa.array(
                frame["feature_value"].astype(float).tolist(),
                type=pa.float64(),
            ),
        },
        schema=FeatureSchema.CANONICAL_SCHEMA,
    )
    return FeatureSchema.validate_table(out)


def _pivot_close(df: "pd.DataFrame") -> "pd.DataFrame":
    import pandas as pd

    if df.empty:
        return pd.DataFrame()
    return (
        df.pivot_table(index="timestamp", columns="symbol", values="close", aggfunc="last")
        .sort_index()
    )


def _to_long_feature_frame(frame: "pd.DataFrame") -> "pd.DataFrame":
    import pandas as pd

    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "feature_value"])

    long_df = frame.stack(dropna=False).rename("feature_value").reset_index()
    if long_df.shape[1] < 3:
        return pd.DataFrame(columns=["timestamp", "symbol", "feature_value"])

    ts_col = long_df.columns[0]
    symbol_col = long_df.columns[1]
    return long_df.rename(columns={ts_col: "timestamp", symbol_col: "symbol"})


def _concat_feature_tables(tables: list[pa.Table]) -> pa.Table:
    non_empty = [tbl for tbl in tables if int(tbl.num_rows) > 0]
    if not non_empty:
        return _empty_feature_table()
    if len(non_empty) == 1:
        return FeatureSchema.validate_table(non_empty[0])
    return FeatureSchema.validate_table(pa.concat_tables(non_empty))


def _load_indicator_backend() -> tuple[str, Any]:
    try:
        import vectorbtpro as vbt  # type: ignore[import-not-found]

        return "vectorbtpro", vbt
    except ImportError:
        try:
            import pandas_ta as pta  # type: ignore[import-not-found]

            return "pandas_ta", pta
        except ImportError:
            try:
                import pandas_ta_classic as pta  # type: ignore[import-not-found]

                return "pandas_ta", pta
            except ImportError as exc:
                raise RuntimeError(
                    "No TA backend available. Install `vectorbtpro` or "
                    "`pandas_ta`/`pandas_ta_classic`."
                ) from exc


def _as_numeric_series(values: Any, index: "pd.Index") -> "pd.Series":
    import pandas as pd

    if isinstance(values, pd.DataFrame):
        if values.empty:
            return pd.Series(index=index, dtype=float)
        values = values.iloc[:, 0]
    if isinstance(values, pd.Series):
        series = values
    else:
        series = pd.Series(values, index=index)
    series = pd.to_numeric(series, errors="coerce")
    if not series.index.equals(index):
        series = series.reindex(index)
    return series.astype(float)


def _apply_series_indicator(
    pivoted: "pd.DataFrame",
    compute_one: Any,
) -> "pd.DataFrame":
    import pandas as pd

    if pivoted.empty:
        return pd.DataFrame(index=pivoted.index)
    out: dict[str, pd.Series] = {}
    for symbol in pivoted.columns:
        series = _as_numeric_series(pivoted[symbol], pivoted.index)
        computed = compute_one(series)
        out[str(symbol)] = _as_numeric_series(computed, pivoted.index)
    return pd.DataFrame(out, index=pivoted.index)


def _extract_named_column(frame: Any, prefixes: tuple[str, ...], index: "pd.Index") -> "pd.Series":
    import pandas as pd

    if frame is None:
        return pd.Series(index=index, dtype=float)
    if isinstance(frame, pd.Series):
        return _as_numeric_series(frame, index)
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(index=index, dtype=float)
    for col in frame.columns:
        col_name = str(col)
        lowered = col_name.lower()
        if any(lowered.startswith(prefix.lower()) for prefix in prefixes):
            return _as_numeric_series(frame[col], index)
    return _as_numeric_series(frame.iloc[:, 0], index)


def _moving_averages(table: pa.Table, params: dict[str, Any]) -> pa.Table:
    """Compute simple moving averages."""
    df = _ohlcv_to_pandas(table)
    pivoted = _pivot_close(df)
    if pivoted.empty:
        return _empty_feature_table()

    pipeline_version = str(params.get("pipeline_version", "v0"))
    feature_prefix = str(params.get("feature_prefix", "sma"))
    raw_windows = params.get("windows", [10, 20, 50])
    windows = [int(w) for w in raw_windows] if isinstance(raw_windows, list) else [10, 20, 50]

    backend_name, backend = _load_indicator_backend()
    tables: list[pa.Table] = []
    for window in windows:
        if window <= 0:
            continue
        if backend_name == "vectorbtpro":
            ma_frame = backend.MA.run(pivoted, window=window).ma
        else:
            ma_frame = _apply_series_indicator(
                pivoted,
                lambda series: backend.sma(series, length=window),
            )
        long_df = _to_long_feature_frame(ma_frame)
        tables.append(
            _emit_feature_table(
                long_df,
                feature_name=f"{feature_prefix}_{window}",
                pipeline_version=pipeline_version,
            )
        )

    return _concat_feature_tables(tables)


def _rsi(table: pa.Table, params: dict[str, Any]) -> pa.Table:
    """Compute RSI."""
    df = _ohlcv_to_pandas(table)
    pivoted = _pivot_close(df)
    if pivoted.empty:
        return _empty_feature_table()

    window = int(params.get("window", 14))
    pipeline_version = str(params.get("pipeline_version", "v0"))
    backend_name, backend = _load_indicator_backend()
    if backend_name == "vectorbtpro":
        rsi_frame = backend.RSI.run(pivoted, window=window).rsi
    else:
        rsi_frame = _apply_series_indicator(
            pivoted,
            lambda series: backend.rsi(series, length=window),
        )

    long_df = _to_long_feature_frame(rsi_frame)
    return _emit_feature_table(
        long_df,
        feature_name=f"rsi_{window}",
        pipeline_version=pipeline_version,
    )


def _bollinger_bands(table: pa.Table, params: dict[str, Any]) -> pa.Table:
    """Compute Bollinger Bands (upper/lower/middle)."""
    import pandas as pd

    df = _ohlcv_to_pandas(table)
    pivoted = _pivot_close(df)
    if pivoted.empty:
        return _empty_feature_table()

    window = int(params.get("window", 20))
    std = float(params.get("std", 2.0))
    pipeline_version = str(params.get("pipeline_version", "v0"))
    std_label = str(std)

    backend_name, backend = _load_indicator_backend()
    if backend_name == "vectorbtpro":
        bbands = backend.BBANDS.run(pivoted, window=window, alpha=std)
        upper = bbands.upper
        middle = bbands.middle
        lower = bbands.lower
    else:
        upper = pd.DataFrame(index=pivoted.index)
        middle = pd.DataFrame(index=pivoted.index)
        lower = pd.DataFrame(index=pivoted.index)
        for symbol in pivoted.columns:
            series = _as_numeric_series(pivoted[symbol], pivoted.index)
            bb = backend.bbands(series, length=window, std=std)
            upper[str(symbol)] = _extract_named_column(bb, ("BBU", "upper"), pivoted.index)
            middle[str(symbol)] = _extract_named_column(bb, ("BBM", "middle"), pivoted.index)
            lower[str(symbol)] = _extract_named_column(bb, ("BBL", "lower"), pivoted.index)

    tables = [
        _emit_feature_table(
            _to_long_feature_frame(upper),
            feature_name=f"bb_upper_{window}_{std_label}",
            pipeline_version=pipeline_version,
        ),
        _emit_feature_table(
            _to_long_feature_frame(middle),
            feature_name=f"bb_middle_{window}_{std_label}",
            pipeline_version=pipeline_version,
        ),
        _emit_feature_table(
            _to_long_feature_frame(lower),
            feature_name=f"bb_lower_{window}_{std_label}",
            pipeline_version=pipeline_version,
        ),
    ]
    return _concat_feature_tables(tables)


def _macd(table: pa.Table, params: dict[str, Any]) -> pa.Table:
    """Compute MACD line, signal, and histogram."""
    import pandas as pd

    df = _ohlcv_to_pandas(table)
    pivoted = _pivot_close(df)
    if pivoted.empty:
        return _empty_feature_table()

    fast_window = int(params.get("fast_window", 12))
    slow_window = int(params.get("slow_window", 26))
    signal_window = int(params.get("signal_window", 9))
    pipeline_version = str(params.get("pipeline_version", "v0"))

    backend_name, backend = _load_indicator_backend()
    if backend_name == "vectorbtpro":
        macd = backend.MACD.run(
            pivoted,
            fast_window=fast_window,
            slow_window=slow_window,
            signal_window=signal_window,
        )
        macd_line = macd.macd
        signal_line = macd.signal
        hist_line = macd.hist
    else:
        macd_line = pd.DataFrame(index=pivoted.index)
        signal_line = pd.DataFrame(index=pivoted.index)
        hist_line = pd.DataFrame(index=pivoted.index)
        for symbol in pivoted.columns:
            series = _as_numeric_series(pivoted[symbol], pivoted.index)
            frame = backend.macd(
                series,
                fast=fast_window,
                slow=slow_window,
                signal=signal_window,
            )
            macd_line[str(symbol)] = _extract_named_column(
                frame,
                ("MACD_", "macd"),
                pivoted.index,
            )
            signal_line[str(symbol)] = _extract_named_column(
                frame,
                ("MACDs", "signal"),
                pivoted.index,
            )
            hist_line[str(symbol)] = _extract_named_column(
                frame,
                ("MACDh", "hist"),
                pivoted.index,
            )

    tables = [
        _emit_feature_table(
            _to_long_feature_frame(macd_line),
            feature_name=f"macd_{fast_window}_{slow_window}",
            pipeline_version=pipeline_version,
        ),
        _emit_feature_table(
            _to_long_feature_frame(signal_line),
            feature_name=f"macd_signal_{signal_window}",
            pipeline_version=pipeline_version,
        ),
        _emit_feature_table(
            _to_long_feature_frame(hist_line),
            feature_name="macd_hist",
            pipeline_version=pipeline_version,
        ),
    ]
    return _concat_feature_tables(tables)


_factory = DagsterAssetFactory()

compute_moving_averages = _factory.build_transformation_op(
    _moving_averages,
    input_schema=OHLCVSchema,
    output_schema=FeatureSchema,
    op_name="compute_moving_averages",
)
compute_rsi = _factory.build_transformation_op(
    _rsi,
    input_schema=OHLCVSchema,
    output_schema=FeatureSchema,
    op_name="compute_rsi",
)
compute_bollinger_bands = _factory.build_transformation_op(
    _bollinger_bands,
    input_schema=OHLCVSchema,
    output_schema=FeatureSchema,
    op_name="compute_bollinger_bands",
)
compute_macd = _factory.build_transformation_op(
    _macd,
    input_schema=OHLCVSchema,
    output_schema=FeatureSchema,
    op_name="compute_macd",
)


__all__ = [
    "compute_bollinger_bands",
    "compute_macd",
    "compute_moving_averages",
    "compute_rsi",
]
