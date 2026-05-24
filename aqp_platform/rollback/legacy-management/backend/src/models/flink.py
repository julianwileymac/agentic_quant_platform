"""Flink-related Pydantic models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FlinkJobState(str, Enum):
    RUNNING = "running"
    SUSPENDED = "suspended"
    FAILED = "failed"
    FINISHED = "finished"
    UNKNOWN = "unknown"


class FlinkDeploymentInfo(BaseModel):
    name: str
    namespace: str
    image: str
    flink_version: str
    task_manager_replicas: int
    lifecycle_state: Optional[str] = None
    status: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class FlinkSessionJobInfo(BaseModel):
    name: str
    namespace: str
    deployment: str
    jar_uri: str
    entry_class: Optional[str] = None
    state: FlinkJobState
    parallelism: int = 1
    upgrade_mode: Optional[str] = None
    job_status: Dict[str, Any] = Field(default_factory=dict)
    savepoint_path: Optional[str] = None
    created_at: Optional[datetime] = None


class FlinkSessionJobCreate(BaseModel):
    name: str = Field(description="FlinkSessionJob name")
    jar_uri: str = Field(description="s3://... or http://... URL to the Flink job JAR / .py")
    entry_class: Optional[str] = Field(default=None, description="Java main class for the JAR")
    args: List[str] = Field(default_factory=list)
    parallelism: int = Field(default=1, ge=1)
    upgrade_mode: str = Field(default="savepoint")
    deployment: str = Field(
        default="flink-trading-session",
        description="Name of the target FlinkDeployment",
    )
    state: FlinkJobState = Field(default=FlinkJobState.SUSPENDED)


class FlinkSessionJobPatch(BaseModel):
    state: Optional[FlinkJobState] = None
    parallelism: Optional[int] = None
    upgrade_mode: Optional[str] = None
    savepoint_trigger: bool = Field(default=False, description="Trigger a savepoint via annotation")


class FlinkMetrics(BaseModel):
    job_id: str
    name: str
    state: str
    start_time: Optional[int] = None
    duration_ms: Optional[int] = None
    records_in: Optional[int] = None
    records_out: Optional[int] = None
    backpressure: Optional[Dict[str, Any]] = None
    checkpoints: Optional[Dict[str, Any]] = None
