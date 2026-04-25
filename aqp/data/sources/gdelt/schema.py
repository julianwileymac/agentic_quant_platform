"""GDelt GKG 2.0 CSV column schema.

Reference: http://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf

The raw files are tab-separated with 27 columns. GDelt uses nested
semicolon- and pound-delimited sub-fields for multi-valued fields
(e.g. themes, persons, organizations); we keep them as strings here
and parse them lazily in :mod:`aqp.data.sources.gdelt.subject_filter`.
"""
from __future__ import annotations

GKG_COLUMNS: tuple[str, ...] = (
    "gkg_record_id",
    "v21_date",
    "v2_source_collection_identifier",
    "v2_source_common_name",
    "v2_document_identifier",
    "v1_counts",
    "v21_counts",
    "v1_themes",
    "v2_enhanced_themes",
    "v1_locations",
    "v2_enhanced_locations",
    "v1_persons",
    "v2_enhanced_persons",
    "v1_organizations",
    "v2_enhanced_organizations",
    "v15_tone",
    "v21_enhanced_dates",
    "v2_gcam",
    "v21_sharing_image",
    "v21_related_images",
    "v21_social_image_embeds",
    "v21_social_video_embeds",
    "v21_quotations",
    "v21_all_names",
    "v21_amounts",
    "v21_translation_info",
    "v2_extras_xml",
)


GKG_NUMERIC_COLUMNS: tuple[str, ...] = ()
"""Columns that should be coerced to numeric during ingest (none at raw level)."""


V15_TONE_FIELDS: tuple[str, ...] = (
    "tone",
    "positive_score",
    "negative_score",
    "polarity",
    "activity_reference_density",
    "self_group_reference_density",
    "word_count",
)


def parse_tone(tone: str | None) -> dict[str, float]:
    """Parse the comma-separated ``v15_tone`` field into a dict."""
    if not tone:
        return {}
    parts = [p.strip() for p in str(tone).split(",")]
    out: dict[str, float] = {}
    for name, value in zip(V15_TONE_FIELDS, parts, strict=False):
        try:
            out[name] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def split_semicolon(value: str | None) -> list[str]:
    """Split the GDelt ``foo;bar;baz`` multi-value format into a clean list."""
    if not value:
        return []
    return [part.strip() for part in str(value).split(";") if part and part.strip()]
