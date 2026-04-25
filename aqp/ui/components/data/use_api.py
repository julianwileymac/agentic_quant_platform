"""`use_api` — Solara reactive hook around :mod:`aqp.ui.api_client`.

Every page in the old UI re-implemented the same pattern:

    state = solara.use_reactive(default)
    def refresh() -> None:
        try:
            state.set(get(path) or default)
        except Exception:
            state.set(default)
    solara.use_effect(refresh, [])

This hook hides all of that boilerplate behind a single call::

    data = use_api("/backtest/runs?limit=25", default=[])
    # data.value              -> the latest Python response (dict / list / ...)
    # data.loading            -> True while fetching
    # data.error              -> last exception string, or ""
    # data.last_updated       -> wall-clock seconds of the last ok fetch
    # data.refresh()          -> manual re-fetch
    # data.reactive           -> underlying solara.Reactive for binding widgets

When ``interval`` is set the hook polls the endpoint in the background, so
pages that need near-real-time refreshes (Portfolio, Live Market) do not have
to pipe their own timers.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import solara

from aqp.ui.api_client import get as _get

logger = logging.getLogger(__name__)


@dataclass
class _ApiResult:
    """Handle returned by :func:`use_api`.

    Exposes the Python values as properties (``value``, ``loading``,
    ``error``, ``last_updated``) so pages can write natural expressions
    like ``if result.loading: ...`` or ``rows = result.value or []``
    without having to remember to unwrap the underlying Reactive. The
    Reactive objects are still reachable via ``*_reactive`` for callers
    that need to pass them to widgets that accept a reactive directly.
    """

    refresh: Callable[[], None]
    reactive: solara.Reactive[Any]
    loading_reactive: solara.Reactive[bool]
    error_reactive: solara.Reactive[str]
    last_updated_reactive: solara.Reactive[float]

    @property
    def value(self) -> Any:
        return self.reactive.value

    @property
    def loading(self) -> bool:
        return bool(self.loading_reactive.value)

    @property
    def error(self) -> str:
        return str(self.error_reactive.value or "")

    @property
    def last_updated(self) -> float:
        return float(self.last_updated_reactive.value or 0.0)

    @property
    def ready(self) -> bool:
        return not self.loading and not self.error


def use_api(
    path: str | None,
    *,
    default: Any = None,
    interval: float | None = None,
    auto: bool = True,
    transform: Callable[[Any], Any] | None = None,
) -> _ApiResult:
    """Reactive GET wrapper.

    Parameters
    ----------
    path:
        API path to GET (e.g. ``"/backtest/runs?limit=25"``). ``None`` is a
        no-op and lets callers conditionally activate polling.
    default:
        Initial value + fallback used when the response is falsy or errors.
    interval:
        Seconds between background polls. ``None`` (default) fetches once on
        mount and then only on ``refresh()``.
    auto:
        If False, the initial fetch is skipped (page calls ``refresh()`` on
        demand, e.g. after a user clicks a button).
    transform:
        Optional post-processor applied to the JSON response.
    """
    value = solara.use_reactive(default)
    loading = solara.use_reactive(False)
    error = solara.use_reactive("")
    last_updated = solara.use_reactive(0.0)
    stop_flag = solara.use_reactive(False)

    def _fetch() -> None:
        if path is None:
            return
        loading.set(True)
        try:
            payload = _get(path)
            if transform is not None:
                payload = transform(payload)
            value.set(payload if payload is not None else default)
            error.set("")
            last_updated.set(time.time())
        except Exception as exc:  # noqa: BLE001
            logger.debug("use_api(%s) failed: %s", path, exc)
            error.set(str(exc))
        finally:
            loading.set(False)

    def _start_polling() -> Callable[[], None]:
        """Spawn a daemon thread that calls _fetch every ``interval`` seconds.

        Returns a teardown that signals the loop to exit.
        """
        if interval is None or path is None:
            if auto and path is not None:
                _fetch()
            return lambda: None

        if auto:
            _fetch()
        stop_flag.set(False)

        def _loop() -> None:
            while not stop_flag.value:
                time.sleep(float(interval))
                if stop_flag.value:
                    break
                _fetch()

        t = threading.Thread(target=_loop, daemon=True, name=f"use_api:{path}")
        t.start()
        return lambda: stop_flag.set(True)

    solara.use_effect(_start_polling, [path, interval, auto])

    return _ApiResult(
        refresh=_fetch,
        reactive=value,
        loading_reactive=loading,
        error_reactive=error,
        last_updated_reactive=last_updated,
    )


def use_api_action(
    *,
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> Callable[[Callable[[], Any]], Callable[[], None]]:
    """Decorator-style helper for 'run this side-effecting call and toast'.

    Usage::

        submit = use_api_action(on_success=lambda _: refresh_runs())

        def on_click() -> None:
            submit(lambda: post("/backtest/run", json={"config": cfg}))
    """
    pending = solara.use_reactive(False)

    def _runner(fn: Callable[[], Any]) -> Callable[[], None]:
        def _go() -> None:
            if pending.value:
                return
            pending.set(True)
            try:
                result = fn()
                if on_success is not None:
                    on_success(result)
            except Exception as exc:  # noqa: BLE001
                if on_error is not None:
                    on_error(str(exc))
                else:
                    solara.Error(str(exc))
            finally:
                pending.set(False)

        return _go

    return _runner
