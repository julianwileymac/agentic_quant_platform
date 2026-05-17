"""URN <-> AQP identifier mapping helpers.

Covers Iceberg datasets, MLflow models, and AQP ``vt_symbol``
identifiers. ``parse_urn`` returns a structured dict for any URN we
can recognize (the rest are returned with ``"kind": "unknown"``).
"""
from __future__ import annotations

from typing import Any

from aqp.config import settings


def iceberg_dataset_urn(
    identifier: str,
    *,
    platform: str | None = None,
    platform_instance: str | None = None,
    env: str | None = None,
) -> str:
    """Build a DataHub URN for an Iceberg ``namespace.table``."""
    plat = platform or settings.datahub_platform or "iceberg"
    env_label = env or settings.datahub_env or "PROD"
    instance = platform_instance or settings.datahub_platform_instance
    parts = [plat]
    if instance:
        parts.append(instance)
    parts.append(identifier)
    name = ".".join(parts)
    return f"urn:li:dataset:(urn:li:dataPlatform:{plat},{name},{env_label})"


def vt_symbol_urn(vt_symbol: str, *, env: str | None = None) -> str:
    """Build a DataHub URN for an AQP instrument identifier."""
    env_label = env or settings.datahub_env or "PROD"
    instance = settings.datahub_platform_instance or "agentic-quant-platform"
    return (
        f"urn:li:dataset:(urn:li:dataPlatform:aqp,{instance}.instruments.{vt_symbol},"
        f"{env_label})"
    )


def mlflow_model_urn(
    name: str,
    *,
    platform: str = "mlflow",
    platform_instance: str | None = None,
    env: str | None = None,
) -> str:
    env_label = env or settings.datahub_env or "PROD"
    instance = platform_instance or settings.datahub_platform_instance
    full_name = f"{instance}.{name}" if instance else name
    return (
        f"urn:li:mlModel:(urn:li:dataPlatform:{platform},{full_name},{env_label})"
    )


def parse_urn(urn: str) -> dict[str, Any]:
    """Decompose a DataHub URN into its parts."""
    if not urn or not urn.startswith("urn:li:"):
        return {"urn": urn, "kind": "unknown"}
    if urn.startswith("urn:li:dataset:("):
        body = urn[len("urn:li:dataset:(") : -1]
        parts = body.split(",")
        if len(parts) >= 3:
            platform_urn = parts[0]
            return {
                "urn": urn,
                "kind": "dataset",
                "platform": platform_urn.split(":")[-1],
                "name": parts[1],
                "env": parts[2],
            }
    if urn.startswith("urn:li:mlModel:("):
        body = urn[len("urn:li:mlModel:(") : -1]
        parts = body.split(",")
        if len(parts) >= 3:
            return {
                "urn": urn,
                "kind": "mlModel",
                "platform": parts[0].split(":")[-1],
                "name": parts[1],
                "env": parts[2],
            }
    if urn.startswith("urn:li:dataFlow:("):
        return {"urn": urn, "kind": "dataFlow"}
    if urn.startswith("urn:li:dataJob:("):
        return {"urn": urn, "kind": "dataJob"}
    return {"urn": urn, "kind": "unknown"}


__all__ = [
    "iceberg_dataset_urn",
    "mlflow_model_urn",
    "parse_urn",
    "vt_symbol_urn",
]
