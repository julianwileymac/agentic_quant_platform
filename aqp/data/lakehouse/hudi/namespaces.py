"""Hudi namespace contract — kept distinct from Iceberg.

Phase 2e of the AQP infra-expansion plan. Iceberg uses the
medallion-tagged namespaces ``aqp_bronze_*`` / ``aqp_silver_*`` /
``aqp_gold_*`` (validated by
:func:`aqp.data.iceberg_catalog._validate_layer_prefix`). Hudi runs
in parallel under ``aqp_hudi_*`` so an accidental ``append_arrow``
call against a Hudi-style identifier fails the existing layer
prefix check, which by design never lets Hudi traffic flow through
the canonical Iceberg writer (rule 3).
"""
from __future__ import annotations

DEFAULT_HUDI_PREFIX = "aqp_hudi_"


def hudi_namespace(name: str, *, prefix: str | None = None) -> str:
    """Return the canonical Hudi namespace for a logical name.

    >>> hudi_namespace("market_l1")
    'aqp_hudi_market_l1'
    """
    actual_prefix = (prefix or DEFAULT_HUDI_PREFIX).strip()
    if not actual_prefix.endswith("_"):
        actual_prefix = actual_prefix + "_"
    bare = name.strip().strip("_")
    if not bare:
        raise ValueError("hudi_namespace requires a non-empty name")
    if bare.startswith(actual_prefix):
        return bare
    return f"{actual_prefix}{bare}"


def is_hudi_namespace(name: str, *, prefix: str | None = None) -> bool:
    actual_prefix = (prefix or DEFAULT_HUDI_PREFIX).strip()
    if not actual_prefix.endswith("_"):
        actual_prefix = actual_prefix + "_"
    return name.startswith(actual_prefix)


def assert_not_iceberg(table_name: str) -> None:
    """Reject Iceberg-style namespaces to defend rule 3.

    The Hudi writer calls this before talking to Spark so a misconfigured
    ``HudiSpec(target_path=...)`` cannot accidentally write to an Iceberg
    namespace and corrupt the canonical lakehouse.
    """
    bare = table_name.strip().lower()
    if bare.startswith(("aqp_bronze_", "aqp_silver_", "aqp_gold_")):
        raise ValueError(
            f"refusing to write Hudi data to Iceberg-medallion namespace "
            f"{table_name!r}; use the {DEFAULT_HUDI_PREFIX}* prefix per "
            f"plan section D"
        )


__all__ = [
    "DEFAULT_HUDI_PREFIX",
    "assert_not_iceberg",
    "hudi_namespace",
    "is_hudi_namespace",
]
