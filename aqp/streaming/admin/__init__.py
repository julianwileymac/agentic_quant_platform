"""Native Kafka and Flink admin services.

Backs the ``/streaming/kafka`` and ``/streaming/flink`` API routes
plus the SinkRegistry / Producer supervisor flows. Both modules are
optional — they degrade to "unavailable" when the underlying SDKs
(``confluent-kafka.admin``, ``aiokafka``, ``kubernetes``) are not
installed or when the cluster is unreachable, so AQP keeps booting
in a paper-only environment.
"""
from aqp.streaming.admin.flink_admin import (
    FlinkAdminError,
    FlinkAdminUnavailableError,
    FlinkJobOverview,
    FlinkRestClient,
    FlinkSessionJob,
    FlinkSessionJobK8s,
    get_flink_rest_client,
    get_flink_session_jobs,
)
from aqp.streaming.admin.kafka_admin import (
    KafkaAdminError,
    KafkaAdminUnavailableError,
    NativeKafkaAdmin,
    get_kafka_admin,
)
from aqp.streaming.admin.schema_registry import (
    ApicurioSchemaRegistry,
    get_schema_registry,
)

__all__ = [
    "ApicurioSchemaRegistry",
    "FlinkAdminError",
    "FlinkAdminUnavailableError",
    "FlinkJobOverview",
    "FlinkRestClient",
    "FlinkSessionJob",
    "FlinkSessionJobK8s",
    "KafkaAdminError",
    "KafkaAdminUnavailableError",
    "NativeKafkaAdmin",
    "get_flink_rest_client",
    "get_flink_session_jobs",
    "get_kafka_admin",
    "get_schema_registry",
]
