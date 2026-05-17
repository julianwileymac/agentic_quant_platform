"""Extract entities from regulatory datasets (CFPB / FDA / USPTO).

Each row -> 0..N entity candidates:

- CFPB: complaint -> ``company`` entity (one per complaint).
- FDA applications: application -> ``drug`` + ``manufacturer`` entities.
- FDA recalls: recall -> ``product`` + ``manufacturer`` entities.
- USPTO patents: patent -> ``patent`` entity + ``assignee`` company.
- USPTO assignments: assignment -> ``assignee`` and ``assignor`` companies.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from aqp.data.entities.extractors.base import EntityCandidate, EntityExtractor


def _str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


class RegulatoryEntityExtractor(EntityExtractor):
    """Extract entities from regulatory dataset rows.

    ``flavor`` selects the source family: ``cfpb``, ``fda_applications``,
    ``fda_recalls``, ``uspto_patents``, ``uspto_assignments``.
    """

    name = "regulatory"
    extractor_id = "regulatory"

    def __init__(self, *, flavor: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        flavor = (flavor or "").lower()
        if flavor not in {
            "cfpb",
            "fda_applications",
            "fda_recalls",
            "uspto_patents",
            "uspto_assignments",
        }:
            raise ValueError(f"RegulatoryEntityExtractor: unknown flavor {flavor!r}")
        self.flavor = flavor
        self.extractor_id = f"regulatory.{flavor}"

    def extract(self, rows: Iterable[Any]) -> Iterator[EntityCandidate]:
        for row in rows:
            data = row if isinstance(row, dict) else dict(row)
            if self.flavor == "cfpb":
                yield from self._cfpb(data)
            elif self.flavor == "fda_applications":
                yield from self._fda_applications(data)
            elif self.flavor == "fda_recalls":
                yield from self._fda_recalls(data)
            elif self.flavor == "uspto_patents":
                yield from self._uspto_patents(data)
            elif self.flavor == "uspto_assignments":
                yield from self._uspto_assignments(data)

    # ------------------------------------------------------------------
    # CFPB
    # ------------------------------------------------------------------

    @staticmethod
    def _cfpb(data: dict[str, Any]) -> Iterator[EntityCandidate]:
        company = _str(data.get("company"))
        if not company:
            return
        product = _str(data.get("product"))
        sub_product = _str(data.get("sub_product"))
        complaint_id = _str(data.get("complaint_id"))
        yield EntityCandidate(
            kind="company",
            canonical_name=company,
            attributes={
                "industry": "consumer_finance",
                "last_complaint_id": complaint_id,
                "last_complaint_product": product,
                "last_complaint_sub_product": sub_product,
            },
            tags=["regulatory", "cfpb"],
            confidence=0.95,
        )

    # ------------------------------------------------------------------
    # FDA
    # ------------------------------------------------------------------

    @staticmethod
    def _fda_applications(data: dict[str, Any]) -> Iterator[EntityCandidate]:
        application_number = _str(data.get("application_number"))
        sponsor = _str(data.get("sponsor_name") or data.get("openfda_manufacturer_name"))
        brand_name = _str(data.get("brand_name") or data.get("openfda_brand_name"))
        generic = _str(data.get("openfda_generic_name") or data.get("generic_name"))

        if brand_name or generic:
            yield EntityCandidate(
                kind="drug",
                canonical_name=brand_name or generic,
                short_name=generic,
                primary_identifier=application_number,
                primary_identifier_scheme="fda_application_number",
                attributes={
                    "sponsor": sponsor,
                    "generic_name": generic,
                    "brand_name": brand_name,
                },
                tags=["regulatory", "fda"],
                confidence=0.9,
                relations=[
                    {
                        "predicate": "manufactured_by",
                        "object_id": "",  # patched downstream by enricher
                    }
                ]
                if sponsor
                else [],
            )
        if sponsor:
            yield EntityCandidate(
                kind="company",
                canonical_name=sponsor,
                tags=["regulatory", "fda", "manufacturer"],
                confidence=0.9,
            )

    @staticmethod
    def _fda_recalls(data: dict[str, Any]) -> Iterator[EntityCandidate]:
        recall_number = _str(data.get("recall_number"))
        product = _str(data.get("product_description"))
        firm = _str(data.get("recalling_firm"))
        if product:
            yield EntityCandidate(
                kind="product",
                canonical_name=product[:240],
                primary_identifier=recall_number,
                primary_identifier_scheme="fda_recall_number",
                attributes={
                    "recall_classification": _str(data.get("classification")),
                    "recall_initiation_date": _str(data.get("recall_initiation_date")),
                    "recalling_firm": firm,
                },
                tags=["regulatory", "fda", "recall"],
                confidence=0.85,
            )
        if firm:
            yield EntityCandidate(
                kind="company",
                canonical_name=firm,
                tags=["regulatory", "fda", "recalling_firm"],
                confidence=0.85,
            )

    # ------------------------------------------------------------------
    # USPTO
    # ------------------------------------------------------------------

    @staticmethod
    def _uspto_patents(data: dict[str, Any]) -> Iterator[EntityCandidate]:
        patent_number = _str(data.get("patent_number") or data.get("patent_id"))
        title = _str(data.get("patent_title") or data.get("title"))
        assignee = _str(
            data.get("assignee_organization")
            or data.get("assignee_first_name")
            or data.get("assignees")
        )
        if patent_number:
            yield EntityCandidate(
                kind="patent",
                canonical_name=title or patent_number,
                primary_identifier=patent_number,
                primary_identifier_scheme="uspto_patent",
                attributes={
                    "title": title,
                    "filing_date": _str(data.get("patent_date")),
                    "assignee": assignee,
                },
                tags=["regulatory", "uspto"],
                confidence=0.92,
                identifiers=[
                    {"scheme": "uspto_patent", "value": patent_number}
                ],
            )
        if assignee:
            yield EntityCandidate(
                kind="company",
                canonical_name=assignee,
                tags=["regulatory", "uspto", "assignee"],
                confidence=0.85,
            )

    @staticmethod
    def _uspto_assignments(data: dict[str, Any]) -> Iterator[EntityCandidate]:
        assignor = _str(
            data.get("assignor_name") or data.get("assignor")
        )
        assignee = _str(
            data.get("assignee_name") or data.get("assignee")
        )
        if assignor:
            yield EntityCandidate(
                kind="company",
                canonical_name=assignor,
                tags=["regulatory", "uspto", "assignor"],
                confidence=0.8,
            )
        if assignee:
            yield EntityCandidate(
                kind="company",
                canonical_name=assignee,
                tags=["regulatory", "uspto", "assignee"],
                confidence=0.8,
            )
