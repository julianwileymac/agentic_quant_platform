"""Kafka-related Pydantic models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KafkaTopicSpec(BaseModel):
    partitions: int = Field(default=6, ge=1)
    replicas: int = Field(default=1, ge=1)
    config: Dict[str, Any] = Field(default_factory=dict)


class KafkaTopicInfo(BaseModel):
    name: str
    namespace: str
    partitions: int
    replicas: int
    cluster: str
    status: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class KafkaTopicCreate(BaseModel):
    name: str = Field(description="Topic name, e.g. market.sample.v1")
    partitions: int = Field(default=6, ge=1)
    replicas: int = Field(default=1, ge=1)
    cluster: str = Field(default="trading-kafka")
    config: Dict[str, str] = Field(default_factory=dict)


class KafkaUserCreate(BaseModel):
    name: str = Field(description="KafkaUser name")
    cluster: str = Field(default="trading-kafka")
    authentication_type: str = Field(default="scram-sha-512")
    acls: List[Dict[str, Any]] = Field(default_factory=list)


class KafkaUserInfo(BaseModel):
    name: str
    namespace: str
    cluster: str
    authentication_type: str
    secret_name: Optional[str] = None
    status: Optional[str] = None


class KafkaConsumerGroupInfo(BaseModel):
    group_id: str
    state: str
    members: int
    topics: List[str]
    lag: Dict[str, int] = Field(default_factory=dict, description="lag per topic:partition")


class KafkaConnectorInfo(BaseModel):
    name: str
    cluster: str
    connector_class: str
    tasks_max: int
    state: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    status: Optional[Dict[str, Any]] = None


class KafkaProduceRequest(BaseModel):
    """Body for POST /kafka/topics/{name}/produce - proxied to the Bridge."""

    records: List[Dict[str, Any]]
    key_field: Optional[str] = Field(default=None, description="Field on each record to use as key")


class SchemaRegistrySubject(BaseModel):
    group_id: str
    artifact_id: str
    version: str
    state: Optional[str] = None
    created_on: Optional[datetime] = None
