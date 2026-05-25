"""Validate the Alembic revision graph.

Walks ``alembic/versions/`` directly (no DB connection) and verifies:

1. Every revision id appears exactly once.
2. Every ``down_revision`` resolves to either a known revision id, a
   tuple of known revisions (merge revisions), or ``None`` (the
   first migration).
3. There is exactly one head — exactly one revision is not referenced
   as a ``down_revision`` by any other revision (excluding merge
   parents already covered).
4. There are no cycles.

The historical bifurcation at ``0020_bots`` /
``0020_data_control_metadata`` and the merge revision
``0023_merge_data_control_branch`` is supported natively because rule
2 accepts tuple ``down_revision`` values.

Exit codes:
* 0 — graph is valid
* 1 — any of the above invariants is violated
* 2 — IO / parse error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"


_REVISION_RE = re.compile(r"^\s*revision\s*=\s*([\"']?)(?P<value>[^\"']+)\1", re.M)
_DOWN_REVISION_RE = re.compile(
    r"^\s*down_revision\s*(?::\s*[^=]*)?=\s*(?P<rhs>.+?)\s*(?:#.*)?$",
    re.M,
)


def _parse_module(path: Path) -> tuple[str, list[str] | None]:
    """Return ``(revision, down_revision_list_or_None)``.

    ``down_revision_list`` is ``None`` when the migration declares
    ``down_revision = None`` (i.e. the first migration in the chain).
    Otherwise it's a list of one or more revision ids.
    """
    text = path.read_text(encoding="utf-8")

    rev_match = _REVISION_RE.search(text)
    if not rev_match:
        raise SystemExit(f"{path.name}: missing `revision = ...` declaration")
    revision = rev_match.group("value").strip()

    down_match = _DOWN_REVISION_RE.search(text)
    if not down_match:
        raise SystemExit(f"{path.name}: missing `down_revision = ...` declaration")
    raw = down_match.group("rhs").strip()

    if raw in ("None", "none"):
        return revision, None

    # Single string literal
    single = re.fullmatch(r"[\"']([^\"']+)[\"']", raw)
    if single is not None:
        return revision, [single.group(1)]

    # Tuple of literals — supports either parenthesised or bare comma forms.
    tuple_inner = raw.strip("()[]")
    items = [item.strip().strip("\"'") for item in tuple_inner.split(",") if item.strip()]
    if items:
        return revision, items

    raise SystemExit(
        f"{path.name}: cannot parse down_revision rhs {raw!r}"
    )


def _walk() -> dict[str, list[str] | None]:
    """Return ``{revision: down_revisions or None}``."""
    if not VERSIONS_DIR.is_dir():
        raise FileNotFoundError(f"missing migrations dir: {VERSIONS_DIR}")
    graph: dict[str, list[str] | None] = {}
    for entry in sorted(VERSIONS_DIR.iterdir()):
        if entry.suffix != ".py" or entry.name.startswith("__"):
            continue
        rev, down = _parse_module(entry)
        if rev in graph:
            raise SystemExit(
                f"duplicate revision {rev!r} in {entry.name}"
            )
        graph[rev] = down
    return graph


def check_chain() -> list[str]:
    """Return a list of human-readable error messages (empty == OK)."""
    graph = _walk()
    errors: list[str] = []

    revisions = set(graph.keys())

    # Rule 2 — every parent must resolve to a known revision.
    for rev, parents in graph.items():
        if parents is None:
            continue
        for parent in parents:
            if parent not in revisions:
                errors.append(
                    f"revision {rev!r} references unknown down_revision {parent!r}"
                )

    # Rule 3 — exactly one head.
    referenced: set[str] = set()
    for parents in graph.values():
        if parents is None:
            continue
        referenced.update(parents)
    heads = sorted(rev for rev in revisions if rev not in referenced)
    if len(heads) == 0:
        errors.append("no head revision found (every revision is referenced)")
    elif len(heads) > 1:
        errors.append(
            "multiple heads detected (must be a single linear chain "
            "or merged via a merge revision): "
            + ", ".join(heads)
        )

    # Rule 4 — no cycles. Walk every revision back to root via DFS,
    # detecting any visited-on-current-path repeats.
    def dfs(start: str) -> None:
        stack: list[tuple[str, list[str]]] = [(start, list(graph.get(start) or []))]
        path: list[str] = [start]
        seen_on_path: set[str] = {start}
        while stack:
            current, remaining = stack[-1]
            if not remaining:
                stack.pop()
                seen_on_path.discard(path.pop())
                continue
            nxt = remaining.pop()
            if nxt in seen_on_path:
                errors.append(
                    f"cycle detected: {' -> '.join(path)} -> {nxt}"
                )
                continue
            parents = graph.get(nxt)
            if parents is None:
                continue
            seen_on_path.add(nxt)
            path.append(nxt)
            stack.append((nxt, list(parents)))

    for head in heads:
        dfs(head)

    return errors


def main() -> int:
    errors = check_chain()
    if errors:
        print("[migration-chain] FAIL:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("[migration-chain] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
