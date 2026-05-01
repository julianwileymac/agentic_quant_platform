"""Celery tasks wrapping :mod:`aqp.data.pipelines.dataset_preset_pipelines`.

Each task is a thin shell over the corresponding pipeline function with
the standard AQP progress-bus contract (`emit` / `emit_done` /
`emit_error`).
"""
from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from aqp.data.pipelines.dataset_preset_pipelines import (
    ingest_akshare_china_panel,
    ingest_commodity_futures_panel,
    ingest_crypto_kucoin_intraday,
    ingest_eod_options_sample,
    ingest_etf_intraday_panel,
    ingest_finviz_screener,
    ingest_fred_macro_basket,
    ingest_lob_sample,
    ingest_sp500_daily,
)
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


def _wrap(task_self, name: str, fn, **kwargs):
    task_id = task_self.request.id if task_self else "local"
    emit(task_id, "started", f"{name} ingestion started", **kwargs)
    try:
        result = fn(**kwargs)
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s ingestion failed", name)
        emit_error(task_id, str(exc))
        raise


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_etf_intraday_panel")
def task_ingest_etf_intraday_panel(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "intraday_momentum_etf", ingest_etf_intraday_panel, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_commodity_futures_panel")
def task_ingest_commodity_futures_panel(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "commodity_futures_panel", ingest_commodity_futures_panel, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_akshare_china_panel")
def task_ingest_akshare_china_panel(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "china_a_shares_top200", ingest_akshare_china_panel, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_crypto_kucoin_intraday")
def task_ingest_crypto_kucoin_intraday(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "crypto_majors_intraday", ingest_crypto_kucoin_intraday, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_sp500_daily")
def task_ingest_sp500_daily(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "equity_universe_sp500_daily", ingest_sp500_daily, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_fred_macro_basket")
def task_ingest_fred_macro_basket(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "fred_macro_basket", ingest_fred_macro_basket, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_eod_options_sample")
def task_ingest_eod_options_sample(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "eod_options_chain_sample", ingest_eod_options_sample, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_lob_sample")
def task_ingest_lob_sample(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "lob_btcusdt_sample", ingest_lob_sample, **kwargs)


@shared_task(bind=True, name="aqp.tasks.dataset_preset_tasks.ingest_finviz_screener")
def task_ingest_finviz_screener(self, **kwargs: Any) -> dict[str, Any]:
    return _wrap(self, "finviz_screener", ingest_finviz_screener, **kwargs)


_TASKS_BY_PRESET = {
    "intraday_momentum_etf": task_ingest_etf_intraday_panel,
    "commodity_futures_panel": task_ingest_commodity_futures_panel,
    "china_a_shares_top200": task_ingest_akshare_china_panel,
    "crypto_majors_intraday": task_ingest_crypto_kucoin_intraday,
    "equity_universe_sp500_daily": task_ingest_sp500_daily,
    "fred_macro_basket": task_ingest_fred_macro_basket,
    "eod_options_chain_sample": task_ingest_eod_options_sample,
    "lob_btcusdt_sample": task_ingest_lob_sample,
}


def dispatch_preset_ingest(preset_name: str, **kwargs: Any):
    """Dispatch the right Celery task for a given preset name."""
    if preset_name not in _TASKS_BY_PRESET:
        raise KeyError(f"Unknown preset: {preset_name!r}; known={sorted(_TASKS_BY_PRESET)}")
    return _TASKS_BY_PRESET[preset_name].delay(**kwargs)
