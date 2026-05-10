"""Optional RediSearch full-text index over cache hashes.

When Redis Stack is available we ``FT.CREATE`` an index over the
``by_id`` hashes per category so the discovery browser (Phase 1) and
the global search box can do prefix matching against ``name``,
``provider``, ``domain``, and ``tags`` simultaneously.

If Redis Stack isn't available the cache still works — callers fall
back to ``ZRANGEBYLEX`` with a name-prefix only via
:meth:`MetadataCache.zrange_lex`.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.cache.client import MetadataCache, get_cache
from aqp.cache.keys import CACHE_CATEGORIES, fulltext_index
from aqp.config import settings

logger = logging.getLogger(__name__)


_INDEXED_FIELDS_PER_CATEGORY: dict[str, tuple[str, ...]] = {
    "datasets": ("name", "provider", "domain", "iceberg_identifier", "tags"),
    "namespaces": ("name",),
    "sink_kinds": ("kind",),
    "sink_names": ("name", "kind"),
    "airbyte_connectors": ("name", "kind", "runtime"),
    "projects": ("name", "workspace_id"),
    "credentials": ("name",),
    "dataset_kinds": ("name", "kind"),
}


def try_create_full_text_index(
    cache: MetadataCache | None = None,
    *,
    categories: tuple[str, ...] = CACHE_CATEGORIES,
) -> dict[str, bool]:
    """Best-effort ``FT.CREATE`` per category.

    Returns a ``{category: created_or_existed}`` map. Errors are
    swallowed so the prefetcher never trips on a missing module.
    """
    if not getattr(settings, "cache_fulltext_index", True):
        return {category: False for category in categories}
    cache = cache or get_cache()
    if not cache.is_remote:
        return {category: False for category in categories}
    out: dict[str, bool] = {}
    try:
        from redis.commands.search.field import (  # type: ignore[import-not-found]
            TagField,
            TextField,
        )
        from redis.commands.search.indexDefinition import (  # type: ignore[import-not-found]
            IndexDefinition,
            IndexType,
        )
    except Exception:  # noqa: BLE001
        logger.info("RediSearch unavailable; cache full-text index skipped")
        return {category: False for category in categories}

    client = cache._client  # noqa: SLF001 — search needs the raw client
    for category in categories:
        idx_name = fulltext_index(category)
        try:
            client.ft(idx_name).info()
            out[category] = True
            continue
        except Exception:  # noqa: BLE001
            pass
        prefix = f"{settings.cache_key_prefix}:{category}:by_id:"
        fields: list[Any] = []
        for field_name in _INDEXED_FIELDS_PER_CATEGORY.get(category, ("name",)):
            if field_name == "tags":
                fields.append(TagField(field_name))
            else:
                fields.append(TextField(field_name))
        try:
            client.ft(idx_name).create_index(
                fields=fields,
                definition=IndexDefinition(prefix=[prefix], index_type=IndexType.HASH),
            )
            out[category] = True
        except Exception as exc:  # noqa: BLE001
            logger.info("FT.CREATE for %s failed: %s", category, exc)
            out[category] = False
    return out


__all__ = ["try_create_full_text_index"]
