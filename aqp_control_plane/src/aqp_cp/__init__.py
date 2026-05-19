"""AQP control plane — isolated FastAPI micro-project.

Depends ONLY on ``aqp_platform_core`` (the shared library) — never on
``aqp.*``. See ADR 005.
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
