"""Connector marketplace catalog.

Phase 5 seeds this with 50+ templates that back the Vite catalog
UI. Phase 1 ships the loader + a starter set of 10 financial
templates so the agent + operator paths can be exercised end to
end before Phase 5 fans out.
"""
from __future__ import annotations

from aqp_ingest.marketplace.loader import (
    Template,
    iter_templates,
    load_template,
    seed_templates_to_db,
)

__all__ = [
    "Template",
    "iter_templates",
    "load_template",
    "seed_templates_to_db",
]
