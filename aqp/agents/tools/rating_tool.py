"""Rating5 convenience tool — exposes the ordinal rating scale to agents.

Used by roles that need to normalize free-form text like "strong buy",
"positive", or "bearish outlook" into the canonical :class:`Rating5`.
Returns the normalized value + signed numeric (-2..2) so downstream
prompts stay schema-faithful.
"""
from __future__ import annotations

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aqp.agents.trading.types import Rating5, parse_rating


class RatingInput(BaseModel):
    text: str = Field(..., description="Any free-form rating text to normalize")


class RatingTool(BaseTool):
    name: str = "normalize_rating"
    description: str = (
        "Normalize free-form rating text into the canonical 5-tier scale "
        "(strong_buy/buy/hold/sell/strong_sell) and the signed integer -2..2."
    )
    args_schema: type[BaseModel] = RatingInput

    def _run(self, text: str) -> str:  # type: ignore[override]
        r = parse_rating(text)
        return f"{r.value},{Rating5.numeric(r)}"
