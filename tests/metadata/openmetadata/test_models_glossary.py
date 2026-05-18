"""Tests for OpenMetadata glossary/document models."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from aqp.metadata.openmetadata import Document


def _valid_document_payload() -> dict[str, object]:
    """Return a valid payload for `Document` tests."""
    return {
        "urn": "urn:aqp:document:dev:fomc_minutes_2026_05",
        "instrument_urn": "urn:aqp:instrument:dev:SPY",
        "valid_from": datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        "valid_to": datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
        "glossary_terms": ["carry", "term premium"],
        "content_text": "Federal Open Market Committee minutes...",
        "source_url": "https://example.com/fomc-minutes",
        "language": "en",
    }


def test_document_valid_payload_roundtrip_dates_and_terms() -> None:
    """Document should preserve datetime fields and glossary terms."""
    payload = _valid_document_payload()
    document = Document(**payload)

    assert document.valid_from == payload["valid_from"]
    assert document.valid_to == payload["valid_to"]
    assert document.glossary_terms == ["carry", "term premium"]


def test_document_rejects_invalid_urn() -> None:
    """Primary document URN must match the AQP URN format."""
    payload = _valid_document_payload()
    payload["urn"] = "urn:foo:bar"

    with pytest.raises(ValidationError):
        Document(**payload)
