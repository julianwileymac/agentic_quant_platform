"""FastAPI router(s) for ``aqp_models``.

Both routers (``ml`` and ``analytics_ml``) are mounted into the monolith
FastAPI app at the same paths the legacy ``aqp.api.routes.ml`` and
``aqp.api.routes.analytics_ml`` routers used, so the operator UI and
external clients are unaffected by the boundary extraction.
"""
from __future__ import annotations
