"""FastAPI gateway + routes.

Imports are done lazily at call sites so that lightweight consumers (e.g.
``from aqp.api.schemas import BacktestRequest``) don't force FastAPI to load.
"""
