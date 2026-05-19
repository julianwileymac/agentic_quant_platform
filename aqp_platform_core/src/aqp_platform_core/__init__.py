"""Shared, dependency-free models + ABCs for the AQP platform.

This package is the foundation depended on by both ``aqp/`` (the AQP
monolith) and ``aqp_control_plane/`` (the isolated control-plane
micro-project). It MUST NOT import from ``aqp.*`` — that's enforced
by CI and protects the strict-isolation contract of
``aqp_control_plane``.
"""
from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
