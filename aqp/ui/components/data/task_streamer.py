"""Live WebSocket streamers for task progress and market feeds.

- :class:`TaskStreamer` subscribes to ``/chat/stream/{task_id}`` for Celery
  progress frames (stage / message / timestamp / result).
- :class:`LiveStreamer` subscribes to ``/live/stream/{channel_id}`` for
  ticker bars.

Both components spin up a background thread using
:func:`aqp.ui.api_client.iter_ws` and push parsed JSON dicts into a
reactive state that the Solara renderer consumes.  The driver also
exposes a :class:`WSStatus` reactive so pages can render a connection
status chip (connected / reconnecting / polling / error).

Robustness highlights (v2):
* Exponential backoff reconnect (1s → 8s cap) so a brief network blip
  doesn't kick us straight into polling mode.
* Polling fallback only engages after the WS has been unhealthy for
  ``poll_grace_sec`` seconds (default 5s).  Previously any WS hiccup
  silently dropped us into polling forever.
* The stream driver pushes status transitions to an optional callback so
  the caller can surface them in the UI.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import solara

from aqp.ui.api_client import get, iter_ws
from aqp.ui.theme import PALETTE, chip_style

logger = logging.getLogger(__name__)


WSStatusLiteral = Literal["idle", "connecting", "connected", "reconnecting", "polling", "error"]


@dataclass
class WSStatus:
    """Lightweight status record the driver emits on every transition."""

    state: WSStatusLiteral = "idle"
    detail: str = ""
    since_ms: float = 0.0

    @classmethod
    def now(cls, state: WSStatusLiteral, detail: str = "") -> "WSStatus":
        return cls(state=state, detail=detail, since_ms=time.time() * 1000.0)


# ---------------------------------------------------------------------------
# Shared subscription driver
# ---------------------------------------------------------------------------


def _spawn_stream(
    path: str,
    on_message: Callable[[dict[str, Any]], None],
    stop_flag: solara.Reactive,
    poll_fallback: Callable[[], list[dict[str, Any]]] | None = None,
    poll_interval: float = 2.0,
    on_status: Callable[[WSStatus], None] | None = None,
    *,
    max_reconnect_sec: float = 8.0,
    poll_grace_sec: float = 5.0,
    max_reconnects: int = 4,
) -> Callable[[], None]:
    """Start a daemon thread that drains the stream and stops on ``stop_flag``.

    Returns a teardown that signals the thread to exit.  Status
    transitions are pushed to ``on_status`` so the caller can render a
    chip.
    """
    stop_flag.set(False)

    def _emit_status(status: WSStatus) -> None:
        if on_status is not None:
            try:
                on_status(status)
            except Exception:  # pragma: no cover - defensive
                logger.debug("ws status callback raised", exc_info=True)

    def _run() -> None:
        attempt = 0
        ever_healthy = False
        _emit_status(WSStatus.now("connecting", path))
        while not stop_flag.value:
            this_run_messages = 0
            try:
                iterator = iter_ws(path)
                for msg in iterator:
                    if stop_flag.value:
                        break
                    # ``iter_ws`` yields {"stage": "error", ...} when the
                    # websocket closes unexpectedly; treat it as a signal
                    # to reconnect rather than a real event.
                    if isinstance(msg, dict) and msg.get("stage") == "error":
                        logger.debug("ws reported error, will reconnect: %s", msg.get("message"))
                        break
                    this_run_messages += 1
                    if not ever_healthy:
                        ever_healthy = True
                        attempt = 0
                        _emit_status(WSStatus.now("connected", path))
                    on_message(msg)
                    if msg.get("stage") in {"done", "error"}:
                        _emit_status(WSStatus.now("connected", "stream complete"))
                        return
            except Exception as exc:  # noqa: BLE001
                logger.debug("stream %s errored: %s", path, exc, exc_info=True)

            if stop_flag.value:
                break

            # If the WS never delivered a single message and we have a
            # polling fallback, fall through immediately.  This matches
            # the legacy "ws dead → poll" behavior that callers rely on
            # when the ``websockets`` package is absent.
            if not ever_healthy and this_run_messages == 0 and poll_fallback is not None:
                _emit_status(
                    WSStatus.now(
                        "polling",
                        f"WebSocket unavailable; polling every {poll_interval:.1f}s",
                    )
                )
                _poll_loop(poll_fallback, stop_flag, poll_interval, on_message)
                return

            attempt += 1
            if attempt > max_reconnects:
                if poll_fallback is not None:
                    _emit_status(
                        WSStatus.now(
                            "polling",
                            f"WebSocket unavailable after {attempt} attempts; falling back to REST polling",
                        )
                    )
                    _poll_loop(poll_fallback, stop_flag, poll_interval, on_message)
                else:
                    _emit_status(WSStatus.now("error", "WebSocket unavailable and no polling fallback"))
                return

            backoff = min(max_reconnect_sec, 1.0 * (2 ** (attempt - 1)))
            _emit_status(
                WSStatus.now(
                    "reconnecting",
                    f"attempt {attempt}/{max_reconnects} — retrying in {backoff:.1f}s",
                )
            )
            grace = time.monotonic() + backoff
            while not stop_flag.value and time.monotonic() < grace:
                time.sleep(0.1)

            # If the WS has been dead for longer than ``poll_grace_sec``
            # and we still have a polling fallback, let the UI start
            # seeing data even while we keep trying to reconnect.
            if (
                poll_fallback is not None
                and backoff >= poll_grace_sec
                and not stop_flag.value
            ):
                _emit_status(
                    WSStatus.now(
                        "polling",
                        f"polling every {poll_interval:.1f}s while waiting for WebSocket to recover",
                    )
                )
                try:
                    rows = poll_fallback() or []
                    for row in rows:
                        on_message(row)
                except Exception:
                    logger.debug("poll fallback errored", exc_info=True)

    t = threading.Thread(target=_run, daemon=True, name=f"stream:{path}")
    t.start()
    return lambda: stop_flag.set(True)


def _poll_loop(
    fetch: Callable[[], list[dict[str, Any]]],
    stop_flag: solara.Reactive,
    interval: float,
    on_message: Callable[[dict[str, Any]], None],
) -> None:
    seen = 0
    while not stop_flag.value:
        try:
            rows = fetch() or []
        except Exception:
            rows = []
        for row in rows[seen:]:
            on_message(row)
        seen = len(rows)
        time.sleep(interval)


# ---------------------------------------------------------------------------
# TaskStreamer — Celery progress view for backtests, factor evals, ML training
# ---------------------------------------------------------------------------


@solara.component
def TaskStreamer(
    task_id: str | None,
    *,
    title: str = "Task progress",
    auto_connect: bool = True,
    max_events: int = 200,
    empty: str = "_Waiting for the worker…_",
    show_result: bool = True,
) -> None:
    """Render a live task-progress viewer.

    Events are shown newest-last with timestamp + stage chip + message. When
    the task publishes a ``done`` frame, its ``result`` payload is rendered
    as JSON underneath for quick inspection.
    """
    events: solara.Reactive[list[dict[str, Any]]] = solara.use_reactive([])
    stop_flag = solara.use_reactive(False)
    connected = solara.use_reactive(False)

    def _on_message(msg: dict[str, Any]) -> None:
        connected.set(True)
        buf = [*events.value, msg]
        if len(buf) > max_events:
            buf = buf[-max_events:]
        events.set(buf)

    def _connect() -> Callable[[], None]:
        if not task_id or not auto_connect:
            return lambda: None
        events.set([])
        connected.set(False)
        return _spawn_stream(f"/chat/stream/{task_id}", _on_message, stop_flag)

    solara.use_effect(_connect, [task_id, auto_connect])

    with solara.Card(title):
        if not task_id:
            solara.Markdown("_No task id yet._")
            return
        status = "LIVE" if connected.value else "CONNECTING"
        solara.Markdown(
            f"**<span style='{_chip_html('success' if connected.value else 'info')}'>{status}</span>**"
            f" &nbsp;task `{task_id}`"
        )
        if not events.value:
            solara.Markdown(empty)
        else:
            with solara.Column(
                style={
                    "max-height": "360px",
                    "overflow-y": "auto",
                    "font-family": "ui-monospace, SFMono-Regular, Menlo, monospace",
                    "font-size": "12px",
                }
            ):
                for e in events.value:
                    solara.Markdown(_format_event(e))
        last = events.value[-1] if events.value else {}
        if show_result and last.get("stage") == "done" and last.get("result"):
            solara.Markdown("**Result**")
            import json

            solara.Markdown(
                f"```json\n{json.dumps(last['result'], indent=2, default=str)}\n```"
            )


def _format_event(e: dict[str, Any]) -> str:
    ts = e.get("timestamp")
    ts_str = ""
    if ts:
        try:
            ts_str = datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
        except Exception:
            ts_str = str(ts)
    stage = (e.get("stage") or "info").upper()
    message = e.get("message") or e.get("raw") or ""
    chip = _stage_chip(stage)
    return f"`{ts_str}` {chip} {message}"


def _stage_chip(stage: str) -> str:
    tone_map = {
        "START": "info",
        "RUNNING": "info",
        "DONE": "success",
        "ERROR": "error",
        "HEARTBEAT": "neutral",
    }
    return (
        f"<span style='{_chip_html(tone_map.get(stage, 'neutral'))}'>{stage}</span>"
    )


def _chip_html(tone: str) -> str:
    s = chip_style(tone)
    return ";".join(f"{k}:{v}" for k, v in s.items())


# ---------------------------------------------------------------------------
# LiveStreamer — bars tiles for Live Market page
# ---------------------------------------------------------------------------


@solara.component
def LiveStreamer(
    channel_id: str | None,
    *,
    symbols: list[str] | None = None,
    tile_width: str = "180px",
    auto_connect: bool = True,
    on_status: Callable[[WSStatus], None] | None = None,
    on_bar: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Render a grid of live price tiles for each symbol in ``symbols``.

    Subscribes to ``/live/stream/{channel_id}`` and, when a bar arrives, the
    tile for that ``vt_symbol`` flashes and updates its close + volume.

    Callers can pass ``on_bar`` to react to each incoming bar (e.g. to
    append it onto a chart), and ``on_status`` to render a connection
    chip.  The component falls back to polling the REST endpoint if the
    WebSocket stays unavailable after 4 retries.
    """
    prices: solara.Reactive[dict[str, dict[str, Any]]] = solara.use_reactive({})
    stop_flag = solara.use_reactive(False)
    flash: solara.Reactive[str] = solara.use_reactive("")

    def _on_message(msg: dict[str, Any]) -> None:
        vt = msg.get("vt_symbol") or msg.get("symbol")
        if not vt:
            return
        new_map = dict(prices.value)
        new_map[vt] = msg
        prices.set(new_map)
        flash.set(str(vt))
        if on_bar is not None:
            try:
                on_bar(msg)
            except Exception:  # pragma: no cover
                logger.debug("on_bar callback raised", exc_info=True)

    def _poll_once() -> list[dict[str, Any]]:
        """Fallback: pull the latest bar per subscription symbol."""
        try:
            subs = get("/live/subscriptions") or []
        except Exception:
            return []
        sub = next((s for s in subs if s.get("channel_id") == channel_id), None)
        if not sub:
            return []
        rows: list[dict[str, Any]] = []
        for s in sub.get("symbols") or []:
            try:
                payload = get(f"/data/{s}/bars?limit=1")
                bars = payload.get("bars") or []
                if bars:
                    last = bars[-1]
                    rows.append({"vt_symbol": s, **last})
            except Exception:
                continue
        return rows

    def _connect() -> Callable[[], None]:
        if not channel_id or not auto_connect:
            return lambda: None
        prices.set({})
        return _spawn_stream(
            f"/live/stream/{channel_id}",
            _on_message,
            stop_flag,
            poll_fallback=_poll_once,
            poll_interval=3.0,
            on_status=on_status,
        )

    solara.use_effect(_connect, [channel_id, auto_connect])

    if not channel_id:
        solara.Markdown("_Subscribe to a venue first._")
        return

    keys = list(symbols or list(prices.value.keys()))
    if not keys:
        solara.Markdown("_Waiting for the first bar…_")
        return

    with solara.Row(gap="10px", style={"flex-wrap": "wrap"}):
        for sym in keys:
            bar = prices.value.get(sym, {})
            close = bar.get("close")
            volume = bar.get("volume")
            ts = bar.get("timestamp")
            highlighted = sym == flash.value
            _tile(sym, close, volume, ts, highlighted, tile_width)


