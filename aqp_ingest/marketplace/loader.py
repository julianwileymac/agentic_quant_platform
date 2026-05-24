"""Template loader for the connector marketplace.

Walks the [`seed/`](seed/) tree and emits :class:`Template` dicts
the Phase 5 catalog UI surfaces and the Celery seed-task upserts
into ``template_catalog`` (Alembic 0069).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


_SEED_DIR = Path(__file__).resolve().parent / "seed"


@dataclass(slots=True)
class Template:
    slug: str
    display_name: str
    kind: str  # low_code_yaml | python_cdk | cdc
    vendor_tier: str | None
    spec: dict[str, Any]
    rate_limit_class: str | None
    default_sync_mode: str | None
    doc_url: str | None
    extras: dict[str, Any] = field(default_factory=dict)


def iter_templates(seed_dir: Path | None = None) -> Iterable[Template]:
    """Yield every template under :data:`_SEED_DIR`."""
    base = seed_dir or _SEED_DIR
    if not base.exists():
        return iter(())
    for path in sorted(base.rglob("*.yaml")):
        tmpl = load_template(path)
        if tmpl is not None:
            yield tmpl


def load_template(path: Path) -> Template | None:
    """Parse a single template YAML."""
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not parse template %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return Template(
            slug=str(raw["slug"]),
            display_name=str(raw["display_name"]),
            kind=str(raw.get("kind", "low_code_yaml")),
            vendor_tier=raw.get("vendor_tier"),
            spec=dict(raw.get("spec", {})),
            rate_limit_class=raw.get("rate_limit_class"),
            default_sync_mode=raw.get("default_sync_mode"),
            doc_url=raw.get("doc_url"),
            extras=dict(raw.get("extras", {})),
        )
    except KeyError as exc:
        logger.warning("template %s missing field %s", path, exc)
        return None


def seed_templates_to_db(seed_dir: Path | None = None) -> dict[str, int]:
    """Upsert every template under :data:`_SEED_DIR` into ``template_catalog``.

    Designed to run on platform boot (or on a Celery beat task) so
    the catalog stays in sync with the seed directory. Returns
    ``{count, skipped, errors}``.
    """
    counts = {"count": 0, "skipped": 0, "errors": 0}
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_ratelimit import TemplateCatalog
    except Exception as exc:  # noqa: BLE001
        logger.warning("template_catalog model unavailable: %s", exc)
        return counts
    with get_session() as session:
        for tmpl in iter_templates(seed_dir):
            try:
                existing = (
                    session.query(TemplateCatalog)
                    .filter(TemplateCatalog.slug == tmpl.slug)
                    .one_or_none()
                )
                if existing is None:
                    session.add(
                        TemplateCatalog(
                            slug=tmpl.slug,
                            display_name=tmpl.display_name,
                            kind=tmpl.kind,
                            vendor_tier=tmpl.vendor_tier,
                            spec_json=tmpl.spec,
                            rate_limit_class=tmpl.rate_limit_class,
                            default_sync_mode=tmpl.default_sync_mode,
                            doc_url=tmpl.doc_url,
                            is_active=True,
                        )
                    )
                    counts["count"] += 1
                else:
                    existing.display_name = tmpl.display_name
                    existing.kind = tmpl.kind
                    existing.spec_json = tmpl.spec
                    existing.rate_limit_class = tmpl.rate_limit_class
                    existing.default_sync_mode = tmpl.default_sync_mode
                    existing.doc_url = tmpl.doc_url
                    counts["skipped"] += 1
            except Exception:  # noqa: BLE001
                counts["errors"] += 1
                logger.warning(
                    "template %s upsert failed", tmpl.slug, exc_info=True
                )
        session.commit()
    return counts


__all__ = ["Template", "iter_templates", "load_template", "seed_templates_to_db"]
