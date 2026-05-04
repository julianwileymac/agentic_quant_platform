"""Jinja2 templates for cluster-side workloads (FlinkSessionJob, etc.)."""
from __future__ import annotations

from importlib import resources
from typing import Any


def render_factor_session_job(
    *,
    name: str,
    namespace: str,
    factor_jar_uri: str,
    entry_class: str,
    args: list[str],
    parallelism: int = 1,
    state: str = "running",
) -> dict[str, Any]:
    """Render a FlinkSessionJob manifest dict suitable for `kubectl apply`."""
    return {
        "apiVersion": "flink.apache.org/v1beta1",
        "kind": "FlinkSessionJob",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/managed-by": "aqp",
                "aqp.flink/factor": "true",
            },
        },
        "spec": {
            "deploymentName": "flink-session",
            "job": {
                "jarURI": factor_jar_uri,
                "entryClass": entry_class,
                "args": list(args),
                "parallelism": int(parallelism),
                "upgradeMode": "stateless",
                "state": state,
            },
        },
    }


def load_template_text(name: str) -> str:
    """Read a packaged template file by name."""
    return resources.files("aqp.streaming.templates").joinpath(name).read_text(
        encoding="utf-8"
    )


__all__ = ["load_template_text", "render_factor_session_job"]
