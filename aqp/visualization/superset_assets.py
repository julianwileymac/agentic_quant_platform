"""Declarative Superset assets for AQP's Trino-backed datasets.

The asset plan is built deterministically from the curated
:data:`aqp.data.dataset_presets.PRESETS` registry. For each preset we emit:

* a :class:`SupersetDatasetSpec` referencing the Iceberg table via its
  ``namespace.table`` identifier;
* one or more :class:`SupersetChartSpec` chosen from a category-aware
  catalog (price/intraday/options/macro/fundamentals/lob/screen/...);
* a single dashboard shell that aggregates everything into the
  ``aqp-market-data-explorer`` slug.

Adding a preset under :data:`PRESETS` automatically promotes it into the
plan; no edits needed here unless the preset belongs to a brand-new
category that doesn't fit the existing chart catalog.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from aqp.config import settings
from aqp.data.dataset_presets import PRESETS, DatasetPreset

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SupersetDatasetSpec:
    identifier: str
    schema: str
    table_name: str
    label: str
    description: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SupersetChartSpec:
    slice_name: str
    viz_type: str
    datasource_identifier: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SupersetDashboardSpec:
    dashboard_title: str
    slug: str
    position_json: dict[str, Any] = field(default_factory=dict)
    json_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SupersetAssetPlan:
    database: dict[str, Any]
    datasets: list[SupersetDatasetSpec]
    charts: list[SupersetChartSpec]
    dashboards: list[SupersetDashboardSpec]

    def to_dict(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "datasets": [d.__dict__ for d in self.datasets],
            "charts": [c.__dict__ for c in self.charts],
            "dashboards": [d.__dict__ for d in self.dashboards],
        }


# ---------------------------------------------------------------------------
# Category routing
# ---------------------------------------------------------------------------

#: Category → list of (chart slice suffix, viz_type, params) emitter functions.
#: Each emitter accepts a ``DatasetPreset`` and returns the chart params dict.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "price": ("equity", "etf", "us", "china"),
    "intraday": ("intraday", "5m", "30m"),
    "fundamentals": ("fundamentals", "ml"),
    "macro": ("macro", "fred"),
    "options": ("options",),
    "lob": ("lob", "hft"),
    "screening": ("screening", "scraper"),
    "futures": ("futures", "commodity"),
    "fx": ("fx", "stat_arb"),
    "tabular": ("tabular", "preprocessing", "cleaning"),
    "crypto": ("crypto",),
    "universe": ("universe", "point_in_time"),
}


def _classify(preset: DatasetPreset) -> str:
    """Pick the most-specific category for a preset.

    Order matters: a `fundamentals` preset that's also tagged `equity`
    routes to `fundamentals` first because it appears earlier in the
    keyword map.
    """

    tag_set = {tag.lower() for tag in preset.tags}
    interval = (preset.interval or "").lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(k in tag_set for k in keywords):
            return category
    if interval in {"5m", "15m", "30m", "1m"}:
        return "intraday"
    if interval == "1d":
        return "price"
    if interval == "tick":
        return "lob"
    return "table"


# ---------------------------------------------------------------------------
# Chart factories — one per category
# ---------------------------------------------------------------------------


def _label(preset: DatasetPreset) -> str:
    return preset.name.replace("_", " ").title()


def _price_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    label = _label(preset)
    identifier = preset.iceberg_identifier
    return [
        SupersetChartSpec(
            slice_name=f"{label} Close",
            viz_type="echarts_timeseries_line",
            datasource_identifier=identifier,
            params={
                "x_axis": "timestamp",
                "metrics": ["close"],
                "groupby": ["vt_symbol"],
                "row_limit": 10000,
                "show_legend": True,
            },
        ),
        SupersetChartSpec(
            slice_name=f"{label} Volume",
            viz_type="echarts_timeseries_bar",
            datasource_identifier=identifier,
            params={
                "x_axis": "timestamp",
                "metrics": ["volume"],
                "groupby": ["vt_symbol"],
                "row_limit": 10000,
            },
        ),
        SupersetChartSpec(
            slice_name=f"{label} Latest Bars",
            viz_type="table",
            datasource_identifier=identifier,
            params={"row_limit": 200, "order_desc": True, "timestamp_format": "smart_date"},
        ),
    ]


def _intraday_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    label = _label(preset)
    identifier = preset.iceberg_identifier
    return [
        SupersetChartSpec(
            slice_name=f"{label} Intraday Close",
            viz_type="echarts_timeseries_line",
            datasource_identifier=identifier,
            params={
                "x_axis": "timestamp",
                "metrics": ["close"],
                "groupby": ["vt_symbol"],
                "row_limit": 50000,
                "time_grain_sqla": "PT5M",
            },
        ),
        SupersetChartSpec(
            slice_name=f"{label} Returns Histogram",
            viz_type="dist_bar",
            datasource_identifier=identifier,
            params={"metrics": ["returns"], "row_limit": 50000},
        ),
    ]


def _fundamentals_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    label = _label(preset)
    identifier = preset.iceberg_identifier
    return [
        SupersetChartSpec(
            slice_name=f"{label} Snapshot",
            viz_type="table",
            datasource_identifier=identifier,
            params={"row_limit": 1000, "order_desc": True},
        ),
        SupersetChartSpec(
            slice_name=f"{label} Sector Heatmap",
            viz_type="heatmap",
            datasource_identifier=identifier,
            params={"all_columns_x": "sector", "all_columns_y": "metric"},
        ),
    ]


def _macro_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    label = _label(preset)
    identifier = preset.iceberg_identifier
    return [
        SupersetChartSpec(
            slice_name=f"{label} Series",
            viz_type="echarts_timeseries_line",
            datasource_identifier=identifier,
            params={
                "x_axis": "timestamp",
                "metrics": ["value"],
                "groupby": ["series_id"],
                "row_limit": 5000,
            },
        ),
    ]


def _options_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    label = _label(preset)
    identifier = preset.iceberg_identifier
    return [
        SupersetChartSpec(
            slice_name=f"{label} Chain",
            viz_type="table",
            datasource_identifier=identifier,
            params={"row_limit": 2000},
        ),
        SupersetChartSpec(
            slice_name=f"{label} IV Skew",
            viz_type="echarts_timeseries_scatter",
            datasource_identifier=identifier,
            params={"x_axis": "strike", "metrics": ["implied_volatility"]},
        ),
    ]


def _lob_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    label = _label(preset)
    identifier = preset.iceberg_identifier
    return [
        SupersetChartSpec(
            slice_name=f"{label} Top-of-book",
            viz_type="echarts_timeseries_line",
            datasource_identifier=identifier,
            params={
                "x_axis": "timestamp",
                "metrics": ["bid_price", "ask_price"],
                "row_limit": 50000,
            },
        ),
    ]


def _screening_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    return [
        SupersetChartSpec(
            slice_name=f"{_label(preset)} Screen",
            viz_type="table",
            datasource_identifier=preset.iceberg_identifier,
            params={"row_limit": 2000, "order_desc": True},
        ),
    ]


def _futures_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    return _price_charts(preset)


def _fx_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    return _macro_charts(preset)


def _tabular_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    return [
        SupersetChartSpec(
            slice_name=f"{_label(preset)} Sample",
            viz_type="table",
            datasource_identifier=preset.iceberg_identifier,
            params={"row_limit": 1000},
        ),
    ]


def _crypto_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    return _intraday_charts(preset)


def _universe_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    return [
        SupersetChartSpec(
            slice_name=f"{_label(preset)} Membership",
            viz_type="table",
            datasource_identifier=preset.iceberg_identifier,
            params={"row_limit": 2000},
        ),
    ]


def _generic_charts(preset: DatasetPreset) -> list[SupersetChartSpec]:
    return [
        SupersetChartSpec(
            slice_name=f"{_label(preset)} Preview",
            viz_type="table",
            datasource_identifier=preset.iceberg_identifier,
            params={"row_limit": 1000},
        ),
    ]


_CATEGORY_FACTORIES = {
    "price": _price_charts,
    "intraday": _intraday_charts,
    "fundamentals": _fundamentals_charts,
    "macro": _macro_charts,
    "options": _options_charts,
    "lob": _lob_charts,
    "screening": _screening_charts,
    "futures": _futures_charts,
    "fx": _fx_charts,
    "tabular": _tabular_charts,
    "crypto": _crypto_charts,
    "universe": _universe_charts,
    "table": _generic_charts,
}


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def common_dataset_identifiers() -> list[str]:
    """Return the Iceberg identifiers of every curated preset.

    Kept as a function (not a constant) so unit tests can monkeypatch
    :data:`PRESETS` without touching module-level state.
    """

    return [p.iceberg_identifier for p in PRESETS.values()]


def preset_for_identifier(identifier: str) -> DatasetPreset | None:
    return next((p for p in PRESETS.values() if p.iceberg_identifier == identifier), None)


def build_asset_plan(
    *,
    available_identifiers: list[str] | None = None,
    include_common_only: bool = True,
) -> SupersetAssetPlan:
    """Build deterministic Superset assets from AQP dataset metadata.

    ``available_identifiers`` is the live set of Iceberg tables (typically
    from :func:`aqp.data.iceberg_catalog.list_tables`); we never emit a
    dataset spec that wouldn't resolve. When ``available_identifiers`` is
    ``None`` we trust the preset registry and emit specs for every preset.

    ``include_common_only`` exists for backwards compatibility — it has no
    effect now that the plan is preset-driven, since the registry IS the
    curated common list.
    """

    _ = include_common_only  # kept for backwards-compat signature
    available = set(available_identifiers) if available_identifiers is not None else None

    datasets: list[SupersetDatasetSpec] = []
    charts: list[SupersetChartSpec] = []

    for preset in PRESETS.values():
        if available is not None and preset.iceberg_identifier not in available:
            continue
        datasets.append(
            SupersetDatasetSpec(
                identifier=preset.iceberg_identifier,
                schema=preset.namespace,
                table_name=preset.table,
                label=_label(preset),
                description=preset.description,
                tags=list(preset.tags),
            )
        )
        category = _classify(preset)
        factory = _CATEGORY_FACTORIES.get(category, _generic_charts)
        charts.extend(factory(preset))

    dashboards = [
        SupersetDashboardSpec(
            dashboard_title="AQP Market Data Explorer",
            slug="aqp-market-data-explorer",
            # Superset's json_metadata schema is a strict allowlist; AQP
            # bookkeeping fields (categories / chart ids) live on the
            # SupersetDashboardSpec instance instead.
            json_metadata={
                "label_colors": {},
                "timed_refresh_immune_slices": [],
                "expanded_slices": {},
                "refresh_frequency": 0,
            },
        ),
    ]

    # Superset's POST /api/v1/database/ takes ``extra`` as a JSON string,
    # not a nested object — passing a dict yields a 400 validation error.
    extra_json = json.dumps(
        {
            "metadata_params": {},
            "engine_params": {},
            "metadata_cache_timeout": {},
            "schemas_allowed_for_file_upload": [],
        }
    )

    return SupersetAssetPlan(
        database={
            "database_name": "AQP Trino Iceberg",
            "sqlalchemy_uri": settings.trino_uri,
            "expose_in_sqllab": True,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_dml": False,
            "extra": extra_json,
        },
        datasets=datasets,
        charts=charts,
        dashboards=dashboards,
    )


# Backwards-compatible re-export so the original four-entry constant still resolves.
COMMON_DATASETS: list[str] = [
    "aqp_equity.sp500_daily",
    "aqp_alpha_vantage.time_series_intraday",
    "aqp_finrl.fundamentals_panel_sample",
    "aqp_macro.fred_basket",
]


__all__ = [
    "COMMON_DATASETS",
    "SupersetAssetPlan",
    "SupersetChartSpec",
    "SupersetDashboardSpec",
    "SupersetDatasetSpec",
    "build_asset_plan",
    "common_dataset_identifiers",
    "preset_for_identifier",
]
