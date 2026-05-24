#!/usr/bin/env python3
"""Round-trip ``DocumentRecord`` instances through Redis OM.

Demonstrates ensuring the model index is migrated, creating two
documents with tags, querying them by tag, and deleting them.

Usage::

    python -m pipelines.examples.redis_om_document_demo
"""

from __future__ import annotations

import time

from pipelines.redis_io import ping, require_modules
from pipelines.redis_om_models import DocumentRecord, ensure_migrated


def main() -> None:
    if not ping():
        raise SystemExit("Cannot reach Redis. Check REDIS_URL / REDIS_PASSWORD.")
    require_modules(("search", "rejson"))

    ensure_migrated()

    a = DocumentRecord(
        title="Redis 8 Stack Cluster Notes",
        collection="manuals",
        source="upload",
        tags=["redis", "manual"],
        size_bytes=12345,
        chunk_count=42,
        owner="admin",
        description="Cheat-sheet for the new shared cache.",
    )
    b = DocumentRecord(
        title="Cache-aside playbook",
        collection="manuals",
        source="upload",
        tags=["redis", "cache"],
        size_bytes=2048,
        chunk_count=4,
        owner="admin",
        description="When to cache and when not to.",
    )
    a.save()
    b.save()

    print("Saved:")
    print(f"  {a.pk}  {a.title}")
    print(f"  {b.pk}  {b.title}")

    print("\nQuery (tags ~ 'cache'):")
    for hit in DocumentRecord.find(DocumentRecord.tags << ["cache"]).all():
        print(f"  {hit.pk}  {hit.title}  ({len(hit.tags)} tags)")

    time.sleep(0.5)
    DocumentRecord.delete(a.pk)
    DocumentRecord.delete(b.pk)
    print("\nDeleted both records.")


if __name__ == "__main__":
    main()
