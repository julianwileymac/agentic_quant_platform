"""Markdown skill catalog for the Assistant Engine.

Skills are read-only, content-hashed Markdown descriptors the UI
renders so operators know what reusable behaviours an assistant has
access to. There is **no autonomous mutation** — assistants display
skills, not rewrite them. New behaviour must come through a new
:class:`AssistantSpec` version (rule: hash-locked spec versions are
immutable).

Rationale: the AstrBot / RD-Agent inspiration repos motivate skill
manifests, but the AQP equivalent stays display-only on purpose so an
LLM cannot edit its own runtime contract from inside a chat.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from aqp.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantSkillDescriptor:
    """One discovered Markdown skill.

    ``content_hash`` lets the registry detect modifications between
    scans — if the hash changes, the cached :class:`AssistantSkill`
    row is updated (never deleted) so historical runs that referenced
    the prior content still resolve.
    """

    slug: str
    title: str
    content_hash: str
    path: str
    tags: tuple[str, ...] = field(default_factory=tuple)


def default_skill_root() -> Path:
    """Default Markdown skill directory.

    Read from ``settings.data_dir`` (single source of truth — never
    ``os.environ``) so every consumer agrees on the location even if
    operators flip the data root.
    """
    return Path(settings.data_dir) / "assistant_skills"


def list_markdown_skills(
    root: Path | None = None,
) -> list[AssistantSkillDescriptor]:
    """Enumerate every Markdown skill descriptor under ``root``.

    Sort order is stable (file path) so successive scans round-trip
    deterministically — the descriptor cache row updates only when
    content actually changes.
    """
    return list(_iter_markdown_skills(root))


def _iter_markdown_skills(
    root: Path | None,
) -> Iterator[AssistantSkillDescriptor]:
    target = root or default_skill_root()
    if not target.exists():
        return
    for path in sorted(target.glob("**/*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        title = _title_from_markdown(text) or path.stem.replace("-", " ").title()
        tags = tuple(_tags_from_markdown(text))
        yield AssistantSkillDescriptor(
            slug=path.stem,
            title=title,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            path=str(path),
            tags=tags,
        )


def get_skill(slug: str, *, root: Path | None = None) -> AssistantSkillDescriptor | None:
    """Look up a single skill descriptor by slug. Returns ``None`` when missing."""
    for descriptor in _iter_markdown_skills(root):
        if descriptor.slug == slug:
            return descriptor
    return None


def list_skills_for_assistant(
    spec: object, *, root: Path | None = None
) -> list[AssistantSkillDescriptor]:
    """Filter the skill catalog to those declared in ``spec.extras['skills']``.

    The :class:`AssistantSpec` doesn't make skills first-class today —
    operators thread them through ``extras['skills']: list[str]`` so
    we never mutate the spec schema. When no skills are declared we
    return the empty list (NOT the full catalog) so the UI surfaces
    only what the assistant explicitly opts into.
    """
    extras = getattr(spec, "extras", None) or {}
    declared = list(extras.get("skills") or [])
    if not declared:
        return []
    catalog = {d.slug: d for d in _iter_markdown_skills(root)}
    return [catalog[slug] for slug in declared if slug in catalog]


def sync_skill_cache(
    descriptors: Iterable[AssistantSkillDescriptor] | None = None,
) -> int:
    """Best-effort sync of Markdown descriptors into ``assistant_skills``.

    Returns the number of rows touched. No-ops cleanly when:

    - the Phase 2 ``assistant_skills`` table isn't yet provisioned, or
    - Postgres is unreachable, or
    - the skill root is missing.

    The function never raises — it's safe to call from the registry
    bootstrap path and from a Celery beat heartbeat.
    """
    items = list(descriptors) if descriptors is not None else list_markdown_skills()
    if not items:
        return 0
    try:
        from datetime import datetime

        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_assistants import AssistantSkill
    except Exception:  # noqa: BLE001
        logger.debug("assistant_skills table unavailable", exc_info=True)
        return 0
    touched = 0
    try:
        with SessionLocal() as session:
            for descriptor in items:
                row = (
                    session.query(AssistantSkill)
                    .filter(AssistantSkill.slug == descriptor.slug)
                    .one_or_none()
                )
                if row is None:
                    row = AssistantSkill(
                        slug=descriptor.slug,
                        title=descriptor.title,
                        content_hash=descriptor.content_hash,
                        path=descriptor.path,
                        tags=list(descriptor.tags),
                    )
                    session.add(row)
                    touched += 1
                elif row.content_hash != descriptor.content_hash:
                    row.title = descriptor.title
                    row.content_hash = descriptor.content_hash
                    row.path = descriptor.path
                    row.tags = list(descriptor.tags)
                    row.updated_at = datetime.utcnow()
                    touched += 1
            if touched:
                session.commit()
    except Exception:  # noqa: BLE001
        logger.debug("sync_skill_cache failed", exc_info=True)
        return 0
    return touched


def _title_from_markdown(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _tags_from_markdown(text: str) -> list[str]:
    """Pull a simple ``tags:`` list out of an optional YAML front-matter.

    Supports the conventional fenced front-matter:

    .. code-block:: text

        ---
        tags: [research, codebase]
        ---

    Returns ``[]`` when no front-matter is present.
    """
    if not text.startswith("---"):
        return []
    lines = text.splitlines()
    end = -1
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = idx
            break
    if end == -1:
        return []
    front = "\n".join(lines[1:end])
    try:
        import yaml

        data = yaml.safe_load(front) or {}
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("tags")
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    if isinstance(raw, str):
        return [raw.strip()]
    return []


__all__ = [
    "AssistantSkillDescriptor",
    "default_skill_root",
    "get_skill",
    "list_markdown_skills",
    "list_skills_for_assistant",
    "sync_skill_cache",
]
