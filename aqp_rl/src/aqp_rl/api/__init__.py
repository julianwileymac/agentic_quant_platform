"""FastAPI router(s) for ``aqp_rl``.

The router is mounted into the monolith FastAPI app at the same path
the legacy ``aqp.api.routes.rl`` router used (``/rl``), so the
operator UI and external clients are unaffected by the boundary
extraction.
"""
from __future__ import annotations
