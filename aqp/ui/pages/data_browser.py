"""Data Browser — interactive OHLCV discovery + charting.

Split-pane layout: left rail with the universe catalog + per-symbol form,
right pane with the dense :class:`Candlestick` + volume + indicator
overlays + stats strip. Multi-symbol overlay moved into its own tab so
the main view stays compact.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pandas as pd
import solara

from aqp.ui.api_client import get, post
from aqp.ui.components import (
    Candlestick,
    EntityTable,
    IndicatorOverlay,
    MetricTile,
    SplitPane,
    TabPanel,
    TabSpec,
    TaskStreamer,
    use_api,
)
from aqp.ui.layout.page_header import PageHeader
from aqp.ui.services.security import IBKRAvailability, get_ibkr_availability
from aqp.ui.theme import PALETTE, plotly_template


@dataclass
class _LoadError:
    title: str = ""
    detail: str = ""
    code: str = ""
    hint: str = ""

    def is_empty(self) -> bool:
        return not (self.title or self.detail)


@solara.component
def Page() -> None:
    selected_symbol = solara.use_reactive("")
    start = solara.use_reactive("2023-01-01")
    end = solara.use_reactive("2024-12-31")
    source_mode = solara.use_reactive("Lake")
    ibkr_bar_size = solara.use_reactive("1 day")
    ibkr_what_to_show = solara.use_reactive("TRADES")
    ibkr_use_rth = solara.use_reactive(True)
    ibkr_ingest_task_id = solara.use_reactive("")
    overlays_raw = solara.use_reactive("SMA:20, EMA:26")
    overlay_symbols = solara.use_reactive("")

    bars_df: solara.Reactive[pd.DataFrame] = solara.use_reactive(pd.DataFrame())
    stats: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    overlay_df: solara.Reactive[pd.DataFrame] = solara.use_reactive(pd.DataFrame())
    load_error: solara.Reactive[_LoadError] = solara.use_reactive(_LoadError())
    ibkr_state: solara.Reactive[IBKRAvailability] = solara.use_reactive(
        IBKRAvailability(ok=False, message="")
    )

    catalog = use_api("/data/describe", default=[], interval=20.0)

    def _probe_ibkr() -> None:
        if source_mode.value in {"IBKR Preview", "IBKR Persist"}:
            ibkr_state.set(get_ibkr_availability())

    solara.use_effect(_probe_ibkr, [source_mode.value])

    def _set_structured_error(title: str, exc: Exception) -> None:
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = None
            if isinstance(detail, dict):
                load_error.set(
                    _LoadError(
                        title=title,
                        detail=str(detail.get("detail") or exc),
                        code=str(detail.get("code") or ""),
                        hint=str(detail.get("hint") or ""),
                    )
                )
                return
            if isinstance(detail, str):
                load_error.set(_LoadError(title=title, detail=detail))
                return
        load_error.set(_LoadError(title=title, detail=str(exc)))

    def _ibkr_payload() -> dict[str, Any]:
        return {
            "vt_symbol": selected_symbol.value,
            "start": start.value,
            "end": end.value,
            "bar_size": ibkr_bar_size.value,
            "what_to_show": ibkr_what_to_show.value,
            "use_rth": bool(ibkr_use_rth.value),
        }

    def _load_symbol() -> None:
        if not selected_symbol.value:
            return
        load_error.set(_LoadError())
        if source_mode.value == "IBKR Preview":
            try:
                payload = post("/data/ibkr/historical/fetch", json=_ibkr_payload())
                rows = payload.get("bars") or []
                df = pd.DataFrame(rows)
                if not df.empty:
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df = _apply_overlays(df, overlays_raw.value)
                bars_df.set(df)
                stats.set(
                    {
                        "first_ts": payload.get("first_ts"),
                        "last_ts": payload.get("last_ts"),
                        "bar_count": payload.get("count", len(df)),
                        "source": "ibkr",
                        "what_to_show": payload.get("what_to_show", ibkr_what_to_show.value),
                        "bar_size": payload.get("bar_size", ibkr_bar_size.value),
                        "use_rth": payload.get("use_rth", bool(ibkr_use_rth.value)),
                        "gaps": [],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                bars_df.set(pd.DataFrame())
                stats.set({})
                _set_structured_error("IBKR historical fetch failed", exc)
            return

        try:
            payload = get(
                f"/data/{selected_symbol.value}/bars"
                f"?start={start.value}&end={end.value}"
            )
            rows = payload.get("bars") or []
            df = pd.DataFrame(rows)
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = _apply_overlays(df, overlays_raw.value)
            bars_df.set(df)
        except Exception as exc:  # noqa: BLE001
            bars_df.set(pd.DataFrame())
            _set_structured_error("Bars fetch failed", exc)
        try:
            stats.set(
                get(
                    f"/data/{selected_symbol.value}/stats"
                    f"?start={start.value}&end={end.value}"
                )
                or {}
            )
        except Exception:
            stats.set({})

    def _persist_symbol() -> None:
        if not selected_symbol.value:
            return
        load_error.set(_LoadError())
        try:
            payload = {**_ibkr_payload(), "overwrite": False}
            resp = post("/data/ibkr/historical/ingest", json=payload)
            ibkr_ingest_task_id.set(resp.get("task_id", ""))
            catalog.refresh()
            solara.Info(f"IBKR ingest queued: {resp.get('task_id')}")
        except Exception as exc:  # noqa: BLE001
            _set_structured_error("Could not queue IBKR ingest", exc)

    def _load_overlay_multi() -> None:
        symbols = [s.strip() for s in overlay_symbols.value.split(",") if s.strip()]
        if not symbols:
            overlay_df.set(pd.DataFrame())
            return
        frames: list[pd.DataFrame] = []
        for sym in symbols:
            try:
                payload = get(
                    f"/data/{sym}/bars?start={start.value}&end={end.value}"
                )
                rows = payload.get("bars") or []
                if not rows:
                    continue
                sub = pd.DataFrame(rows)
                sub["timestamp"] = pd.to_datetime(sub["timestamp"])
                first = float(sub["close"].iloc[0]) or 1.0
                sub["normalized"] = sub["close"] / first
                sub["vt_symbol"] = sym
                frames.append(sub[["timestamp", "vt_symbol", "normalized"]])
            except Exception:
                continue
        overlay_df.set(
            pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        )

    PageHeader(
        title="Data Browser",
        subtitle=(
            "Interactive per-symbol OHLCV view over the local Parquet lake, with "
            "quick indicator overlays and multi-symbol normalised comparison."
        ),
        icon="🔎",
    )

    with solara.Column(gap="12px", style={"padding": "14px 20px"}):
        if not load_error.value.is_empty():
            _error_card(load_error.value)
        SplitPane(
            left_width="300px",
            left=lambda: _left_rail(
                catalog_rows=catalog.value or [],
                selected=selected_symbol,
                start=start,
                end=end,
                source_mode=source_mode,
                ibkr_bar_size=ibkr_bar_size,
                ibkr_what_to_show=ibkr_what_to_show,
                ibkr_use_rth=ibkr_use_rth,
                overlays_raw=overlays_raw,
                ibkr_state=ibkr_state.value,
                on_load=_load_symbol,
                on_persist=_persist_symbol,
            ),
            right=lambda: TabPanel(
                tabs=[
                    TabSpec(
                        key="chart",
                        label="Chart",
                        render=lambda: _chart_tab(
                            selected_symbol=selected_symbol.value,
                            bars=bars_df.value,
                            stats=stats.value or {},
                            overlays_raw=overlays_raw.value,
                        ),
                    ),
                    TabSpec(
                        key="overlay",
                        label="Multi-symbol overlay",
                        render=lambda: _overlay_tab(
                            overlay_symbols=overlay_symbols,
                            overlay_df=overlay_df.value,
                            on_load=_load_overlay_multi,
                        ),
                    ),
                    TabSpec(
                        key="catalog",
                        label="Catalog",
                        render=lambda: EntityTable(
                            rows=catalog.value or [],
                            title="Parquet lake catalog",
                            empty="_Lake empty — run `aqp data ingest`._",
                        ),
                    ),
                    TabSpec(
                        key="data-links",
                        label="Data Links",
                        render=lambda: _data_links_tab(selected_symbol.value),
                    ),
                ]
            ),
        )
        if ibkr_ingest_task_id.value:
            TaskStreamer(
                task_id=ibkr_ingest_task_id.value,
                title="IBKR ingest stream",
                show_result=True,
            )


def _error_card(err: _LoadError) -> None:
    with solara.Div(
        style={
            "background": PALETTE.error,
            "color": PALETTE.error_fg,
            "padding": "12px 16px",
            "border-radius": "10px",
            "border-left": f"4px solid {PALETTE.text_inverse}",
        }
    ):
        solara.Markdown(
            f"<strong>{err.title or 'Error'}</strong>"
            + (f" <span style='opacity:0.85'>[{err.code}]</span>" if err.code else "")
        )
        solara.Markdown(err.detail)
        if err.hint:
            solara.Markdown(f"<em>Hint:</em> {err.hint}")


def _ibkr_availability_chip(state: IBKRAvailability) -> None:
    from aqp.ui.theme import chip_style

    tone = "success" if state.ok else "warning"
    icon = "✅" if state.ok else "⚠️"
    msg = state.message or "Probing TWS / IB Gateway…"
    css = ";".join(f"{k}:{v}" for k, v in chip_style(tone).items())
    solara.Markdown(f"<span style='{css}'>{icon} IBKR: {msg}</span>")


def _left_rail(
    *,
    catalog_rows: list[dict[str, Any]],
    selected: solara.Reactive[str],
    start: solara.Reactive[str],
    end: solara.Reactive[str],
    source_mode: solara.Reactive[str],
    ibkr_bar_size: solara.Reactive[str],
    ibkr_what_to_show: solara.Reactive[str],
    ibkr_use_rth: solara.Reactive[bool],
    overlays_raw: solara.Reactive[str],
    ibkr_state: IBKRAvailability,
    on_load,
    on_persist,
) -> None:
    with solara.Column(gap="12px"):
        with solara.Card("Symbol"):
            solara.InputText("vt_symbol (e.g. AAPL.NASDAQ)", value=selected)
            with solara.Row(gap="6px", style={"flex-wrap": "wrap"}):
                solara.InputText("start", value=start)
                solara.InputText("end", value=end)
            solara.Select(
                label="Source",
                value=source_mode,
                values=["Lake", "IBKR Preview", "IBKR Persist"],
            )
            if source_mode.value != "Lake":
                _ibkr_availability_chip(ibkr_state)
                with solara.Row(gap="6px", style={"flex-wrap": "wrap"}):
                    solara.Select(
                        label="IBKR bar size",
                        value=ibkr_bar_size,
                        values=[
                            "1 secs",
                            "5 secs",
                            "10 secs",
                            "15 secs",
                            "30 secs",
                            "1 min",
                            "2 mins",
                            "3 mins",
                            "5 mins",
                            "10 mins",
                            "15 mins",
                            "20 mins",
                            "30 mins",
                            "1 hour",
                            "2 hours",
                            "3 hours",
                            "4 hours",
                            "8 hours",
                            "1 day",
                        ],
                    )
                    solara.Select(
                        label="whatToShow",
                        value=ibkr_what_to_show,
                        values=["TRADES", "MIDPOINT", "BID", "ASK"],
                    )
                solara.Checkbox(label="IBKR useRTH", value=ibkr_use_rth)
            solara.InputText(
                "Overlays (e.g. SMA:20, EMA:26, RSI:14)", value=overlays_raw
            )
            disabled = (
                source_mode.value in {"IBKR Preview", "IBKR Persist"} and not ibkr_state.ok
            )
            if source_mode.value == "IBKR Persist":
                solara.Button(
                    "Persist to lake",
                    on_click=on_persist,
                    color="primary",
                    disabled=disabled,
                )
            else:
                solara.Button(
                    "Load",
                    on_click=on_load,
                    color="primary",
                    disabled=disabled,
                )
        if catalog_rows:
            with solara.Card("Top symbols"):
                with solara.Column(gap="4px"):
                    for row in catalog_rows[:10]:
                        vt = row.get("vt_symbol") or row.get("symbol") or "?"
                        rows = row.get("n_bars") or row.get("rows") or "?"
                        solara.Button(
                            label=f"{vt} ({rows} rows)",
                            on_click=lambda vt=vt: selected.set(vt),
                            outlined=True,
                            dense=True,
                        )


def _chart_tab(
    *,
    selected_symbol: str,
    bars: pd.DataFrame,
    stats: dict[str, Any],
    overlays_raw: str,
) -> None:
    if bars is None or bars.empty:
        solara.Markdown("_Pick a symbol and click **Load** to see its candlestick._")
        return
    with solara.Column(gap="12px"):
        _stats_strip(stats, bars, selected_symbol)
        overlays = _build_overlay_list(overlays_raw, bars)
        Candlestick(
            bars=bars,
            title=f"{selected_symbol} OHLCV",
            overlays=overlays,
            show_volume=True,
            height=540,
        )
        gaps = (stats or {}).get("gaps") or []
        if gaps:
            solara.Markdown(
                f"**{len(gaps)} missing trading days** (first 20): "
                f"{', '.join(gaps[:20])}"
            )


def _overlay_tab(
    *,
    overlay_symbols: solara.Reactive[str],
    overlay_df: pd.DataFrame,
    on_load,
) -> None:
    with solara.Column(gap="10px"):
        solara.Markdown(
            "Enter 2+ tickers to overlay their normalised closes (first bar = 1)."
        )
        solara.InputText(
            "symbols (comma-separated)", value=overlay_symbols
        )
        solara.Button("Load overlay", on_click=on_load)
        if overlay_df is None or overlay_df.empty:
            solara.Markdown("_No overlay loaded yet._")
            return
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            for sym, grp in overlay_df.groupby("vt_symbol"):
                fig.add_trace(
                    go.Scatter(
                        x=grp["timestamp"],
                        y=grp["normalized"],
                        mode="lines",
                        name=sym,
                    )
                )
            fig.update_layout(
                template=plotly_template(),
                title="Normalised price overlay",
                xaxis_title="date",
                yaxis_title="price / first close",
                height=420,
            )
            solara.FigurePlotly(fig)
        except Exception as exc:  # noqa: BLE001
            solara.Markdown(f"_Overlay error: {exc}_")


def _stats_strip(
    stats: dict[str, Any], bars: pd.DataFrame, vt: str
) -> None:
    last_close = float(bars["close"].iloc[-1]) if not bars.empty else None
    first_close = float(bars["close"].iloc[0]) if not bars.empty else None
    gain = None
    if last_close and first_close:
        gain = last_close / first_close - 1
    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile("Symbol", vt)
        first_hint = (
            stats.get("first_ts")
            or stats.get("first_bar")
            or "-"
        )
        last_hint = (
            stats.get("last_ts")
            or stats.get("last_bar")
            or "-"
        )
        MetricTile("Bars", len(bars), hint=f"{first_hint} → {last_hint}")
        MetricTile("Last close", last_close, unit="$")
        MetricTile("Window return", gain, unit="%", tone=_return_tone(gain))
        gaps = stats.get("gaps") or []
        MetricTile(
            "Gaps",
            len(gaps),
            tone="warning" if gaps else "success",
        )


def _return_tone(val: Any) -> str:
    if val is None:
        return "neutral"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "neutral"
    if v > 0:
        return "success"
    if v < 0:
        return "error"
    return "neutral"


def _apply_overlays(bars: pd.DataFrame, overlays_raw: str) -> pd.DataFrame:
    """Compute the raw overlay columns on the local bar slice.

    We use :class:`aqp.data.indicators_zoo.IndicatorZoo` here so the same
    indicator names that power the Indicator Builder page land in the Data
    Browser for free.
    """
    specs = [s.strip() for s in overlays_raw.split(",") if s.strip()]
    if not specs:
        return bars
    try:
        from aqp.data.indicators_zoo import IndicatorZoo

        return IndicatorZoo().transform(bars, indicators=specs)
    except Exception:
        return bars


def _build_overlay_list(overlays_raw: str, bars: pd.DataFrame) -> list[IndicatorOverlay]:
    """Convert ``"SMA:20, EMA:26, RSI:14"`` into :class:`IndicatorOverlay`."""
    from aqp.data.indicators_zoo import IndicatorSpec

    overlays: list[IndicatorOverlay] = []
    for raw in [s.strip() for s in overlays_raw.split(",") if s.strip()]:
        spec = IndicatorSpec.parse(raw)
        col = _column_for(spec)
        if col not in bars.columns:
            continue
        panel = _panel_for(spec.name)
        overlays.append(
            IndicatorOverlay(
                column=col,
                label=raw,
                panel=panel,
                width=1.4,
            )
        )
    return overlays


def _column_for(spec) -> str:
    if "period" in spec.kwargs:
        return f"{spec.name.lower()}_{spec.kwargs['period']}"
    if spec.kwargs:
        tail = "_".join(f"{k}{v}" for k, v in spec.kwargs.items())
        return f"{spec.name.lower()}_{tail}"
    return spec.name.lower()


def _panel_for(name: str) -> str:
    name = name.upper()
    if name in {"RSI", "STOCH", "MACD", "Z", "ATR"}:
        return "oscillator"
    return "price"


def _data_links_tab(vt_symbol: str) -> None:
    """Tab body: "what data do we have for this instrument?"

    Calls ``GET /instruments/{vt_symbol}/data`` which aggregates the
    ``data_links`` table across every registered source and domain. If
    nothing matches the symbol, we tell the user rather than rendering
    an empty frame.
    """
    if not vt_symbol:
        solara.Markdown("_Select a symbol on the left rail first._")
        return
    try:
        payload = get(f"/instruments/{vt_symbol}/data")
    except Exception as exc:  # noqa: BLE001
        solara.Error(f"Could not load data links: {exc}")
        return
    rows = list(payload.get("rows") or [])
    if not rows:
        solara.Markdown(
            "_No registered data linked to this instrument yet. Use the "
            "FRED / SEC / GDelt explorers to ingest data and tie it back via "
            "`/identifiers/link`._"
        )
        return
    solara.Markdown(f"## Data linked to `{vt_symbol}`")
    solara.DataFrame(pd.DataFrame(rows))
