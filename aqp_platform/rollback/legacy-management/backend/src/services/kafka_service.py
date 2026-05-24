"""Kafka management service.

Wraps the Strimzi CRDs (``KafkaTopic``, ``KafkaUser``, ``KafkaConnector``) and
adjacent services (Kafka Bridge HTTP, Apicurio Schema Registry) so the
management API can expose granular Kafka operations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from ..config import Settings
from ..models.kafka import (
    KafkaConnectorInfo,
    KafkaConsumerGroupInfo,
    KafkaProduceRequest,
    KafkaTopicCreate,
    KafkaTopicInfo,
    KafkaUserCreate,
    KafkaUserInfo,
    SchemaRegistrySubject,
)
from ..telemetry.tracing import traced
from .kubernetes_service import KubernetesService

logger = logging.getLogger(__name__)

STRIMZI_GROUP = "kafka.strimzi.io"
STRIMZI_VERSION = "v1beta2"


class KafkaService:
    """Kafka control plane built on Strimzi CRDs + Bridge + Apicurio."""

    def __init__(self, settings: Settings, k8s_service: KubernetesService) -> None:
        self.settings = settings
        self.k8s = k8s_service

    # ------------------------------------------------------------------
    # Strimzi CRD helpers
    # ------------------------------------------------------------------

    @property
    def _custom(self) -> client.CustomObjectsApi:
        return self.k8s.custom_api

    def _list_crd(self, plural: str) -> List[Dict[str, Any]]:
        try:
            res = self._custom.list_namespaced_custom_object(
                group=STRIMZI_GROUP,
                version=STRIMZI_VERSION,
                namespace=self.settings.kafka.namespace,
                plural=plural,
            )
            return res.get("items", [])
        except ApiException as exc:
            logger.warning("list %s failed: %s", plural, exc)
            return []

    # ------------------------------------------------------------------
    # Topics
    # ------------------------------------------------------------------

    @traced("kafka.list_topics")
    async def list_topics(self) -> List[KafkaTopicInfo]:
        return [self._topic_from_item(i) for i in self._list_crd("kafkatopics")]

    @traced("kafka.get_topic")
    async def get_topic(self, name: str) -> Optional[KafkaTopicInfo]:
        try:
            item = self._custom.get_namespaced_custom_object(
                group=STRIMZI_GROUP,
                version=STRIMZI_VERSION,
                namespace=self.settings.kafka.namespace,
                plural="kafkatopics",
                name=name,
            )
            return self._topic_from_item(item)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    @traced("kafka.create_topic")
    async def create_topic(self, payload: KafkaTopicCreate) -> KafkaTopicInfo:
        body = {
            "apiVersion": f"{STRIMZI_GROUP}/{STRIMZI_VERSION}",
            "kind": "KafkaTopic",
            "metadata": {
                "name": payload.name,
                "namespace": self.settings.kafka.namespace,
                "labels": {"strimzi.io/cluster": payload.cluster},
            },
            "spec": {
                "partitions": payload.partitions,
                "replicas": payload.replicas,
                "config": payload.config,
            },
        }
        item = self._custom.create_namespaced_custom_object(
            group=STRIMZI_GROUP,
            version=STRIMZI_VERSION,
            namespace=self.settings.kafka.namespace,
            plural="kafkatopics",
            body=body,
        )
        return self._topic_from_item(item)

    @traced("kafka.delete_topic")
    async def delete_topic(self, name: str) -> None:
        try:
            self._custom.delete_namespaced_custom_object(
                group=STRIMZI_GROUP,
                version=STRIMZI_VERSION,
                namespace=self.settings.kafka.namespace,
                plural="kafkatopics",
                name=name,
            )
        except ApiException as exc:
            if exc.status != 404:
                raise

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    @traced("kafka.list_users")
    async def list_users(self) -> List[KafkaUserInfo]:
        return [self._user_from_item(i) for i in self._list_crd("kafkausers")]

    @traced("kafka.create_user")
    async def create_user(self, payload: KafkaUserCreate) -> KafkaUserInfo:
        body = {
            "apiVersion": f"{STRIMZI_GROUP}/{STRIMZI_VERSION}",
            "kind": "KafkaUser",
            "metadata": {
                "name": payload.name,
                "namespace": self.settings.kafka.namespace,
                "labels": {"strimzi.io/cluster": payload.cluster},
            },
            "spec": {
                "authentication": {"type": payload.authentication_type},
                "authorization": {"type": "simple", "acls": payload.acls},
            },
        }
        item = self._custom.create_namespaced_custom_object(
            group=STRIMZI_GROUP,
            version=STRIMZI_VERSION,
            namespace=self.settings.kafka.namespace,
            plural="kafkausers",
            body=body,
        )
        return self._user_from_item(item)

    @traced("kafka.delete_user")
    async def delete_user(self, name: str) -> None:
        try:
            self._custom.delete_namespaced_custom_object(
                group=STRIMZI_GROUP,
                version=STRIMZI_VERSION,
                namespace=self.settings.kafka.namespace,
                plural="kafkausers",
                name=name,
            )
        except ApiException as exc:
            if exc.status != 404:
                raise

    @traced("kafka.get_user_secret")
    async def get_user_secret(self, name: str) -> Optional[Dict[str, str]]:
        """Return the SCRAM secret materialized by the User Operator."""
        try:
            secret = self.k8s.core_api.read_namespaced_secret(
                name=name,
                namespace=self.settings.kafka.namespace,
            )
            if not secret.data:
                return None
            import base64

            return {k: base64.b64decode(v).decode("utf-8") for k, v in secret.data.items()}
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    # ------------------------------------------------------------------
    # Connectors
    # ------------------------------------------------------------------

    @traced("kafka.list_connectors")
    async def list_connectors(self) -> List[KafkaConnectorInfo]:
        return [self._connector_from_item(i) for i in self._list_crd("kafkaconnectors")]

    @traced("kafka.patch_connector_state")
    async def patch_connector_state(self, name: str, state: str) -> KafkaConnectorInfo:
        patch = [{"op": "replace", "path": "/spec/state", "value": state}]
        item = self._custom.patch_namespaced_custom_object(
            group=STRIMZI_GROUP,
            version=STRIMZI_VERSION,
            namespace=self.settings.kafka.namespace,
            plural="kafkaconnectors",
            name=name,
            body=patch,
            _content_type="application/json-patch+json",
        )
        return self._connector_from_item(item)

    # ------------------------------------------------------------------
    # Kafka Bridge produce proxy
    # ------------------------------------------------------------------

    @traced("kafka.produce_via_bridge")
    async def produce_via_bridge(self, topic: str, request: KafkaProduceRequest) -> Dict[str, Any]:
        if not self.settings.kafka.bridge_url:
            raise RuntimeError("Kafka Bridge URL not configured")
        url = f"{self.settings.kafka.bridge_url.rstrip('/')}/topics/{topic}"
        records = []
        for payload in request.records:
            item: Dict[str, Any] = {"value": payload}
            if request.key_field and request.key_field in payload:
                item["key"] = str(payload[request.key_field])
            records.append(item)
        async with httpx.AsyncClient(timeout=15.0) as http:
            res = await http.post(
                url,
                json={"records": records},
                headers={"Content-Type": "application/vnd.kafka.json.v2+json"},
            )
            res.raise_for_status()
            return res.json()

    # ------------------------------------------------------------------
    # Consumer groups (via AdminClient)
    # ------------------------------------------------------------------

    @traced("kafka.list_consumer_groups")
    async def list_consumer_groups(self) -> List[KafkaConsumerGroupInfo]:
        try:
            from confluent_kafka.admin import AdminClient, ConsumerGroupState
        except ImportError:
            logger.warning("confluent-kafka not installed; cannot inspect consumer groups.")
            return []

        admin = AdminClient({"bootstrap.servers": self.settings.kafka.bootstrap_plain})
        future = admin.list_consumer_groups(request_timeout=10)
        groups_result = future.result(timeout=10)
        results: List[KafkaConsumerGroupInfo] = []
        for valid in groups_result.valid:
            results.append(
                KafkaConsumerGroupInfo(
                    group_id=valid.group_id,
                    state=valid.state.name if valid.state else "UNKNOWN",
                    members=0,
                    topics=[],
                )
            )
        return results

    # ------------------------------------------------------------------
    # Schema registry proxy
    # ------------------------------------------------------------------

    @traced("kafka.list_schema_subjects")
    async def list_schema_subjects(self) -> List[SchemaRegistrySubject]:
        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.get(f"{self.settings.kafka.schema_registry_url}/search/artifacts")
            res.raise_for_status()
            body = res.json()
            artifacts = body.get("artifacts") if isinstance(body, dict) else body
            results: List[SchemaRegistrySubject] = []
            for art in artifacts or []:
                results.append(
                    SchemaRegistrySubject(
                        group_id=art.get("groupId", "default"),
                        artifact_id=art.get("id"),
                        version=str(art.get("version", "1")),
                        state=art.get("state"),
                        created_on=_parse_datetime(art.get("createdOn")),
                    )
                )
            return results

    # ------------------------------------------------------------------
    # Transformers
    # ------------------------------------------------------------------

    def _topic_from_item(self, item: Dict[str, Any]) -> KafkaTopicInfo:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        labels = meta.get("labels") or {}
        conditions = status.get("conditions") or []
        state = None
        for cond in conditions:
            if cond.get("type") == "Ready":
                state = cond.get("status")
                break
        return KafkaTopicInfo(
            name=meta.get("name", "?"),
            namespace=meta.get("namespace", self.settings.kafka.namespace),
            partitions=int(spec.get("partitions", 0)),
            replicas=int(spec.get("replicas", 0)),
            cluster=labels.get("strimzi.io/cluster", ""),
            status=state,
            config=spec.get("config", {}) or {},
            created_at=_parse_datetime(meta.get("creationTimestamp")),
        )

    def _user_from_item(self, item: Dict[str, Any]) -> KafkaUserInfo:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        labels = meta.get("labels") or {}
        auth = spec.get("authentication") or {}
        status = item.get("status") or {}
        return KafkaUserInfo(
            name=meta.get("name", "?"),
            namespace=meta.get("namespace", self.settings.kafka.namespace),
            cluster=labels.get("strimzi.io/cluster", ""),
            authentication_type=auth.get("type", "?"),
            secret_name=(status.get("secret") or meta.get("name")),
            status=_condition_state(status),
        )

    def _connector_from_item(self, item: Dict[str, Any]) -> KafkaConnectorInfo:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        labels = meta.get("labels") or {}
        status = item.get("status") or {}
        return KafkaConnectorInfo(
            name=meta.get("name", "?"),
            cluster=labels.get("strimzi.io/cluster", ""),
            connector_class=spec.get("class", "?"),
            tasks_max=int(spec.get("tasksMax", 1)),
            state=spec.get("state"),
            config=spec.get("config", {}),
            status=status,
        )


def _parse_datetime(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _condition_state(status: Dict[str, Any]) -> Optional[str]:
    for cond in status.get("conditions") or []:
        if cond.get("type") == "Ready":
            return cond.get("status")
    return None
