"""Schema checks for paper config YAML metadata keys."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_PAPER_CONFIGS = [
    "alpaca_mean_rev.yaml",
    "ibkr_mean_rev.yaml",
    "avellaneda_stoikov_quotes.yaml",
    "lucic_tse_options.yaml",
    "tradier_rest.yaml",
]

_MODEL_URN_RE = re.compile(r"^urn:aqp:mlmodel:prod:.+$")
_PIPELINE_URN_RE = re.compile(r"^urn:aqp:pipeline:prod:.+$")


@pytest.mark.parametrize("filename", _PAPER_CONFIGS)
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
