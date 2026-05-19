"""Standard response envelope used by every control-plane API route."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorEnvelope(BaseModel):
    """Structured error returned in :attr:`ResponseEnvelope.error`."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(description="Machine-readable error code.")
    message: str = Field(description="Human-readable error message.")
    details: dict[str, Any] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel, Generic[T]):
    """Uniform ``{ "status": ..., "data": ..., "error": ... }`` envelope.

    Every mutating route on the control plane returns this shape so
    the rpi_k8s_sdk + the frontend can parse responses uniformly.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        description="One of 'ok', 'accepted', 'error'.",
    )
    data: T | None = None
    error: ErrorEnvelope | None = None


__all__ = ["ErrorEnvelope", "ResponseEnvelope"]
