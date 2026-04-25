"""Optional BigQuery federation path for GDelt GKG 2.0.

Uses the public ``gdelt-bq.gdeltv2.gkg`` table; you pay only for the
bytes scanned by your query. The client keeps its dependency on
``google-cloud-bigquery`` lazy so the base install stays lean — callers
must install the ``[gdelt-bq]`` extra and provision a service account
(``GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json``) or application
default credentials before using this module.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)


class GDeltBigQueryError(RuntimeError):
    """Raised when google-cloud-bigquery is missing or a query fails."""


class GDeltBigQueryClient:
    """Thin wrapper around :class:`google.cloud.bigquery.Client`."""

    def __init__(
        self,
        *,
        project: str | None = None,
        table: str | None = None,
    ) -> None:
        self.project = project or settings.gdelt_bigquery_project or None
        self.table = table or settings.gdelt_bigquery_table

    def probe(self) -> tuple[bool, str]:
        try:
            self._client()
        except GDeltBigQueryError as exc:
            return False, str(exc)
        return True, "ok"

    def _client(self) -> Any:
        try:
            from google.cloud import bigquery  # type: ignore[import-not-found]
        except ImportError as exc:
            raise GDeltBigQueryError(
                "google-cloud-bigquery is not installed; run "
                "'pip install \"agentic-quant-platform[gdelt-bq]\"'"
            ) from exc
        try:
            return bigquery.Client(project=self.project) if self.project else bigquery.Client()
        except Exception as exc:  # pragma: no cover - auth variations
            raise GDeltBigQueryError(f"BigQuery client init failed: {exc}") from exc

    def query_window(
        self,
        *,
        start: datetime | str,
        end: datetime | str,
        organizations: list[str] | None = None,
        themes: list[str] | None = None,
        limit: int = 10_000,
    ) -> pd.DataFrame:
        """Query the public ``gkg`` table for a date window.

        Returns a :class:`pandas.DataFrame` with the subset of columns
        (``DATE``, ``V2DocumentIdentifier``, ``V2SourceCommonName``,
        ``V2EnhancedOrganizations``, ``V2EnhancedThemes``, ``V15Tone``).
        """
        client = self._client()
        start_dt = _coerce_dt(start)
        end_dt = _coerce_dt(end)

        filters = ["_PARTITIONTIME >= @start_ts", "_PARTITIONTIME <= @end_ts"]
        params: list[Any] = []
        import_parts: list[Any] = []
        try:
            from google.cloud import bigquery  # type: ignore[import-not-found]

            params.append(bigquery.ScalarQueryParameter("start_ts", "TIMESTAMP", start_dt))
            params.append(bigquery.ScalarQueryParameter("end_ts", "TIMESTAMP", end_dt))
            import_parts.append(bigquery)
        except Exception as exc:  # pragma: no cover
            raise GDeltBigQueryError(str(exc)) from exc

        if organizations:
            or_terms = " OR ".join(
                [f"V2EnhancedOrganizations LIKE @org_{i}" for i in range(len(organizations))]
            )
            filters.append(f"({or_terms})")
            for idx, org in enumerate(organizations):
                params.append(
                    import_parts[0].ScalarQueryParameter(
                        f"org_{idx}", "STRING", f"%{org}%"
                    )
                )
        if themes:
            or_terms = " OR ".join(
                [f"V2EnhancedThemes LIKE @theme_{i}" for i in range(len(themes))]
            )
            filters.append(f"({or_terms})")
            for idx, theme in enumerate(themes):
                params.append(
                    import_parts[0].ScalarQueryParameter(
                        f"theme_{idx}", "STRING", f"%{theme}%"
                    )
                )

        where_clause = " AND ".join(filters)
        sql = f"""
        SELECT
          GKGRECORDID,
          DATE,
          V2SourceCommonName,
          V2DocumentIdentifier,
          V2EnhancedOrganizations,
          V2EnhancedThemes,
          V15Tone
        FROM `{self.table}`
        WHERE {where_clause}
        LIMIT {int(limit)}
        """

        job_config = import_parts[0].QueryJobConfig(query_parameters=params)
        try:
            df = client.query(sql, job_config=job_config).to_dataframe()
        except Exception as exc:
            raise GDeltBigQueryError(f"BigQuery query failed: {exc}") from exc
        return df


def _coerce_dt(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return pd.Timestamp(value).to_pydatetime()
