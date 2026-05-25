"""Enforce AGENTS Rule 6 — Alembic migrations are immutable once shipped.

Compares the SHA-256 of every file in ``alembic/versions/`` against
the canonical lock at ``alembic/versions/.hashes.lock`` (a JSON object
``{filename: sha256_hex}``).

Operations:

* ``--check`` (default): exit non-zero when any locked file has
  changed. New (unlocked) files are reported but do NOT fail unless
  ``--strict-new`` is also passed.
* ``--update``: regenerate the lock file from the current state. Used
  ONCE at lock seeding; never run in CI.
* ``--strict-new``: also fail when a new migration is missing from
  the lock. Useful for branches that intentionally freeze the chain.

Exit codes:
* 0 — clean
* 1 — drift on existing entries (Rule 6 violation)
* 2 — usage error / IO error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"
LOCK_PATH = VERSIONS_DIR / ".hashes.lock"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _enumerate_migrations() -> dict[str, str]:
    """Return ``{filename: sha256}`` for every ``*.py`` migration file."""
    if not VERSIONS_DIR.is_dir():
        raise FileNotFoundError(f"missing migrations dir: {VERSIONS_DIR}")
    out: dict[str, str] = {}
    for entry in sorted(VERSIONS_DIR.iterdir()):
        if entry.suffix != ".py":
            continue
        if entry.name.startswith("__"):
            continue
        out[entry.name] = _hash_file(entry)
    return out


def _load_lock() -> dict[str, str]:
    if not LOCK_PATH.is_file():
        return {}
    try:
        return dict(json.loads(LOCK_PATH.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"corrupt lock file at {LOCK_PATH}: {exc}") from exc


def _write_lock(payload: dict[str, str]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    LOCK_PATH.write_text(text, encoding="utf-8")


def cmd_check(*, strict_new: bool) -> int:
    actual = _enumerate_migrations()
    expected = _load_lock()

    if not expected:
        print(
            "[migration-immutability] WARNING: no lock file at "
            f"{LOCK_PATH.relative_to(REPO_ROOT)}. Generate one with "
            "`python scripts/ci/check_migration_immutability.py --update`."
        )
        # An empty lock cannot be enforced; treat as soft-pass so the
        # gate's first deployment lands without forcing a hard fail
        # before the seed commit.
        return 0

    drifted: list[str] = []
    missing_from_disk: list[str] = []
    new_unlocked: list[str] = []

    for name, locked_hash in expected.items():
        on_disk = actual.get(name)
        if on_disk is None:
            missing_from_disk.append(name)
            continue
        if on_disk != locked_hash:
            drifted.append(name)

    for name in actual:
        if name not in expected:
            new_unlocked.append(name)

    if drifted:
        print("[migration-immutability] FAIL: locked migrations were modified:")
        for name in drifted:
            print(f"  - {name}")
            print(f"      expected: {expected[name]}")
            print(f"      actual:   {actual[name]}")
        print(
            "\nAGENTS Rule 6 forbids editing a previously-shipped "
            "migration. Write a new migration to correct the schema "
            "or, if absolutely necessary, an alembic_version repair "
            "script.\n"
        )

    if missing_from_disk:
        print("[migration-immutability] FAIL: locked migrations are missing on disk:")
        for name in missing_from_disk:
            print(f"  - {name}")

    if new_unlocked:
        print(
            "[migration-immutability] INFO: new migrations not yet "
            "in the lock (run `--update` to add them):"
        )
        for name in new_unlocked:
            print(f"  - {name}")

    if drifted or missing_from_disk:
        return 1
    if strict_new and new_unlocked:
        return 1
    print(
        "[migration-immutability] OK: "
        f"{len(expected)} locked, {len(new_unlocked)} new (unlocked)."
    )
    return 0


def cmd_update() -> int:
    actual = _enumerate_migrations()
    _write_lock(actual)
    print(
        f"[migration-immutability] wrote {len(actual)} entries to "
        f"{LOCK_PATH.relative_to(REPO_ROOT)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Regenerate the lock file from the current migrations dir.",
    )
    parser.add_argument(
        "--strict-new",
        action="store_true",
        help="Fail when new migrations are not yet in the lock.",
    )
    args = parser.parse_args(argv)

    if args.update:
        return cmd_update()
    return cmd_check(strict_new=args.strict_new)


if __name__ == "__main__":
    sys.exit(main())
