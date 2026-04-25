"""Indicator Builder — pick/compose indicators and overlay them on OHLCV.

Inspired by zvt's Factor page (``inspiration/zvt-master/src/zvt/ui/apps/factor_app.py``):
a dense left-rail control surface + a big right-hand chart. Powered by
:class:`aqp.data.indicators_zoo.IndicatorZoo` through the new
``/data/indicators[/preview]`` endpoints.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import solara

from aqp.ui.api_client import post
from aqp.ui.components import (
    Candlestick,
    EntityTable,
    IndicatorOverlay,
    MetricTile,
    SplitPane,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader


_CATEGORY_PANEL = {
    "trend": "price",
    "bands": "price",
    "volume": "volume",
    "oscillator": "oscillator",
    "volatility": "oscillator",
    "statistical": "oscillator",
    "other": "price",
}


@solara.component
def Page() -> None:
    symbol = solara.use_reactive("AAPL.NASDAQ")
    start = solara.use_reactive("2023-01-01")
    end = solara.use_reactive("2024-12-31")
    picks = solara.use_reactive(["SMA:20", "EMA:26"])

    bars_df: solara.Reactive[pd.DataFrame] = solara.use_reactive(pd.DataFrame())
    overlay_cols: solara.Reactive[list[str]] = solara.use_reactive([])
    error = solara.use_reactive("")

    indicator_catalog = use_api("/data/indicators", default=[])
    symbols_catalog = use_api("/data/describe", default=[])

    def _preview() -> None:
        error.set("")
        if not picks.value:
            bars_df.set(pd.DataFrame())
            overlay_cols.set([])
            return
        try:
            payload = post(
                "/data/indicators/preview",
                json={
                    "vt_symbol": symbol.value,
                    "indicators": list(picks.value),
                    "start": start.value,
                    "end": end.value,
                    "rows": 800,
                },
            )
            rows = payload.get("bars") or []
            df = pd.DataFrame(rows)
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
            bars_df.set(df)
            overlay_cols.set(payload.get("overlays") or [])
        except Exception as exc:  # noqa: BLE001
            error.set(str(exc))

    def _toggle(spec: str) -> None:
        cur = list(picks.value)
        if spec in cur:
            cur.remove(spec)
        else:
            cur.append(spec)
        picks.set(cur)

    def _spec_default(ind: dict[str, Any]) -> str:
        name = ind.get("name") or ""
        period = ind.get("default_period")
        if period:
            return f"{name}:{period}"
        return name

    PageHeader(
        title="Indicator Builder",
        subtitle=(
            "Pick technical indicators from the zoo, preview them on a symbol, "
            "and copy the spec list into your strategy recipe."
        ),
        icon="🎛️",
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        SplitPane(
            left_width="320px",
            left=lambda: _left_rail(
                symbol=symbol,
                start=start,
                end=end,
                picks=picks,
                catalog=indicator_catalog.value or [],
                symbols=symbols_catalog.value or [],
                on_preview=_preview,
                on_toggle=_toggle,
                spec_default=_spec_default,
                error=error.value,
            ),
            right=lambda: _chart_pane(
                symbol=symbol.value,
                bars=bars_df.value,
                picks=list(picks.value),
                overlay_cols=overlay_cols.value,
                catalog=indicator_catalog.value or [],
            ),
        )


def _left_rail(
    *,
    symbol: solara.Reactive[str],
    start: solara.Reactive[str],
    end: solara.Reactive[str],
    picks: solara.Reactive[list[str]],
    catalog: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    on_preview,
    on_toggle,
    spec_default,
    error: str,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Symbol"):
            solara.InputText("vt_symbol (e.g. AAPL.NASDAQ)", value=symbol)
            with solara.Row(gap="6px"):
                solara.InputText("start", value=start)
                solara.InputText("end", value=end)
            if symbols:
                labels = [s.get("vt_symbol") or s.get("symbol") or "?" for s in symbols[:15]]
                with solara.Column(gap="4px"):
                    for lab in labels:
                        solara.Button(
                            label=lab,
                            on_click=lambda v=lab: symbol.set(v),
                            outlined=True,
                            dense=True,
                        )
            solara.Button("Preview", on_click=on_preview, color="primary")
            if error:
                solara.Error(error)

        with solara.Card("Indicators"):
            if not catalog:
                solara.Markdown("_Loading indicator zoo…_")
            else:
                categories = sorted({c.get("category") or "other" for c in catalog})
                category_filter = solara.use_reactive("(all)")
                solara.Select(
                    label="Category",
                    value=category_filter,
                    values=["(all)", *categories],
                )
                rows = (
                    catalog
                    if category_filter.value == "(all)"
                    else [c for c in catalog if c.get("category") == category_filter.value]
                )
                with solara.Column(gap="4px"):
                    for ind in rows:
                        spec = spec_default(ind)
                        in_picks = spec in picks.value
                        name = ind.get("name") or spec
                        desc = ind.get("description") or ""
                        tone_bg = "#1e3a8a" if in_picks else "rgba(148, 163, 184, 0.12)"
                        with solara.Row(
                            gap="6px",
                            style={
                                "background": tone_bg,
                                "padding": "6px 8px",
                                "border-radius": "8px",
                                "align-items": "center",
                            },
                        ):
                            solara.Markdown(
                                f"<div style='flex:1'><strong>{name}</strong>"
                                f"<div style='font-size:11px;opacity:0.65'>{desc}</div></div>"
                            )
                            solara.Button(
                                "Remove" if in_picks else "Add",
                                on_click=lambda spec=spec: on_toggle(spec),
                                dense=True,
                                outlined=True,
                            )

        with solara.Card("Selected"):
            if not picks.value:
                solara.Markdown("_No indicators selected._")
            else:
                for spec in picks.value:
                    solara.Markdown(f"- `{spec}`")
                recipe_snippet = (
                    "indicators:\n"
                    + "\n".join(f"  - {s}" for s in picks.value)
                )
                with solara.Details(summary="Recipe YAML snippet"):
                    solara.Markdown(f"```yaml\n{recipe_snippet}\n```")


def _chart_pane(
    *,
    symbol: str,
    bars: pd.DataFrame,
    picks: list[str],
    overlay_cols: list[str],
    catalog: list[dict[str, Any]],
) -> None:
    if bars is None or bars.empty:
        solara.Markdown("_Preview a symbol to see its overlayed candlestick._")
        return

    last = float(bars["close"].iloc[-1])
    first = float(bars["close"].iloc[0]) if len(bars) else last
    gain = last / first - 1 if first else 0.0
    with solara.Column(gap="10px"):
        with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
            MetricTile("Symbol", symbol)
            MetricTile("Bars", len(bars))
            MetricTile(
                "Window return",
                gain,
                unit="%",
                tone="success" if gain > 0 else "error" if gain < 0 else "neutral",
            )
            MetricTile("Indicators on chart", len(picks))

        overlays = _build_overlay_list(picks, overlay_cols, catalog)
        Candlestick(
            bars=bars,
            title=symbol,
            overlays=overlays,
            show_volume=True,
            height=560,
        )

        if picks:
            EntityTable(
                rows=[
                    {
                        "spec": spec,
                        "column": _column_for(spec),
                        "in_data": _column_for(spec) in bars.columns,
                    }
                    for spec in picks
                ],
                title="Overlay columns",
                searchable=False,
            )


def _build_overlay_list(
    picks: list[str],
    overlay_cols: list[str],
    catalog: list[dict[str, Any]],
) -> list[IndicatorOverlay]:
    cat_map = {c.get("name"): c.get("category") or "other" for c in catalog}
    overlays: list[IndicatorOverlay] = []
    for spec in picks:
        col = _column_for(spec)
        if col not in overlay_cols:
            continue
        name = spec.split(":", 1)[0]
        panel = _CATEGORY_PANEL.get(cat_map.get(name, "other"), "price")
        overlays.append(
            IndicatorOverlay(
                column=col,
                label=spec,
                panel=panel,
                width=1.4,
            )
        )
    return overlays


def _column_for(spec: str) -> str:
    if ":" not in spec:
        return spec.lower()
    name, tail = spec.split(":", 1)
    parts = [p.strip() for p in tail.split(",") if p.strip()]
    if len(parts) == 1 and parts[0].isdigit():
        return f"{name.lower()}_{parts[0]}"
    pieces = []
    for i, p in enumerate(parts):
        if "=" in p:
            k, v = p.split("=", 1)
            pieces.append(f"{k.strip()}{v.strip()}")
        else:
            pieces.append(f"arg_{i}{p}")
    tail_str = "_".join(pieces)
    return f"{name.lower()}_{tail_str}" if tail_str else name.lower()
