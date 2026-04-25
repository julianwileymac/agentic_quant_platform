"""Celery tasks — offloaded compute (backtests, RL training, crews, ingestion)."""

from aqp.tasks.celery_app import celery_app

__all__ = ["celery_app"]
