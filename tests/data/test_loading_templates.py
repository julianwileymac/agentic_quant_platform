from __future__ import annotations

import pytest

from aqp.data.loading_templates import (
    build_template_payload,
    get_loading_template,
    list_loading_templates,
)


def test_intraday_template_defaults_to_two_year_all_active_delta() -> None:
    template, payload = build_template_payload("alpha-vantage-intraday-2y-all-active")

    assert template.run_kind == "alpha_vantage_intraday_delta"
    assert template.endpoint == "/pipelines/alpha-vantage/intraday/delta"
    assert payload["plan"]["symbols"] == "all_active"
    assert payload["plan"]["lookback_months"] == 24
    assert payload["load"]["batch_size"] == 25


def test_template_overrides_are_deep_merged_without_mutating_defaults() -> None:
    _, payload = build_template_payload(
        "alpha-vantage-intraday-2y-all-active",
        {"plan": {"limit": 10}, "load": {"batch_size": 3}},
    )

    original = get_loading_template("alpha-vantage-intraday-2y-all-active")
    assert payload["plan"]["symbols"] == "all_active"
    assert payload["plan"]["limit"] == 10
    assert payload["load"]["batch_size"] == 3
    assert original.default_payload["plan"]["limit"] is None
    assert original.default_payload["load"]["batch_size"] == 25


def test_template_catalog_exposes_visual_flow_graphs() -> None:
    templates = list_loading_templates()

    assert {template.id for template in templates} >= {
        "alpha-vantage-intraday-2y-all-active",
        "local-path-director-iceberg",
    }
    assert all(template.flow_graph["domain"] == "data" for template in templates)


def test_unknown_template_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_loading_template("missing")