def _tile(
    symbol: str,
    close: Any,
    volume: Any,
    ts: Any,
    highlighted: bool,
    width: str,
) -> None:
    # Tile background flips to the accent colour on flash so you can see
    # which ticker just updated.  Both colours satisfy AA contrast vs
    # ``text_inverse``.
    bg = PALETTE.accent if highlighted else PALETTE.bg_panel
    border = PALETTE.accent_hover if highlighted else "rgba(148, 163, 184, 0.35)"
    with solara.Column(
        gap="2px",
        style={
            "background": bg,
            "color": PALETTE.text_inverse,
            "padding": "10px 12px",
            "border-radius": "10px",
            "min-width": width,
            "border": f"1px solid {border}",
            "box-shadow": "0 1px 2px rgba(15, 23, 42, 0.25)",
            "transition": "background 0.25s ease",
        },
    ):
        solara.Markdown(
            f"<div style='font-size:12px;text-transform:uppercase;letter-spacing:0.06em;opacity:0.95;font-weight:700'>{symbol}</div>"
        )
        solara.Markdown(
            f"<div style='font-size:22px;font-weight:700;color:{PALETTE.text_inverse}'>{_fmt(close)}</div>"
        )
        solara.Markdown(
            f"<div style='font-size:11px;opacity:0.88'>vol {_fmt(volume, plain=True)} @ {ts or '—'}</div>"
        )


def _fmt(value: Any, *, plain: bool = False) -> str:
    if value is None or value == "-":
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if plain:
        return f"{f:,.0f}"
    return f"{f:,.4g}"
