"""Shared Pydantic types for the CRD mirror classes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class K8sMetadata(BaseModel):
    """Minimal k8s ObjectMeta mirror."""

    model_config = ConfigDict(extra="allow")

    name: str
    namespace: str = "default"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    uid: str | None = None
    resourceVersion: str | None = None
    generation: int | None = None
    creationTimestamp: datetime | None = None
    finalizers: list[str] = Field(default_factory=list)


class K8sCondition(BaseModel):
    """Standard k8s status condition."""

    model_config = ConfigDict(extra="allow")

    type: str
    status: str  # "True" / "False" / "Unknown"
    lastTransitionTime: datetime | None = None
    reason: str | None = None
    message: str | None = None
    observedGeneration: int | None = None


class CrdBase(BaseModel):
    """Common envelope: apiVersion + kind + metadata.

    Spec/status are added by each concrete CR subclass.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    apiVersion: str = "quantbot.io/v1"
    kind: str
    metadata: K8sMetadata


class OwnerReference(BaseModel):
    """K8s OwnerReference for ownerRefs on rendered objects."""

    apiVersion: str
    kind: str
    name: str
    uid: str
    controller: bool = True
    blockOwnerDeletion: bool = True


__all__ = ["CrdBase", "K8sCondition", "K8sMetadata", "OwnerReference"]
