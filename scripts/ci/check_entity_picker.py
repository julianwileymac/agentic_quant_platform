"""Enforce AGENTS Rule 29 — typed-entity selection uses ``<EntityPicker>``.

Scans frontend ``.tsx`` files under ``aqp_client/src/`` and
``aqp_ui/src/``. Flags any free-text input whose label / placeholder /
name / list-id matches one of the entity-shaped patterns, unless the
input is itself the canonical ``EntityPicker`` component file.

Patterns we treat as entity-shaped (case-insensitive):

* ``urn:aqp:`` literal in placeholders / values
* ``entity_type`` / ``entityType``
* ``workspace_id`` / ``workspaceId``
* ``dataset_id`` / ``dataset.*id`` (dataset selectors)
* ``project_id`` / ``projectId`` (project selectors)
* ``experiment_id`` / ``test_id``

The lint is regex-based for speed. False positives can be added to
``scripts/ci/allowlists/entity_picker.txt``.

Exit codes:
* 0 — no violations (after allowlist)
* 1 — at least one violation
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_ROOTS = (
    "aqp_client/src",
    "aqp_ui/src",
)

# Files that legitimately implement free-text URN inputs (the
# ``EntityPicker`` itself + its tests). Anything else is suspect.
SELF_EXEMPT_NAMES = (
    "EntityPicker.tsx",
    "EntityPicker.test.tsx",
    "EntityPicker.spec.tsx",
    "EntityPickerWidget.tsx",
)

# Patterns that mark an input as targeting a typed AQP entity.
SUSPICIOUS_PATTERNS = (
    re.compile(r"urn:aqp:", re.IGNORECASE),
    re.compile(r"\bentity[_\s]?type\b", re.IGNORECASE),
    re.compile(r"\bworkspace[_\s]?id\b", re.IGNORECASE),
    re.compile(r"\bdataset[_\s]?id\b", re.IGNORECASE),
    re.compile(r"\bproject[_\s]?id\b", re.IGNORECASE),
    re.compile(r"\bexperiment[_\s]?id\b", re.IGNORECASE),
    re.compile(r"\btest[_\s]?id\b", re.IGNORECASE),
)

# JSX input-shaped tags we audit. ``<select>`` is included because a
# raw <select> for a typed-entity field is a Rule 29 violation just
# like a free-text <input>.
INPUT_TAG_RE = re.compile(
    r"<(Input|input|TextInput|TextField|select|textarea)\b[^>]*?>",
    re.IGNORECASE | re.DOTALL,
)


sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
from _lint_allowlist import filter_violations, normalise_path  # noqa: E402


def _scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    if path.name in SELF_EXEMPT_NAMES:
        return []

    out: list[tuple[int, str]] = []
    for match in INPUT_TAG_RE.finditer(source):
        snippet = match.group(0)
        if not any(p.search(snippet) for p in SUSPICIOUS_PATTERNS):
            continue
        # Compute approximate line number.
        line = source.count("\n", 0, match.start()) + 1
        # Compress the snippet for the report.
        compact = re.sub(r"\s+", " ", snippet).strip()
        if len(compact) > 220:
            compact = compact[:217] + "..."
        out.append((line, compact))
    return out


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.tsx"):
            if "node_modules" in path.parts:
                continue
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
    )
    args = parser.parse_args(argv)

    files = [Path(p) for p in args.paths] if args.paths else _iter_files()

    raw: list[tuple[str, str]] = []
    for path in files:
        for lineno, snippet in _scan_file(path):
            rel = normalise_path(path.resolve().relative_to(REPO_ROOT))
            raw.append((rel, f"{rel}:{lineno} {snippet}"))

    filtered = filter_violations(raw, "entity_picker")
    if filtered:
        print(
            "[entity-picker] FAIL: free-text input(s) capturing typed AQP "
            "entities detected.\n"
            "Replace with `<EntityPicker kind=\"...\" value={...} "
            "onChange={...} />` (Rule 29) or allowlist with a removal "
            "deadline in scripts/ci/allowlists/entity_picker.txt.\n"
        )
        for _, message in filtered:
            print(f"  - {message}")
        return 1
    print(
        f"[entity-picker] OK: scanned {len(files)} .tsx files, "
        f"{len(raw)} raw match(es), 0 unallowlisted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
