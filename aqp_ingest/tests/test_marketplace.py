"""Marketplace loader tests — Phase 1 seeded templates."""
from __future__ import annotations

from aqp_ingest.marketplace.loader import iter_templates


def test_loader_yields_phase1_templates():
    slugs = {tmpl.slug for tmpl in iter_templates()}
    # Phase 1 ships at minimum these 10 templates per plan section 5.
    expected = {
        "polygon-aggregates",
        "polygon-trades",
        "polygon-quotes",
        "polygon-options-chain",
        "databento-historical",
        "alpaca-bars",
        "alpaca-trades",
        "iex-cloud-snapshots",
        "bloomberg-bpipe",
        "fred-economic-series",
    }
    missing = expected - slugs
    assert missing == set(), f"missing templates: {missing}"


def test_templates_have_required_fields():
    for tmpl in iter_templates():
        assert tmpl.slug
        assert tmpl.display_name
        assert tmpl.kind in {"low_code_yaml", "python_cdk", "cdc"}
        assert tmpl.spec
