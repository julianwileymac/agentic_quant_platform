"""HoodieStreamer / HudiSparkStreaming Kubernetes launcher.

Phase 2e of the AQP infra-expansion plan. The launcher submits
``SparkApplication`` custom resources to the Spark Operator (deployed
in the ``aqp-mlops`` namespace) so HoodieStreamer runs continuously
against a Kafka / Redpanda topic, materialising Hudi tables under
``s3://aqp-lakehouse/hudi/<namespace>/<table>/``.

This module never executes Spark in-process. It RENDERS a
``SparkApplication`` manifest and submits it via the existing
:class:`aqp.kubernetes.KubernetesAdapter` so the operation is audit-
logged through the same workload runtime path as everything else.

The launcher is invoked by the ``data.lakehouse.hudi.start_streamer``
MCP tool (Phase 2e) and by Celery tasks under
``aqp/tasks/lakehouse_tasks.py`` (Phase 5 follow-up).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aqp.config import settings
from aqp.data.lakehouse.hudi.namespaces import (
    DEFAULT_HUDI_PREFIX,
    assert_not_iceberg,
    hudi_namespace,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HudiStreamerSpec:
    """Spec for one HoodieStreamer SparkApplication."""

    name: str
    namespace: str  # AQP-side logical namespace, e.g., "market_l1"
    table: str
    source_class: str  # e.g., org.apache.hudi.utilities.sources.AvroKafkaSource
    target_table_type: str = "MERGE_ON_READ"
    op: str = "UPSERT"
    record_key_field: str = "vt_symbol"
    precombine_field: str = "ts_ns"
    partition_path_field: str = "exchange,date_str"
    kafka_topic: str = ""
    kafka_bootstrap: str = ""
    schema_registry_url: str = ""
    spark_image: str = (
        "ghcr.io/apache/hudi/hudi-spark3.5-bundle_2.12:1.0.1"
    )
    spark_application_namespace: str = "aqp-mlops"
    extra_props: dict[str, str] = field(default_factory=dict)

    def fully_qualified_name(self) -> str:
        return f"hudi-streamer-{self.name}"

    def base_path(self) -> str:
        base = (settings.hudi_warehouse_url or "").rstrip("/")
        if not base:
            raise ValueError(
                "settings.hudi_warehouse_url unset; cannot render Hudi base path"
            )
        return f"{base}/{hudi_namespace(self.namespace)}/{self.table}/"

    def render_manifest(self) -> dict[str, Any]:
        """Render the SparkApplication CR dict."""
        assert_not_iceberg(hudi_namespace(self.namespace))
        if not hudi_namespace(self.namespace).startswith(DEFAULT_HUDI_PREFIX):
            raise ValueError(
                f"Hudi namespace must start with {DEFAULT_HUDI_PREFIX!r}; got "
                f"{self.namespace!r}"
            )
        properties_lines = [
            f"hoodie.streamer.source.kafka.topic={self.kafka_topic}",
            f"bootstrap.servers={self.kafka_bootstrap or settings.kafka_bootstrap}",
            f"hoodie.streamer.schemaprovider.registry.url={self.schema_registry_url or settings.schema_registry_url}",
            f"hoodie.datasource.write.recordkey.field={self.record_key_field}",
            f"hoodie.datasource.write.precombine.field={self.precombine_field}",
            f"hoodie.datasource.write.partitionpath.field={self.partition_path_field}",
            "auto.offset.reset=earliest",
        ]
        for key, value in self.extra_props.items():
            properties_lines.append(f"{key}={value}")
        manifest: dict[str, Any] = {
            "apiVersion": "sparkoperator.k8s.io/v1beta2",
            "kind": "SparkApplication",
            "metadata": {
                "name": self.fully_qualified_name(),
                "namespace": self.spark_application_namespace,
                "labels": {
                    "app.kubernetes.io/part-of": "aqp",
                    "app.kubernetes.io/component": "lakehouse",
                    "aqp.internal/cluster": "lakehouse.hudi",
                },
            },
            "spec": {
                "type": "Scala",
                "sparkVersion": "3.5.5",
                "mode": "cluster",
                "image": self.spark_image,
                "mainClass": "org.apache.hudi.utilities.deltastreamer.HoodieDeltaStreamer",
                "mainApplicationFile": "local:///opt/spark/jars/hudi-utilities-bundle.jar",
                "arguments": [
                    "--table-type",
                    self.target_table_type,
                    "--op",
                    self.op,
                    "--target-base-path",
                    self.base_path(),
                    "--target-table",
                    self.table,
                    "--source-class",
                    self.source_class,
                    "--continuous",
                    "--props",
                    "/opt/aqp/hoodie/streamer.properties",
                ],
                "driver": {
                    "cores": 1,
                    "memory": "2g",
                    "labels": {"app.kubernetes.io/part-of": "aqp"},
                },
                "executor": {
                    "cores": 2,
                    "instances": 2,
                    "memory": "4g",
                    "labels": {"app.kubernetes.io/part-of": "aqp"},
                },
                "deps": {
                    "files": [
                        "configmap:aqp-hudi-streamer-properties:streamer.properties",
                    ],
                },
            },
            # The streamer.properties content is mounted via ConfigMap;
            # the launcher writes it next to the SparkApplication.
            "_configmap_streamer_properties": "\n".join(properties_lines),
        }
        return manifest


class HudiStreamerLauncher:
    """Submit HoodieStreamer SparkApplications via the KubernetesAdapter."""

    def __init__(self) -> None:
        self._adapter = None

    def _get_adapter(self) -> Any:
        if self._adapter is not None:
            return self._adapter
        from aqp.kubernetes import get_kubernetes_adapter

        self._adapter = get_kubernetes_adapter()
        return self._adapter

    def start(self, spec: HudiStreamerSpec) -> dict[str, Any]:
        """Submit the SparkApplication CR; returns the manifest payload sent."""
        manifest = spec.render_manifest()
        cm_body = manifest.pop("_configmap_streamer_properties", "")
        # The actual apply lives on the KubernetesAdapter; we don't import
        # the adapter at module-top to keep import-time cost minimal.
        adapter = self._get_adapter()
        try:
            create = getattr(adapter, "apply_custom_resource", None)
            if create is None:
                raise NotImplementedError(
                    "active KubernetesAdapter does not implement "
                    "apply_custom_resource; install the AQP cluster mgmt "
                    "API or run with kubernetes_adapter=in_cluster."
                )
            create(manifest)
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("HudiStreamerLauncher.start failed")
            raise RuntimeError(
                f"HudiStreamerLauncher submit failed: {exc}"
            ) from exc
        logger.info(
            "Submitted HudiStreamer SparkApplication name=%s base_path=%s",
            spec.fully_qualified_name(),
            spec.base_path(),
        )
        return {
            "ok": True,
            "spark_application": spec.fully_qualified_name(),
            "namespace": spec.spark_application_namespace,
            "base_path": spec.base_path(),
            "configmap_properties_size": len(cm_body),
        }

    def stop(self, name: str, *, namespace: str = "aqp-mlops") -> dict[str, Any]:
        """Delete the SparkApplication CR."""
        adapter = self._get_adapter()
        try:
            delete = getattr(adapter, "delete_custom_resource", None)
            if delete is None:
                raise NotImplementedError(
                    "active KubernetesAdapter does not implement "
                    "delete_custom_resource"
                )
            delete(
                api_version="sparkoperator.k8s.io/v1beta2",
                kind="SparkApplication",
                name=name,
                namespace=namespace,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"HudiStreamerLauncher stop failed: {exc}") from exc
        return {"ok": True, "spark_application": name, "namespace": namespace}


__all__ = [
    "HudiStreamerLauncher",
    "HudiStreamerSpec",
]
