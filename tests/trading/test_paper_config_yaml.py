"""Schema checks for paper config YAML metadata keys."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_PAPER_CONFIG_URNS: dict[str, dict[str, str]] = {
    "alpaca_mean_rev.yaml": {
        "model_urn": "urn:aqp:mlmodel:prod:alpaca_mean_reversion_v1",
        "pipeline_urn": "urn:aqp:pipeline:prod:alpaca_mean_reversion_loop",
    },
    "ibkr_mean_rev.yaml": {
        "model_urn": "urn:aqp:mlmodel:prod:ibkr_mean_reversion_v1",
        "pipeline_urn": "urn:aqp:pipeline:prod:ibkr_mean_reversion_loop",
    },
    "avellaneda_stoikov_quotes.yaml": {
        "model_urn": "urn:aqp:mlmodel:prod:avellaneda_stoikov_v1",
        "pipeline_urn": "urn:aqp:pipeline:prod:avellaneda_stoikov_quotes_loop",
    },
    "lucic_tse_options.yaml": {
        "model_urn": "urn:aqp:mlmodel:prod:lucic_tse_options_v1",
        "pipeline_urn": "urn:aqp:pipeline:prod:lucic_tse_options_loop",
    },
    "tradier_rest.yaml": {
        "model_urn": "urn:aqp:mlmodel:prod:tradier_rest_baseline_v1",
        "pipeline_urn": "urn:aqp:pipeline:prod:tradier_rest_loop",
    },
}

_MODEL_URN_RE = re.compile(r"^urn:aqp:mlmodel:prod:[a-z0-9_]+$")
_PIPELINE_URN_RE = re.compile(r"^urn:aqp:pipeline:prod:[a-z0-9_]+$")


@pytest.mark.parametrize("filename", sorted(_PAPER_CONFIG_URNS.keys()))
def test_paper_yaml_declares_required_metadata_urn_keys(filename: str) -> None:
    """Each paper config should declare non-null production model/pipeline URNs."""
    path = Path("configs/paper") / filename
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(payload, dict)

    session = payload.get("session")
    assert isinstance(session, dict)
    assert "model_urn" in session
    assert "pipeline_urn" in session
    assert session.get("model_urn")
    assert session.get("pipeline_urn")
    assert _MODEL_URN_RE.fullmatch(str(session.get("model_urn")))
    assert _PIPELINE_URN_RE.fullmatch(str(session.get("pipeline_urn")))

    # Roundtrip confirms the parser/dumper keeps the strict keys intact.
    dumped = yaml.safe_dump(payload, sort_keys=False)
    roundtrip = yaml.safe_load(dumped) or {}
    roundtrip_session = roundtrip.get("session")
    assert isinstance(roundtrip_session, dict)
    assert roundtrip_session.get("model_urn") == session.get("model_urn")
    assert roundtrip_session.get("pipeline_urn") == session.get("pipeline_urn")


def test_paper_yaml_urns_match_seed_migration_0049() -> None:
    """Paper YAML URNs must align with alembic 0049 seed migration tuples."""
    for filename, expected in _PAPER_CONFIG_URNS.items():
        path = Path("configs/paper") / filename
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        assert isinstance(payload, dict)
        session = payload.get("session")
        assert isinstance(session, dict)
        assert session.get("model_urn") == expected["model_urn"]
        assert session.get("pipeline_urn") == expected["pipeline_urn"]
