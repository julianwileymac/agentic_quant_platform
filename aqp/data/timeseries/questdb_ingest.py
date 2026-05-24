"""QuestDB ILP (InfluxDB Line Protocol) writer.

Phase 2b of the AQP infra-expansion plan: high-throughput ingest path
for market.l1 / market.l2 / executions tick streams. We use ILP over
TCP because the protocol bypasses SQL parsing and accepts batched
writes in microseconds, matching the QuestDB sizing guidance from
the plan's research findings.

The recommended topology in production is:

    redpanda  ->  Redpanda Connect (with QuestDB sink)  ->  QuestDB

Hand-rolled Python consumers should only be used during development
or for synthetic test ingestion. This module is the sanctioned hand-
rolled path; it is registered as the writer for the ``questdb``
dataset kind in :mod:`aqp.data.datasets.kinds.questdb`.

Single line format::

    market.l1,exchange=NYSE,symbol=AAPL bid=150.25,ask=150.26,size=100i 1727294094000000000

Tag (low-cardinality) and field (high-cardinality numeric) columns
are kept separate to match QuestDB's partitioning hints. Timestamp
is nanosecond Unix epoch.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Any, Iterable, Mapping

from aqp.config import settings

logger = logging.getLogger(__name__)


class QuestDBIngestError(RuntimeError):
    """Raised when the ILP TCP / HTTP send fails."""


def _format_value(value: Any) -> str:
    """Format a single field value per the ILP spec."""
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, int):
        return f"{value}i"
    if isinstance(value, float):
        return repr(value)
    if value is None:
        return ""
    # String: escape backslash + double-quote, wrap in quotes.
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _format_tag_value(value: Any) -> str:
    """Tag values are unquoted; escape spaces, commas, equals."""
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace(",", "\\,")
        .replace("=", "\\=")
    )


def render_ilp(
    measurement: str,
    *,
    tags: Mapping[str, Any] | None = None,
    fields: Mapping[str, Any],
    timestamp_ns: int | None = None,
) -> str:
    """Render a single ILP line."""
    if not fields:
        raise QuestDBIngestError("ILP requires at least one field value")
    parts: list[str] = [measurement]
    if tags:
        parts.append(",")
        parts.append(
            ",".join(f"{k}={_format_tag_value(v)}" for k, v in tags.items() if v is not None)
        )
    parts.append(" ")
    parts.append(
        ",".join(
            f"{k}={_format_value(v)}" for k, v in fields.items() if v is not None
        )
    )
    if timestamp_ns is None:
        timestamp_ns = time.time_ns()
    parts.append(f" {int(timestamp_ns)}\n")
    return "".join(parts)


class QuestDBIngester:
    """Long-lived ILP TCP writer.

    Construct once per worker process; reuse the connection across
    batches. ``send_batch`` uses a thread-safe lock so producers
    running in different threads can share one ingester.
    """

    def __init__(
        self,
        ilp_url: str | None = None,
        *,
        timeout_seconds: float = 5.0,
    ) -> None:
        url = ilp_url or settings.questdb_ilp_url
        if not url:
            raise QuestDBIngestError(
                "questdb_ilp_url is unset; configure AQP_QUESTDB_ILP_URL or "
                "topology services > questdb > endpoints.ilp_tcp"
            )
        self._url = url
        self._host, self._port = self._parse(url)
        self._timeout = float(timeout_seconds)
        self._sock: socket.socket | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _parse(url: str) -> tuple[str, int]:
        # url examples:
        #   "questdb.aqp-timeseries.svc.cluster.local:9009"
        #   "tcp://questdb:9009"
        clean = url.replace("tcp://", "").rstrip("/")
        if ":" not in clean:
            raise QuestDBIngestError(
                f"questdb_ilp_url {url!r} missing port; expected host:9009"
            )
        host, port_text = clean.rsplit(":", 1)
        try:
            return host, int(port_text)
        except ValueError as exc:
            raise QuestDBIngestError(
                f"questdb_ilp_url {url!r} port is not an integer"
            ) from exc

    def _connect(self) -> socket.socket:
        with self._lock:
            if self._sock is not None:
                return self._sock
            try:
                sock = socket.create_connection(
                    (self._host, self._port), timeout=self._timeout
                )
                sock.settimeout(self._timeout)
            except OSError as exc:
                raise QuestDBIngestError(
                    f"failed to connect to QuestDB ILP at {self._url}: {exc}"
                ) from exc
            self._sock = sock
            return sock

    def send_lines(self, lines: Iterable[str]) -> int:
        """Send pre-rendered ILP lines. Returns bytes written."""
        with self._lock:
            sock = self._connect()
            payload = "".join(lines).encode("utf-8")
            try:
                sock.sendall(payload)
            except OSError as exc:
                # Drop the bad socket so the next call reconnects.
                self.close()
                raise QuestDBIngestError(
                    f"QuestDB ILP send failed: {exc}"
                ) from exc
            return len(payload)

    def send_record(
        self,
        measurement: str,
        *,
        tags: Mapping[str, Any] | None = None,
        fields: Mapping[str, Any],
        timestamp_ns: int | None = None,
    ) -> int:
        """Render and send a single record."""
        line = render_ilp(
            measurement, tags=tags, fields=fields, timestamp_ns=timestamp_ns
        )
        return self.send_lines([line])

    def send_batch(
        self,
        measurement: str,
        records: Iterable[Mapping[str, Any]],
        *,
        tag_keys: Iterable[str],
        field_keys: Iterable[str],
        timestamp_key: str = "ts_ns",
    ) -> int:
        """Render and send a batch of records.

        Each record is a mapping that contains keys from ``tag_keys`` +
        ``field_keys`` + the ``timestamp_key`` (nanoseconds).
        """
        tag_keys = tuple(tag_keys)
        field_keys = tuple(field_keys)
        lines: list[str] = []
        for rec in records:
            tags = {k: rec[k] for k in tag_keys if k in rec and rec[k] is not None}
            fields = {k: rec[k] for k in field_keys if k in rec and rec[k] is not None}
            ts = rec.get(timestamp_key)
            lines.append(
                render_ilp(measurement, tags=tags, fields=fields, timestamp_ns=ts)
            )
        return self.send_lines(lines)

    def close(self) -> None:
        with self._lock:
            if self._sock is None:
                return
            try:
                self._sock.close()
            except Exception:  # noqa: BLE001
                pass
            self._sock = None


__all__ = [
    "QuestDBIngestError",
    "QuestDBIngester",
    "render_ilp",
]
