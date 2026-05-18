"""Tests for Document aspect emission in RAG indexers."""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from aqp.metadata.writer import AspectWriterControl
from aqp.persistence.models import Base, DatasetCatalog, Instrument
from aqp.persistence.models_aspects import EntityAspect, MetadataEntity
from aqp.persistence.models_entities import Industry, Issuer, Sector
from aqp.persistence.models_entity_registry import EntityRow
from aqp.persistence.models_lineage import DataLineageEvent
from aqp.rag import document_aspects
from aqp.rag.document_aspects import emit_document_aspect, extract_glossary_terms


@pytest.fixture
def aspect_db(monkeypatch: pytest.MonkeyPatch) -> sessionmaker:
    """Create a hermetic sqlite metadata store for aspect tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            MetadataEntity.__table__,
            EntityAspect.__table__,
            DatasetCatalog.__table__,
            Sector.__table__,
            Industry.__table__,
            Issuer.__table__,
            Instrument.__table__,
            EntityRow.__table__,
            DataLineageEvent.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    @contextmanager
    def _patched_get_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(document_aspects, "get_session", _patched_get_session)
    return SessionLocal


def test_emit_document_aspect_writes_first_version(aspect_db: sessionmaker) -> None:
    """Writing one document payload creates version 1 with glossary terms."""
    urn = emit_document_aspect(
        document_id="alpha-doc-1",
        content_text="Sharpe Ratio and Momentum support this idea.",
        glossary_terms=["Sharpe Ratio", "Momentum"],
        source_url="https://example.com/doc/alpha",
    )

    with aspect_db() as session:
        row = (
            session.execute(
                select(EntityAspect).where(
                    EntityAspect.urn == urn,
                    EntityAspect.aspect_name == "documentMetadata",
                )
            )
            .scalars()
            .one()
        )
        assert row.version == 1
        assert "Sharpe Ratio" in (row.payload.get("glossary_terms") or [])
        assert "Momentum" in (row.payload.get("glossary_terms") or [])


def test_emit_document_aspect_deduplicates_identical_payload(aspect_db: sessionmaker) -> None:
    """Repeated identical payload returns same URN and one stored row."""
    first_urn = emit_document_aspect(
        document_id="same-doc",
        content_text="Volatility remains elevated.",
    )
    second_urn = emit_document_aspect(
        document_id="same-doc",
        content_text="Volatility remains elevated.",
    )

    assert first_urn == second_urn
    with aspect_db() as session:
        count = session.execute(
            select(func.count(EntityAspect.id)).where(
                EntityAspect.urn == first_urn,
                EntityAspect.aspect_name == "documentMetadata",
            )
        ).scalar_one()
        assert int(count) == 1


def test_emit_document_aspect_bumps_version_on_payload_change(aspect_db: sessionmaker) -> None:
    """Changed payload for same document_id creates a new aspect version."""
    urn = emit_document_aspect(
        document_id="versioned-doc",
        content_text="Initial text for this document.",
    )
    same_urn = emit_document_aspect(
        document_id="versioned-doc",
        content_text="Updated text for this document.",
    )

    assert urn == same_urn
    with aspect_db() as session:
        versions = (
            session.execute(
                select(EntityAspect.version)
                .where(
                    EntityAspect.urn == urn,
                    EntityAspect.aspect_name == "documentMetadata",
                )
                .order_by(EntityAspect.version.asc())
            )
            .scalars()
            .all()
        )
        assert versions == [1, 2]


def test_extract_glossary_terms_detects_expected_terms() -> None:
    """Keyword extractor returns canonical glossary terms for matches."""
    text = (
        "The Sharpe Ratio of the portfolio measured against realized "
        "volatility shows healthy momentum."
    )
    terms = extract_glossary_terms(text)
    assert "Sharpe Ratio" in terms
    assert "Realized Volatility" in terms
    assert "Momentum" in terms


def test_emit_document_aspect_respects_suppression(aspect_db: sessionmaker) -> None:
    """Suppression context disables all document aspect writes."""
    with AspectWriterControl.suppress():
        emit_document_aspect(
            document_id="suppressed-doc",
            content_text="This should never persist.",
            glossary_terms=["Volatility"],
        )

    with aspect_db() as session:
        count = session.execute(select(func.count(EntityAspect.id))).scalar_one()
        assert int(count) == 0
