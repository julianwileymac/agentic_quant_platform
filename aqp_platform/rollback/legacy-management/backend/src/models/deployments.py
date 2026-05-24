"""Deployment-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DeploymentStatus(str, Enum):
    """Deployment status enumeration."""

    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"
    SCALING = "Scaling"
    UPDATING = "Updating"


class DeploymentConfig(BaseModel):
    """Configuration for creating a new deployment."""

    name: str = Field(description="Deployment name")
    namespace: str = Field(default="default", description="Target namespace")
    image: str = Field(description="Container image")
    replicas: int = Field(default=1, ge=1, le=10, description="Number of replicas")
    port: Optional[int] = Field(default=None, description="Container port to expose")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    resources: Optional[dict[str, Any]] = Field(
        default=None,
        description="Resource requests/limits",
    )
    labels: dict[str, str] = Field(default_factory=dict, description="Labels to apply")
    node_selector: Optional[dict[str, str]] = Field(
        default=None,
        description="Node selector for scheduling",
    )
    create_service: bool = Field(default=False, description="Create a service for the deployment")
    service_type: str = Field(default="ClusterIP", description="Service type if creating service")


class DeploymentInfo(BaseModel):
    """Information about a deployment."""

    name: str = Field(description="Deployment name")
    namespace: str = Field(description="Deployment namespace")
    status: DeploymentStatus = Field(description="Deployment status")
    replicas: int = Field(description="Desired replicas")
    ready_replicas: int = Field(default=0, description="Ready replicas")
    available_replicas: int = Field(default=0, description="Available replicas")
    image: str = Field(description="Container image")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    labels: dict[str, str] = Field(default_factory=dict, description="Deployment labels")
    conditions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Deployment conditions",
    )


class ScaleRequest(BaseModel):
    """Request to scale a deployment."""

    replicas: int = Field(ge=0, le=20, description="Target number of replicas")


class RollbackRequest(BaseModel):
    """Request to rollback a deployment."""

    revision: Optional[int] = Field(
        default=None,
        description="Revision to rollback to. If None, rolls back to previous.",
    )
