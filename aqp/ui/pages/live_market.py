"""Live Market — unified per-security research view.

This page merges historical OHLCV charting, live streaming, fundamentals,
news, corporate actions and an optional watchlist tile strip into one
place.  Everything is focused on a single *security*: pick a ticker at
the top, choose filters, and drill into any of the tabs below.

Features
--------
* Filters: symbol, venue (``simulated | alpaca | ibkr | kafka``), bar
  size, lookback window, what-to-show (IBKR only), RTH, overlay
  toggles (SMA, EMA, Bollinger, VWAP) and panel toggles (Volume, RSI,
  MACD, Drawdown).
* Tabs: Chart, Fundamentals, News, Company, Corporate, Watchlist.
* KPI strip: last price, change %, market cap, volume, WS status chip.
* Robust loading: every fetch runs through a small helper that
  surfaces :class:`SecurityError` messages in an inline error card
  instead of disappearing silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import solara

from aqp.ui.api_client import delete, post
from aqp.ui.components import (
    LiveStreamer,
    MetricTile,
    StatsGrid,
    build_security_figure,
    use_api,
)
from aqp.ui.components.data.task_streamer import WSStatus
from aqp.ui.components.layout.tab_panel import TabPanel, TabSpec
from aqp.ui.layout.page_header import PageHeader
from aqp.ui.services.security import (
    IBKRAvailability,
    SecurityError,
    get_calendar,
    get_corporate,
    get_fundamentals,
    get_historical_bars,
    get_ibkr_availability,
    get_news,
    get_quote,
)
from aqp.ui.theme import PALETTE, chip_style


# ---------------------------------------------------------------------------
# Constants & static catalog
# ---------------------------------------------------------------------------


_VENUES = ["simulated", "alpaca", "ibkr", "kafka"]
_BAR_SIZES = [
    ("1 min", "1 min"),
    ("5 min", "5 mins"),
    ("15 min", "15 mins"),
    ("30 min", "30 mins"),
    ("1 hour", "1 hour"),
    ("1 day", "1 day"),
]
_WHAT_TO_SHOW = ["TRADES", "MIDPOINT", "BID", "ASK"]
_LOOKBACK_OPTIONS: list[tuple[str, timedelta | None]] = [
    ("1D", timedelta(days=1)),
    ("5D", timedelta(days=5)),
    ("1M", timedelta(days=31)),
    ("3M", timedelta(days=92)),
    ("6M", timedelta(days=183)),
    ("1Y", timedelta(days=365)),
    ("5Y", timedelta(days=365 * 5)),
    ("Max", None),
]
_OVERLAY_TOGGLES: list[tuple[str, str]] = [
    ("sma_20", "SMA(20)"),
    ("sma_50", "SMA(50)"),
    ("ema_20", "EMA(20)"),
    ("ema_50", "EMA(50)"),
    ("bbands", "Bollinger"),
    ("vwap", "VWAP"),
]
_PANEL_TOGGLES: list[tuple[str, str]] = [
    ("volume", "Volume"),
    ("rsi", "RSI(14)"),
    ("macd", "MACD"),
    ("drawdown", "Drawdown"),
]


# ---------------------------------------------------------------------------
# Reactive state containers
# ---------------------------------------------------------------------------


@dataclass
class ErrorState:
    title: str = ""
    detail: str = ""
    hint: str = ""
    code: str = ""

    def is_empty(self) -> bool:
        return not (self.title or self.detail)


@dataclass
class PageState:
    """Bundle for convenience — the actual state lives on reactives."""

    symbol: solara.Reactive[str] = field(default=None)  # type: ignore[assignment]
    venue: solara.Reactive[str] = field(default=None)   # type: ignore[assignment]
    bar_size: solara.Reactive[str] = field(default=None)  # type: ignore[assignment]
    lookback: solara.Reactive[str] = field(default=None)  # type: ignore[assignment]
    rth: solara.Reactive[bool] = field(default=None)      # type: ignore[assignment]
    what_to_show: solara.Reactive[str] = field(default=None)  # type: ignore[assignment]
    overlays: solara.Reactive[set[str]] = field(default=None)  # type: ignore[assignment]
    panels: solara.Reactive[set[str]] = field(default=None)    # type: ignore[assignment]
    watchlist: solara.Reactive[str] = field(default=None)      # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Page component
# ---------------------------------------------------------------------------


@solara.component
def Page() -> None:
    # State
    symbol = solara.use_reactive("AAPL")
    venue = solara.use_reactive("simulated")
    bar_size_label = solara.use_reactive("1 day")
    lookback_label = solara.use_reactive("6M")
    rth = solara.use_reactive(True)
    what_to_show = solara.use_reactive("TRADES")
    overlays: solara.Reactive[set[str]] = solara.use_reactive({"sma_20", "sma_50"})
    panels: solara.Reactive[set[str]] = solara.use_reactive({"volume"})
    watchlist = solara.use_reactive("AAPL,MSFT,SPY")

    focused_channel = solara.use_reactive("")
    focused_symbols: solara.Reactive[list[str]] = solara.use_reactive([])

    bars: solara.Reactive[pd.DataFrame] = solara.use_reactive(pd.DataFrame())
    bars_loading = solara.use_reactive(False)
    bars_error: solara.Reactive[ErrorState] = solara.use_reactive(ErrorState())
    quote: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    fundamentals: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    news: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    calendar: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    corporate: solara.Reactive[dict[str, Any]] = solara.use_reactive({})
    ibkr_state: solara.Reactive[IBKRAvailability] = solara.use_reactive(
        IBKRAvailability(ok=False, message="")
    )
    ws_status: solara.Reactive[WSStatus] = solara.use_reactive(WSStatus())

    subs = use_api("/live/subscriptions", default=[], interval=15.0)

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _clear_error() -> None:
        bars_error.set(ErrorState())

    def _set_error(title: str, err: Exception | SecurityError) -> None:
        if isinstance(err, SecurityError):
            bars_error.set(
                ErrorState(title=title, detail=err.detail, hint=err.hint, code=err.code)
            )
        else:
            bars_error.set(ErrorState(title=title, detail=str(err)))

    def _load_bars() -> None:
        sym = symbol.value.strip().upper()
        if not sym:
            return
        bar_size = _resolve_bar_size(bar_size_label.value)
        end = datetime.now(tz=UTC).replace(tzinfo=None)
        delta = _resolve_lookback(lookback_label.value)
        start = (end - delta).isoformat() if delta else None
        end_iso = end.isoformat()
        bars_loading.set(True)
        _clear_error()
        try:
            df = get_historical_bars(
                symbol=sym,
                venue=venue.value,
                start=start,
                end=end_iso,
                bar_size=bar_size,
                what_to_show=what_to_show.value,
                use_rth=rth.value,
                limit=5000,
            )
            bars.set(df)
        except SecurityError as exc:
            bars.set(pd.DataFrame())
            _set_error("Historical bars failed", exc)
        except Exception as exc:  # noqa: BLE001
            bars.set(pd.DataFrame())
            _set_error("Historical bars failed", exc)
        finally:
            bars_loading.set(False)

    def _load_quote() -> None:
        try:
            quote.set(get_quote(symbol.value))
        except SecurityError as exc:
            # Non-fatal — just blank the panel and note the reason.
            quote.set({"error": exc.detail})
        except Exception as exc:  # noqa: BLE001
            quote.set({"error": str(exc)})

    def _load_fundamentals() -> None:
        try:
            fundamentals.set(get_fundamentals(symbol.value))
        except SecurityError as exc:
            fundamentals.set({"error": exc.detail, "hint": exc.hint, "code": exc.code})
        except Exception as exc:  # noqa: BLE001
            fundamentals.set({"error": str(exc)})

    def _load_news() -> None:
        try:
            news.set(get_news(symbol.value, limit=20))
        except SecurityError as exc:
            news.set({"error": exc.detail, "hint": exc.hint})
        except Exception as exc:  # noqa: BLE001
            news.set({"error": str(exc)})

    def _load_calendar() -> None:
        try:
            calendar.set(get_calendar(symbol.value))
        except SecurityError as exc:
            calendar.set({"error": exc.detail})
        except Exception as exc:  # noqa: BLE001
            calendar.set({"error": str(exc)})

    def _load_corporate() -> None:
        try:
            corporate.set(get_corporate(symbol.value))
        except SecurityError as exc:
            corporate.set({"error": exc.detail})
        except Exception as exc:  # noqa: BLE001
            corporate.set({"error": str(exc)})

    def _probe_ibkr() -> None:
        ibkr_state.set(get_ibkr_availability())

    def _refresh_all() -> None:
        _load_bars()
        _load_quote()
        _load_fundamentals()
        _load_news()
        _load_calendar()
        _load_corporate()

    # Auto-load on mount + whenever the symbol or venue changes.
    solara.use_effect(
        _refresh_all,
        [symbol.value, venue.value, bar_size_label.value, lookback_label.value, rth.value, what_to_show.value],
    )
    solara.use_effect(_probe_ibkr, [venue.value])
    subs_key = tuple(
        (
            str(row.get("channel_id") or ""),
            tuple(row.get("symbols") or []),
        )
        for row in (subs.value or [])
    )

    def _sync_focus_from_subscriptions() -> None:
        rows = subs.value or []
        if not rows:
            if focused_channel.value:
                focused_channel.set("")
                ws_status.set(WSStatus.now("idle"))
            if focused_symbols.value:
                focused_symbols.set([])
            return
        current = focused_channel.value
        match = next((r for r in rows if (r.get("channel_id") or "") == current), None)
        if match is not None:
            symbols_for_current = list(match.get("symbols") or [])
            if symbols_for_current != focused_symbols.value:
                focused_symbols.set(symbols_for_current)
            return
        first = rows[0]
        next_channel = str(first.get("channel_id") or "")
        focused_channel.set(next_channel)
        focused_symbols.set(list(first.get("symbols") or []))

    solara.use_effect(_sync_focus_from_subscriptions, [subs_key])

    # ------------------------------------------------------------------
    # Subscription actions
    # ------------------------------------------------------------------

    def _subscribe() -> None:
        syms = _parse_watchlist(watchlist.value, focus=symbol.value)
        if not syms:
            return
        try:
            resp = post(
                "/live/subscribe",
                json={"venue": venue.value, "symbols": syms},
            )
            focused_channel.set(resp.get("channel_id", ""))
            focused_symbols.set(resp.get("symbols", syms))
            subs.refresh()
        except Exception as exc:  # noqa: BLE001
            _set_error("Could not subscribe to live feed", exc)

    def _focus_subscription(channel_id: str, symbols_for_channel: list[str]) -> None:
        focused_channel.set(channel_id)
        focused_symbols.set(list(symbols_for_channel))

    def _unsubscribe_channel(channel_id: str) -> None:
        if not channel_id:
            return
        try:
            delete(f"/live/subscribe/{channel_id}")
            current = subs.value or []
            remaining = [row for row in current if (row.get("channel_id") or "") != channel_id]
            if focused_channel.value == channel_id:
                if remaining:
                    first = remaining[0]
                    _focus_subscription(
                        str(first.get("channel_id") or ""),
                        list(first.get("symbols") or []),
                    )
                else:
                    focused_channel.set("")
                    focused_symbols.set([])
                    ws_status.set(WSStatus.now("idle"))
            subs.refresh()
        except Exception as exc:  # noqa: BLE001
            _set_error("Could not unsubscribe", exc)

    def _unsubscribe_focused() -> None:
        if not focused_channel.value:
            return
        _unsubscribe_channel(focused_channel.value)

    def _unsubscribe_all() -> None:
        channels = [str(row.get("channel_id") or "") for row in (subs.value or []) if row.get("channel_id")]
        if not channels:
            return
        failures: list[str] = []
        for channel_id in channels:
            try:
                delete(f"/live/subscribe/{channel_id}")
            except Exception:
                failures.append(channel_id)
        focused_channel.set("")
        focused_symbols.set([])
        ws_status.set(WSStatus.now("idle"))
        subs.refresh()
        if failures:
            _set_error(
                "Could not unsubscribe all channels",
                RuntimeError(f"Failed channels: {', '.join(failures)}"),
            )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_actions() -> None:
        with solara.Row(gap="6px", style={"align-items": "center"}):
            solara.Button(
                "Refresh",
                icon_name="mdi-refresh",
                outlined=True,
                on_click=_refresh_all,
                disabled=bars_loading.value,
            )

    PageHeader(
        title="Live Market",
        subtitle=(
            "Unified per-security view. Switch venues, overlay indicators, "
            "track fundamentals & news, and stream live bars — all scoped to "
            "one focus symbol."
        ),
        icon="📈",
        actions=_render_actions,
    )

    with solara.Column(gap="14px", style={"padding": "14px 20px"}):
        _kpi_strip(symbol.value, quote.value, fundamentals.value, ws_status.value, subs.value or [])

        _filters_card(
            symbol=symbol,
            venue=venue,
            bar_size=bar_size_label,
            lookback=lookback_label,
            rth=rth,
            what_to_show=what_to_show,
            watchlist=watchlist,
            overlays=overlays,
            panels=panels,
            ibkr_state=ibkr_state.value,
            on_refresh=_refresh_all,
            on_subscribe=_subscribe,
            on_unsubscribe=_unsubscribe_focused,
            active_channel=focused_channel.value,
        )

        if not bars_error.value.is_empty():
            _error_card(bars_error.value)

        def _chart_tab() -> None:
            _render_chart_tab(
                bars.value,
                overlays=overlays.value,
                panels=panels.value,
                symbol=symbol.value,
                loading=bars_loading.value,
            )

        def _fundamentals_tab() -> None:
            _render_fundamentals_tab(fundamentals.value, symbol.value)

        def _news_tab() -> None:
            _render_news_tab(news.value, symbol.value)

        def _company_tab() -> None:
            _render_company_tab(fundamentals.value, symbol.value)

        def _corporate_tab() -> None:
            _render_corporate_tab(corporate.value, calendar.value, symbol.value)

        def _watchlist_tab() -> None:
            _render_watchlist_tab(
                focused_channel=focused_channel.value,
                focused_symbols=focused_symbols.value,
                subs=subs.value or [],
                on_status=ws_status.set,
                on_focus=_focus_subscription,
                on_unsubscribe=_unsubscribe_channel,
                on_unsubscribe_all=_unsubscribe_all,
            )

        TabPanel(
            tabs=[
                TabSpec(key="chart", label="Chart", icon="📊", render=_chart_tab),
                TabSpec(key="fundamentals", label="Fundamentals", icon="📈", render=_fundamentals_tab),
                TabSpec(key="news", label="News", icon="📰", render=_news_tab),
                TabSpec(key="company", label="Company", icon="🏢", render=_company_tab),
                TabSpec(key="corporate", label="Corporate", icon="💰", render=_corporate_tab),
                TabSpec(key="watchlist", label="Watchlist", icon="📟", render=_watchlist_tab),
            ],
        )


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------


def _kpi_strip(
    symbol: str,
    quote: dict[str, Any],
    fundamentals: dict[str, Any],
    ws_status: WSStatus,
    subs: list[dict[str, Any]],
) -> None:
    change_pct = quote.get("change_pct")
    change = quote.get("change")
    tone = "neutral"
    if isinstance(change_pct, (int, float)):
        tone = "success" if change_pct >= 0 else "error"

    change_hint = ""
    if isinstance(change, (int, float)) and isinstance(change_pct, (int, float)):
        change_hint = f"{change:+,.2f} ({change_pct:+.2f}%)"

    with solara.Row(gap="8px", style={"flex-wrap": "wrap"}):
        MetricTile(
            "Focus",
            symbol,
            hint=f"WS {ws_status.state}" if ws_status.state else "—",
            tone="info",
        )
        MetricTile(
            "Last",
            _fmt_number(quote.get("last")),
            hint=change_hint or None,
            tone=tone,
        )
        MetricTile(
            "Volume",
            _fmt_number(quote.get("volume"), fmt=",.0f"),
            hint="Today",
        )
        MetricTile(
            "Market cap",
            _fmt_compact(fundamentals.get("market_cap")),
            hint=f"Sector: {fundamentals.get('sector') or '—'}",
        )
        MetricTile(
            "Subs",
            len(subs),
            hint="Active live feed channels",
            tone="success" if subs else "neutral",
        )


def _filters_card(
    *,
    symbol: solara.Reactive[str],
    venue: solara.Reactive[str],
    bar_size: solara.Reactive[str],
    lookback: solara.Reactive[str],
    rth: solara.Reactive[bool],
    what_to_show: solara.Reactive[str],
    watchlist: solara.Reactive[str],
    overlays: solara.Reactive[set[str]],
    panels: solara.Reactive[set[str]],
    ibkr_state: IBKRAvailability,
    on_refresh,
    on_subscribe,
    on_unsubscribe,
    active_channel: str,
) -> None:
    with solara.Card("Filters"):
        with solara.Column(gap="10px"):
            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                solara.InputText("Focus symbol", value=symbol, style={"min-width": "160px"})
                solara.Select(label="Venue", value=venue, values=_VENUES)
                solara.Select(
                    label="Bar size",
                    value=bar_size,
                    values=[label for label, _ in _BAR_SIZES],
                )
                solara.Select(
                    label="Lookback",
                    value=lookback,
                    values=[label for label, _ in _LOOKBACK_OPTIONS],
                )
                if venue.value == "ibkr":
                    solara.Select(
                        label="What to show",
                        value=what_to_show,
                        values=_WHAT_TO_SHOW,
                    )
                solara.Switch(label="Regular hours", value=rth)

            with solara.Row(gap="10px", style={"flex-wrap": "wrap", "align-items": "center"}):
                solara.Markdown(
                    f"<div style='font-size:11px;color:{PALETTE.text_muted};"
                    "text-transform:uppercase;letter-spacing:0.08em'>Overlays</div>"
                )
                for key, label in _OVERLAY_TOGGLES:
                    _chip_toggle(label, key, overlays)
                solara.Markdown(
                    f"<div style='font-size:11px;color:{PALETTE.text_muted};"
                    "text-transform:uppercase;letter-spacing:0.08em;margin-left:14px'>Panels</div>"
                )
                for key, label in _PANEL_TOGGLES:
                    _chip_toggle(label, key, panels)

            if venue.value == "ibkr":
                _render_ibkr_status(ibkr_state)

            with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
                solara.InputText(
                    "Watchlist (comma-separated)",
                    value=watchlist,
                    style={"min-width": "240px"},
                )
                solara.Button("Subscribe live", on_click=on_subscribe, color="primary")
                if active_channel:
                    solara.Button("Unsubscribe", on_click=on_unsubscribe, color="error", outlined=True)
                solara.Button("Refresh", on_click=on_refresh, outlined=True)


def _render_ibkr_status(ibkr_state: IBKRAvailability) -> None:
    tone = "success" if ibkr_state.ok else "warning"
    icon = "✅" if ibkr_state.ok else "⚠️"
    msg = ibkr_state.message or "Probing TWS…"
    style = chip_style(tone)
    css = ";".join(f"{k}:{v}" for k, v in style.items())
    solara.Markdown(
        f"<span style='{css}'>{icon} IBKR: {msg}</span>"
    )


def _chip_toggle(label: str, key: str, reactive: solara.Reactive[set[str]]) -> None:
    active = key in reactive.value

    def _toggle() -> None:
        s = set(reactive.value)
        if key in s:
            s.remove(key)
        else:
            s.add(key)
        reactive.set(s)

    tone = "info" if active else "neutral"
    s = chip_style(tone)
    border = PALETTE.accent if active else "rgba(148, 163, 184, 0.35)"
    s["cursor"] = "pointer"
    s["border"] = f"1px solid {border}"
    s["font-weight"] = "600"
    css = ";".join(f"{k}:{v}" for k, v in s.items())
    solara.Button(
        label=label,
        on_click=_toggle,
        text=True,
        style=css,
    )


def _error_card(err: ErrorState) -> None:
    bg = PALETTE.error
    fg = PALETTE.error_fg
    with solara.Div(
        style={
            "background": bg,
            "color": fg,
            "padding": "12px 16px",
            "border-radius": "10px",
            "border-left": f"4px solid {PALETTE.text_inverse}",
        },
    ):
        solara.Markdown(
            f"<strong>{err.title or 'Error'}</strong>"
            + (f" <span style='opacity:0.85'>[{err.code}]</span>" if err.code else "")
        )
        solara.Markdown(err.detail)
        if err.hint:
            solara.Markdown(f"<em>Hint:</em> {err.hint}")


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------


def _render_chart_tab(
    bars: pd.DataFrame,
    *,
    overlays: set[str],
    panels: set[str],
    symbol: str,
    loading: bool,
) -> None:
    if loading:
        solara.Markdown("_Loading historical bars…_")
        return
    if bars is None or bars.empty:
        solara.Markdown(
            "_No bars to chart yet. Try a different venue, bar size, or lookback window._"
        )
        return
    features = overlays | panels
    fig = build_security_figure(
        bars,
        features=features,
        title=f"{symbol} — {len(bars)} bars",
        height=640,
    )
    solara.FigurePlotly(fig)


def _render_fundamentals_tab(payload: dict[str, Any], symbol: str) -> None:
    if payload.get("error"):
        solara.Error(payload["error"])
        if payload.get("hint"):
            solara.Markdown(f"_Hint:_ {payload['hint']}")
        return
    if not payload:
        solara.Markdown("_Loading fundamentals…_")
        return

    # Render as a StatsGrid for quick scanning.
    rows = [
        ("Market cap", _fmt_compact(payload.get("market_cap"))),
        ("Enterprise value", _fmt_compact(payload.get("enterprise_value"))),
        ("Trailing P/E", _fmt_number(payload.get("trailing_pe"))),
        ("Forward P/E", _fmt_number(payload.get("forward_pe"))),
        ("Price / Book", _fmt_number(payload.get("price_to_book"))),
        ("Price / Sales", _fmt_number(payload.get("price_to_sales"))),
        ("PEG", _fmt_number(payload.get("peg_ratio"))),
        ("Dividend yield", _fmt_pct(payload.get("dividend_yield"))),
        ("Payout ratio", _fmt_pct(payload.get("payout_ratio"))),
        ("Beta", _fmt_number(payload.get("beta"))),
        ("52w high", _fmt_number(payload.get("fifty_two_week_high"))),
        ("52w low", _fmt_number(payload.get("fifty_two_week_low"))),
        ("50d avg", _fmt_number(payload.get("fifty_day_average"))),
        ("200d avg", _fmt_number(payload.get("two_hundred_day_average"))),
        ("Profit margin", _fmt_pct(payload.get("profit_margin"))),
        ("Operating margin", _fmt_pct(payload.get("operating_margin"))),
        ("Gross margin", _fmt_pct(payload.get("gross_margin"))),
        ("Revenue growth", _fmt_pct(payload.get("revenue_growth"))),
        ("Earnings growth", _fmt_pct(payload.get("earnings_growth"))),
        ("Return on equity", _fmt_pct(payload.get("return_on_equity"))),
        ("Return on assets", _fmt_pct(payload.get("return_on_assets"))),
    ]
    with solara.Card(f"{symbol} — fundamentals"):
        with solara.Row(style={"flex-wrap": "wrap", "gap": "8px"}):
            for label, value in rows:
                MetricTile(label, value or "—", tone="neutral", min_width="180px")


def _render_news_tab(payload: dict[str, Any], symbol: str) -> None:
    if payload.get("error"):
        solara.Error(payload["error"])
        return
    if not payload:
        solara.Markdown("_Loading headlines…_")
        return
    items = payload.get("items") or []
    if not items:
        solara.Markdown("_No news yet._")
        return
    with solara.Card(f"{symbol} — latest headlines ({len(items)})"):
        for item in items:
            _render_news_item(item)


def _render_news_item(item: dict[str, Any]) -> None:
    title = item.get("title") or "(no title)"
    publisher = item.get("publisher") or ""
    link = item.get("link")
    published = item.get("published")
    summary = item.get("summary") or ""
    ts_str = ""
    if published:
        try:
            ts_str = pd.Timestamp(published).strftime("%Y-%m-%d %H:%M")
        except Exception:
            ts_str = str(published)
    with solara.Div(
        style={
            "padding": "10px 0",
            "border-bottom": "1px solid rgba(148, 163, 184, 0.25)",
        }
    ):
        headline = f"**{title}**"
        if link:
            headline = f"[{title}]({link})"
        solara.Markdown(headline)
        meta_bits = []
        if publisher:
            meta_bits.append(publisher)
        if ts_str:
            meta_bits.append(ts_str)
        if meta_bits:
            solara.Markdown(
                f"<div style='font-size:12px;color:{PALETTE.text_muted}'>{' · '.join(meta_bits)}</div>"
            )
        if summary:
            snippet = summary[:280] + ("…" if len(summary) > 280 else "")
            solara.Markdown(
                f"<div style='font-size:13px;color:{PALETTE.text_secondary}'>{snippet}</div>"
            )


def _render_company_tab(payload: dict[str, Any], symbol: str) -> None:
    if payload.get("error"):
        solara.Error(payload["error"])
        return
    if not payload:
        solara.Markdown("_Loading company profile…_")
        return
    with solara.Card(f"{symbol} — {payload.get('name') or symbol}"):
        summary = payload.get("summary")
        if summary:
            solara.Markdown(summary)
        facts = [
            ("Sector", payload.get("sector")),
            ("Industry", payload.get("industry")),
            ("Country", payload.get("country")),
            ("Exchange", payload.get("exchange")),
            ("Currency", payload.get("currency")),
        ]
        with solara.Row(style={"flex-wrap": "wrap", "gap": "8px", "margin-top": "14px"}):
            for label, value in facts:
                MetricTile(label, value or "—", min_width="180px")
        if payload.get("website"):
            solara.Markdown(f"**Website:** [{payload['website']}]({payload['website']})")


def _render_corporate_tab(
    corporate: dict[str, Any],
    calendar: dict[str, Any],
    symbol: str,
) -> None:
    if corporate.get("error"):
        solara.Error(corporate["error"])
        return
    if not corporate:
        solara.Markdown("_Loading corporate actions…_")
        return

    with solara.Card(f"{symbol} — corporate actions"):
        # Earnings calendar summary on top.
        if calendar and not calendar.get("error"):
            _render_calendar(calendar)

        dividends = corporate.get("dividends") or []
        splits = corporate.get("splits") or []
        holders = corporate.get("institutional_holders") or []

        if dividends:
            solara.Markdown("**Dividends**")
            _render_events_timeline(dividends, value_label="$/share", fmt="{:.4f}")
        else:
            solara.Markdown("_No dividend history._")

        if splits:
            solara.Markdown("**Splits**")
            _render_events_timeline(splits, value_label="ratio", fmt="{:.4f}")

        if holders:
            solara.Markdown("**Top institutional holders**")
            import pandas as pd_

            df = pd_.DataFrame(holders)
            solara.DataFrame(df)


def _render_calendar(calendar: dict[str, Any]) -> None:
    earnings = calendar.get("earnings_date")
    ex_div = calendar.get("ex_dividend_date")
    pay = calendar.get("dividend_date")
    eps_avg = calendar.get("earnings_average")

    rows = [
        ("Next earnings", earnings if isinstance(earnings, str) else (earnings[0] if earnings else "—")),
        ("Ex-dividend", ex_div or "—"),
        ("Dividend pay date", pay or "—"),
        ("EPS (avg est.)", _fmt_number(eps_avg)),
    ]
    with solara.Row(style={"flex-wrap": "wrap", "gap": "8px", "margin-bottom": "12px"}):
        for label, value in rows:
            MetricTile(label, value or "—", tone="info", min_width="180px")


def _render_events_timeline(
    events: list[dict[str, Any]],
    *,
    value_label: str,
    fmt: str,
) -> None:
    import plotly.graph_objects as go

    from aqp.ui.theme import plotly_template

    if not events:
        return
    df = pd.DataFrame(events)
    if "date" not in df.columns:
        return
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    if df.empty:
        return
    fig = go.Figure(
        go.Bar(
            x=df["date"],
            y=df["value"],
            marker={"color": PALETTE.accent},
            name=value_label,
        )
    )
    fig.update_layout(
        template=plotly_template(),
        height=220,
        margin={"l": 40, "r": 20, "t": 30, "b": 30},
        showlegend=False,
    )
    solara.FigurePlotly(fig)


def _render_watchlist_tab(
    *,
    focused_channel: str,
    focused_symbols: list[str],
    subs: list[dict[str, Any]],
    on_status,
    on_focus,
    on_unsubscribe,
    on_unsubscribe_all,
) -> None:
    if not subs:
        solara.Markdown("_No active subscriptions yet. Click **Subscribe live** above to create one._")
        return
    with solara.Card("Active subscriptions"):
        with solara.Column(gap="8px"):
            for sub in subs:
                cid = str(sub.get("channel_id") or "")
                venue_name = str(sub.get("venue") or "?")
                symbols_for_channel = list(sub.get("symbols") or [])
                symbols_str = ", ".join(symbols_for_channel)
                is_focused = cid == focused_channel
                with solara.Row(
                    gap="8px",
                    style={
                        "align-items": "center",
                        "flex-wrap": "wrap",
                        "padding": "6px 0",
                        "border-bottom": "1px solid rgba(148, 163, 184, 0.2)",
                    },
                ):
                    marker = "▶" if is_focused else "•"
                    solara.Markdown(f"{marker} `{cid}` — **{venue_name}** — {symbols_str or '—'}")
                    if not is_focused:
                        solara.Button(
                            "Focus",
                            on_click=lambda cid=cid, syms=symbols_for_channel: on_focus(cid, syms),
                            dense=True,
                            outlined=True,
                        )
                    else:
                        solara.Button(
                            "Focused",
                            dense=True,
                            outlined=True,
                            disabled=True,
                        )
                    solara.Button(
                        "Unsubscribe",
                        on_click=lambda cid=cid: on_unsubscribe(cid),
                        dense=True,
                        outlined=True,
                        color="error",
                    )
            if len(subs) > 1:
                solara.Button(
                    "Unsubscribe all",
                    on_click=on_unsubscribe_all,
                    dense=True,
                    outlined=True,
                    color="error",
                )
    if not focused_channel:
        solara.Markdown("_Select a subscription above to start or resume live streaming tiles._")
        return
    with solara.Card(f"Live channel {focused_channel[:8]}…"):
        solara.Markdown(f"Symbols: **{', '.join(focused_symbols) or '—'}**")
        LiveStreamer(
            channel_id=focused_channel,
            symbols=focused_symbols,
            on_status=on_status,
        )


# ---------------------------------------------------------------------------
# Small formatting / parsing helpers
# ---------------------------------------------------------------------------


def _resolve_bar_size(label: str) -> str:
    for disp, api in _BAR_SIZES:
        if disp == label:
            return api
    return "1 day"


def _resolve_lookback(label: str) -> timedelta | None:
    for disp, delta in _LOOKBACK_OPTIONS:
        if disp == label:
            return delta
    return timedelta(days=183)


def _parse_watchlist(value: str, *, focus: str) -> list[str]:
    seen: list[str] = []
    for chunk in (value or "").split(","):
        t = chunk.strip().upper()
        if t and t not in seen:
            seen.append(t)
    focus_clean = (focus or "").strip().upper()
    if focus_clean and focus_clean not in seen:
        seen.insert(0, focus_clean)
    return seen


def _fmt_number(value: Any, *, fmt: str = ",.4g") -> str:
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:  # NaN
        return "—"
    return format(f, fmt)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:
        return "—"
    # yfinance returns either a fraction (0.18) or a percent (18); make a best guess.
    if abs(f) > 1.0:
        return f"{f:.2f}%"
    return f"{f * 100:.2f}%"


def _fmt_compact(value: Any) -> str:
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f:
        return "—"
    for unit, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(f) >= scale:
            return f"{f / scale:,.2f}{unit}"
    return f"{f:,.0f}"
