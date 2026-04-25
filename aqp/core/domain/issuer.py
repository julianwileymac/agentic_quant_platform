"""Corporate / issuer entity graph.

Every :class:`~aqp.core.domain.instrument.Equity` / :class:`Bond` / ``ETF``
points at an :class:`Issuer` row. The model is polymorphic so we can
represent traditional :class:`CorporateEntity` issuers, :class:`GovernmentEntity`
issuers (treasuries, central banks, municipalities), and :class:`Fund` issuers
(ETFs, mutual funds, sovereign funds) without shoe-horning them into a single
shape.

Fields mirror OpenBB's
``openbb_platform/core/openbb_core/provider/standard_models/equity_info.py``
``EquityInfoData`` schema so ingestion from any OpenBB-compatible provider is
a straight field mapping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as dateType
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aqp.core.domain.enums import IndustryClassificationScheme
from aqp.core.domain.identifiers import IdentifierScheme, IdentifierSet, IdentifierValue


# ---------------------------------------------------------------------------
# Classification primitives
# ---------------------------------------------------------------------------


class EntityKind(StrEnum):
    """Top-level issuer shape."""

    CORPORATE = "corporate"
    GOVERNMENT = "government"
    MUNICIPAL = "municipal"
    SUPRANATIONAL = "supranational"
    CENTRAL_BANK = "central_bank"
    FUND = "fund"
    INDEX_ADMINISTRATOR = "index_administrator"
    INDIVIDUAL = "individual"
    OTHER = "other"


class EntityRelationshipType(StrEnum):
    """How two entities are related."""

    PARENT = "parent"
    SUBSIDIARY = "subsidiary"
    LISTING_AGENT = "listing_agent"
    AUDITOR = "auditor"
    CUSTODIAN = "custodian"
    ISSUER_OF = "issuer_of"
    TRUSTEE_OF = "trustee_of"
    GUARANTEED_BY = "guaranteed_by"
    SPONSOR = "sponsor"
    MANAGES = "manages"
    SHAREHOLDER = "shareholder"
    COUNTERPARTY = "counterparty"
    RENAMED_TO = "renamed_to"
    MERGED_INTO = "merged_into"
    SPUN_OFF_FROM = "spun_off_from"


@dataclass(frozen=True)
class IndustryClassification:
    """One row in the entity's classification matrix.

    An issuer normally carries one entry per scheme (SIC + NAICS + GICS
    sector/industry/sub-industry), hierarchically ordered.
    """

    scheme: IndustryClassificationScheme
    code: str
    label: str = ""
    level: int = 1  # 1=sector, 2=industry_group, 3=industry, 4=sub_industry
    parent_code: str | None = None


@dataclass(frozen=True)
class Sector:
    """Canonical sector descriptor (GICS Level 1 or equivalent)."""

    code: str
    name: str
    scheme: IndustryClassificationScheme = IndustryClassificationScheme.GICS


@dataclass(frozen=True)
class Industry:
    """Canonical industry descriptor (GICS Level 3 or equivalent)."""

    code: str
    name: str
    sector: Sector | None = None
    scheme: IndustryClassificationScheme = IndustryClassificationScheme.GICS


@dataclass(frozen=True)
class Location:
    """Street / city / country address of an entity office."""

    country: str | None = None
    country_iso: str | None = None
    region: str | None = None
    state: str | None = None
    city: str | None = None
    postal_code: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    phone: str | None = None
    is_headquarters: bool = False
    is_mailing: bool = False


# ---------------------------------------------------------------------------
# Executives / governance
# ---------------------------------------------------------------------------


@dataclass
class KeyExecutive:
    """Officer, director, or other named principal of the issuer."""

    name: str
    title: str
    tenure_start: dateType | None = None
    tenure_end: dateType | None = None
    age: int | None = None
    gender: str | None = None
    compensation: Decimal | None = None
    compensation_currency: str | None = "USD"
    bio: str | None = None
    fiscal_year: int | None = None


@dataclass
class ExecutiveCompensation:
    """Year/executive-level compensation breakdown."""

    executive_name: str
    title: str | None = None
    fiscal_year: int | None = None
    salary: Decimal | None = None
    bonus: Decimal | None = None
    stock_awards: Decimal | None = None
    option_awards: Decimal | None = None
    non_equity_incentives: Decimal | None = None
    pension: Decimal | None = None
    other_compensation: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = "USD"


# ---------------------------------------------------------------------------
# IssuerRef — a cheap handle used by Instrument and events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IssuerRef:
    """Lightweight reference: just enough to identify + display an issuer.

    Attached to :class:`~aqp.core.domain.instrument.Equity` / ``Bond`` /
    :class:`~aqp.core.domain.events.FilingEvent` / etc. so the reading side
    doesn't have to load the full :class:`Issuer` record.
    """

    issuer_id: str
    name: str
    lei: str | None = None
    cik: str | None = None
    country: str | None = None


# ---------------------------------------------------------------------------
# Issuer hierarchy
# ---------------------------------------------------------------------------


@dataclass
class Issuer:
    """Polymorphic issuer record.

    Concrete subclasses add entity-kind-specific fields. The base class
    mirrors every field of OpenBB's ``EquityInfoData`` so ingestion from any
    OpenBB-compatible provider flows in without shape changes.
    """

    issuer_id: str
    name: str
    kind: EntityKind = EntityKind.CORPORATE

    # Identifiers (denormalized summary — authoritative graph lives in
    # ``identifier_links``).
    cik: str | None = None
    lei: str | None = None
    cusip: str | None = None
    isin: str | None = None
    figi: str | None = None
    permid: str | None = None
    gvkey: str | None = None
    irs_ein: str | None = None

    # Legal / incorporation
    legal_name: str | None = None
    entity_legal_form: str | None = None
    entity_status: str | None = None
    inc_state: str | None = None
    inc_country: str | None = None

    # Classification
    classifications: list[IndustryClassification] = field(default_factory=list)
    sector: Sector | None = None
    industry: Industry | None = None
    sic: int | None = None
    naics: str | None = None

    # Market footprint
    stock_exchange: str | None = None
    primary_listing: str | None = None
    currency: str | None = None
    is_listed: bool = True
    country: str | None = None
    employees: int | None = None

    # Content
    short_description: str | None = None
    long_description: str | None = None
    company_url: str | None = None
    template: str | None = None

    # Locations
    locations: list[Location] = field(default_factory=list)

    # Officers
    key_executives: list[KeyExecutive] = field(default_factory=list)
    ceo: str | None = None

    # Reference window
    latest_filing_date: dateType | None = None
    first_fundamental_date: dateType | None = None
    last_fundamental_date: dateType | None = None
    first_stock_price_date: dateType | None = None
    last_stock_price_date: dateType | None = None

    # Extra identifiers graph
    identifiers: IdentifierSet = field(default_factory=IdentifierSet)

    # Free-form overflow
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_ref(self) -> IssuerRef:
        return IssuerRef(
            issuer_id=self.issuer_id,
            name=self.name,
            lei=self.lei,
            cik=self.cik,
            country=self.country,
        )

    def add_identifier(
        self,
        scheme: IdentifierScheme | str,
        value: str,
        *,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> None:
        self.identifiers.add(
            IdentifierValue(
                scheme=scheme if isinstance(scheme, IdentifierScheme) else IdentifierScheme(scheme),
                value=value,
                confidence=confidence,
                source=source,
            )
        )


@dataclass
class CorporateEntity(Issuer):
    """Publicly traded corporation, private company, or partnership."""

    kind: EntityKind = EntityKind.CORPORATE
    ipo_date: dateType | None = None
    fiscal_year_end: str | None = None
    is_public: bool = True


@dataclass
class GovernmentEntity(Issuer):
    """Treasury, agency, municipality, or central bank."""

    kind: EntityKind = EntityKind.GOVERNMENT
    jurisdiction: str | None = None
    credit_rating_sp: str | None = None
    credit_rating_moodys: str | None = None
    credit_rating_fitch: str | None = None


@dataclass
class Fund(Issuer):
    """Fund wrapper issuer (ETF, mutual fund, closed-end fund, sovereign fund)."""

    kind: EntityKind = EntityKind.FUND
    fund_family: str | None = None
    manager: str | None = None
    aum: Decimal | None = None
    inception: dateType | None = None
    fund_type: str | None = None  # etf | mutual | closed_end | sovereign


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


@dataclass
class EntityRelationship:
    """Edge in the corporate graph.

    ``from_entity_id`` / ``to_entity_id`` are opaque string IDs; they can
    reference an ``issuers.id`` or an ``instruments.id`` depending on
    ``from_kind`` / ``to_kind``.
    """

    from_entity_id: str
    to_entity_id: str
    relationship_type: EntityRelationshipType
    from_kind: str = "issuer"
    to_kind: str = "issuer"
    ownership_pct: Decimal | None = None
    valid_from: dateType | None = None
    valid_to: dateType | None = None
    source: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
