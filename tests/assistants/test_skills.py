"""Markdown skill descriptor + cache invalidation tests."""
from __future__ import annotations

from pathlib import Path

from aqp.assistants.skills import (
    AssistantSkillDescriptor,
    get_skill,
    list_markdown_skills,
)


def test_list_markdown_skills_handles_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-dir"
    assert list_markdown_skills(missing) == []


def test_list_markdown_skills_extracts_title_and_tags(tmp_path: Path) -> None:
    (tmp_path / "factor-research.md").write_text(
        """---
tags: [alpha, factor]
---

# Factor Research Primer

Some content goes here.
""",
        encoding="utf-8",
    )
    (tmp_path / "no-front-matter.md").write_text(
        "# Bare Title\nbody\n", encoding="utf-8"
    )
    (tmp_path / "untitled.md").write_text("no heading at all", encoding="utf-8")

    descriptors = list_markdown_skills(tmp_path)
    by_slug = {d.slug: d for d in descriptors}
    assert "factor-research" in by_slug
    assert by_slug["factor-research"].title == "Factor Research Primer"
    assert by_slug["factor-research"].tags == ("alpha", "factor")
    assert by_slug["no-front-matter"].title == "Bare Title"
    assert by_slug["untitled"].title == "Untitled"


def test_descriptor_content_hash_changes_with_content(tmp_path: Path) -> None:
    p = tmp_path / "drift.md"
    p.write_text("# v1\nfirst", encoding="utf-8")
    first = list_markdown_skills(tmp_path)[0]
    p.write_text("# v2\nsecond", encoding="utf-8")
    second = list_markdown_skills(tmp_path)[0]
    assert first.content_hash != second.content_hash


def test_get_skill_returns_descriptor(tmp_path: Path) -> None:
    (tmp_path / "lookup.md").write_text("# Look Up\nbody\n", encoding="utf-8")
    descriptor = get_skill("lookup", root=tmp_path)
    assert isinstance(descriptor, AssistantSkillDescriptor)
    assert descriptor.title == "Look Up"


def test_get_skill_returns_none_for_unknown(tmp_path: Path) -> None:
    assert get_skill("missing", root=tmp_path) is None
