"""MarketDataFeed CR — venue feed configuration."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class SecretRef(BaseModel):
    name: str
    key: str = "credentials"


class MarketDataFeedSpecField(BaseModel):
    model_config = ConfigDict(extra="allow")
    venue: str = ""
    transport: Literal["fix", "websocket", "rest", "grpc", "onchain"] = "websocket"
    adapter: str = ""  # registry alias for the concrete adapter class
    endpoint: str = ""
    credentialsRef: SecretRef | None = None
    subscriptions: list[dict[str, Any]] = Field(default_factory=list)
    rateLimitPerSecond: int | None = None
    backoff: dict[str, Any] = Field(default_factory=dict)
    extras: dict[str, Any] = Field(default_factory=dict)


class MarketDataFeedStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    connected: bool = False
    lastEventAt: str | None = None


class MarketDataFeedCR(CrdBase):
    kind: Literal["MarketDataFeed"] = "MarketDataFeed"
    spec: MarketDataFeedSpecField = Field(default_factory=MarketDataFeedSpecField)
    status: MarketDataFeedStatus | None = None


__all__ = ["MarketDataFeedCR", "MarketDataFeedSpecField", "MarketDataFeedStatus", "SecretRef"]
