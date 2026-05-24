"""Synchronous Kafka admin operations.

Wraps ``confluent_kafka.admin.AdminClient`` with a small, task-oriented
surface (list topics, describe topic, list groups, describe lag).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KafkaAdmin:
    def __init__(
        self,
        *,
        bootstrap: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_protocol: str = "SASL_SSL",
        sasl_mechanism: str = "SCRAM-SHA-512",
        ssl_cafile: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        try:
            from confluent_kafka.admin import AdminClient
        except ImportError as exc:
            raise ImportError(
                "confluent-kafka is required; install with `pip install rpi_k8s_sdk[streaming]`"
            ) from exc

        cfg: Dict[str, Any] = {"bootstrap.servers": bootstrap}
        if username:
            cfg.update(
                {
                    "security.protocol": security_protocol,
                    "sasl.mechanism": sasl_mechanism,
                    "sasl.username": username,
                    "sasl.password": password or "",
                }
            )
        if ssl_cafile:
            cfg["ssl.ca.location"] = ssl_cafile

        self._client = AdminClient(cfg)
        self._timeout = timeout

    def list_topics(self, include_internal: bool = False) -> List[str]:
        meta = self._client.list_topics(timeout=self._timeout)
        return [
            name for name in meta.topics
            if include_internal or not name.startswith("__")
        ]

    def describe_topic(self, name: str) -> Dict[str, Any]:
        meta = self._client.list_topics(topic=name, timeout=self._timeout)
        topic = meta.topics.get(name)
        if topic is None:
            raise KeyError(name)
        return {
            "topic": name,
            "partitions": [
                {
                    "id": p.id,
                    "leader": p.leader,
                    "replicas": list(p.replicas),
                    "isr": list(p.isrs),
                }
                for p in topic.partitions.values()
            ],
        }

    def list_consumer_groups(self) -> List[str]:
        future = self._client.list_consumer_groups(request_timeout=self._timeout)
        result = future.result(timeout=self._timeout)
        return [g.group_id for g in result.valid]
