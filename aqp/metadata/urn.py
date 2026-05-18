"""URN helpers for AQP metadata entities."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

logger = logging.getLogger(__name__)

URN_PATTERN = re.compile(
    r"^urn:aqp:[a-z][a-z0-9_]{0,63}:(prod|staging|dev|test):[A-Za-z0-9._:-]{1,200}$"
)


@dataclass(frozen=True, slots=True)
class AqpUrn:
    """Parsed URN components."""

    entity_type: str
    env: str
    id: str

    def __str__(self) -> str:
        return f"urn:aqp:{self.entity_type}:{self.env}:{self.id}"


def make_urn(entity_type: str, env: str, id_: str) -> str:
    """Build and validate a canonical AQP URN."""
    entity_type_clean = str(entity_type or "").strip().lower()
    env_clean = str(env or "").strip().lower()
    id_clean = str(id_ or "").strip()
    candidate = f"urn:aqp:{entity_type_clean}:{env_clean}:{id_clean}"
    if not URN_PATTERN.fullmatch(candidate):
        raise ValueError(
            "Invalid AQP URN parts: "
            f"entity_type={entity_type!r}, env={env!r}, id={id_!r}. "
            "Expected entity_type=[a-z][a-z0-9_]{0,63}, "
            "env in {prod,staging,dev,test}, "
            "and id in [A-Za-z0-9._:-]{1,200}."
        )
    return candidate


def parse_urn(urn: str) -> AqpUrn:
    """Parse an AQP URN into structured components."""
    urn_clean = str(urn or "").strip()
    if not URN_PATTERN.fullmatch(urn_clean):
        raise ValueError(
            "Invalid AQP URN: "
            f"{urn!r}. Expected format "
            "'urn:aqp:<entity_type>:<env>:<id>' with env in "
            "{prod,staging,dev,test}."
        )
    _, _, entity_type, env, entity_id = urn_clean.split(":", 4)
    return AqpUrn(entity_type=entity_type, env=env, id=entity_id)


def to_datahub_urn(aqp_urn: str, *, platform: str = "aqp") -> str:
    """Convert an AQP URN into a DataHub-compatible URN."""
    parsed = parse_urn(aqp_urn)
    platform_clean = str(platform or "aqp").strip() or "aqp"
    encoded_id = quote(parsed.id, safe="._:-")
    if parsed.entity_type == "dataset":
        return (
            f"urn:li:dataset:(urn:li:dataPlatform:{platform_clean},"
            f"{encoded_id},{parsed.env.upper()})"
        )
    return f"urn:li:{parsed.entity_type}:{encoded_id}"


__all__ = ["AqpUrn", "URN_PATTERN", "make_urn", "parse_urn", "to_datahub_urn"]

