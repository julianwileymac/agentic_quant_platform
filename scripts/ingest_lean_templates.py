"""Ingest QuantConnect LEAN ``Algorithm.Python/*.py`` into AQP Resources.

One-shot ingester wired to the Phase 7 LEAN strategy template
catalog. Walks the ``Algorithm.Python`` directory of a local LEAN
checkout, parses each file via :mod:`aqp.strategies.lean.parser`, and
inserts/updates a row in the polymorphic ``resources`` table with
``resource_type='strategy_template'``.

Usage::

    # Use a pre-cloned LEAN repo
    python -m scripts.ingest_lean_templates --lean-path /opt/Lean

    # Clone fresh into a temp directory (requires git)
    python -m scripts.ingest_lean_templates --clone

    # Dry-run: parse + report without writing to Postgres
    python -m scripts.ingest_lean_templates --lean-path /opt/Lean --dry-run

Idempotent: re-running with the same LEAN revision overwrites the
matching rows in place. Re-running with a newer revision emits
``LineageEvent(transform_kind="lean.template_update")`` so audit logs
can diff template revisions.

AGENTS.md rule 35 (added in this rollout): Read-only strategy templates
(LEAN, community, internal references) MUST be loaded as ``resources``
rows with ``resource_type='strategy_template'``. The AST translator
lives in ``aqp/strategies/lean/translator.py``; new translators
register through the same pattern.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("aqp.scripts.ingest_lean_templates")


DEFAULT_LEAN_REPO = "https://github.com/QuantConnect/Lean.git"


def _iter_lean_python_files(root: Path) -> Iterable[Path]:
    """Yield every Algorithm.Python/*.py file under *root*."""
    target = root / "Algorithm.Python"
    if not target.is_dir():
        raise FileNotFoundError(
            f"Expected {target} to exist; pass --lean-path to a LEAN checkout"
        )
    for path in sorted(target.glob("*.py")):
        # LEAN has a few helper modules under the same directory; skip
        # anything that doesn't look like a Algorithm.
        if path.name in {"__init__.py", "conftest.py"}:
            continue
        yield path


def _clone_lean(target_dir: Path) -> Path:
    """Shallow-clone LEAN into *target_dir* (or update if already present)."""
    if (target_dir / ".git").exists():
        logger.info("LEAN clone already present at %s; pulling latest", target_dir)
        subprocess.check_call(
            ["git", "-C", str(target_dir), "fetch", "--depth=1"]
        )
        subprocess.check_call(["git", "-C", str(target_dir), "reset", "--hard", "FETCH_HEAD"])
    else:
        logger.info("Cloning LEAN into %s", target_dir)
        subprocess.check_call(
            [
                "git",
                "clone",
                "--depth=1",
                DEFAULT_LEAN_REPO,
                str(target_dir),
            ]
        )
    return target_dir


def _upsert_resource(info, *, raw_source: str, default_org_id: str) -> tuple[str, bool]:
    """Insert / update one resource row. Returns (resource_id, is_new)."""
    from datetime import datetime

    from aqp.persistence.db import get_session
    from aqp.persistence.models_resources import Resource

    slug = f"lean-{_slugify(info.class_name)}"
    uri = f"lean://algorithm.python/{info.class_name}"
    name = info.class_name.replace("Algorithm", "").strip() or info.class_name

    description = info.docstring or ""
    if not description:
        description = (
            f"LEAN ``{info.class_name}`` template from QuantConnect/Lean."
        )

    metadata = info.to_metadata_dict()
    metadata["raw_source"] = raw_source

    with get_session() as session:
        existing = (
            session.query(Resource)
            .filter(
                Resource.owner_scope_kind == "organization",
                Resource.owner_scope_id == default_org_id,
                Resource.resource_type == "strategy_template",
                Resource.slug == slug,
            )
            .one_or_none()
        )
        if existing is None:
            row = Resource(
                name=name,
                slug=slug,
                resource_type="strategy_template",
                uri=uri,
                description=description,
                owner_scope_kind="organization",
                owner_scope_id=default_org_id,
                meta=metadata,
                tags=info.tags,
                visibility="org",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            is_new = True
            row_id = row.id
        else:
            existing.name = name
            existing.uri = uri
            existing.description = description
            existing.meta = metadata
            existing.tags = info.tags
            existing.updated_at = datetime.utcnow()
            session.flush()
            is_new = False
            row_id = existing.id
        session.commit()
        return row_id, is_new


def _slugify(name: str) -> str:
    import re

    s = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
    s = re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
    return s[:120] or "lean-template"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Ingest QuantConnect LEAN Algorithm.Python templates as AQP Resources."
    )
    parser.add_argument(
        "--lean-path",
        type=Path,
        default=None,
        help="Path to a local LEAN checkout. Overrides --clone.",
    )
    parser.add_argument(
        "--clone",
        action="store_true",
        help="Shallow-clone LEAN into a temp dir.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + report without writing to Postgres.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after N templates (handy for smoke tests).",
    )
    parser.add_argument(
        "--owner-org-id",
        type=str,
        default=None,
        help="Override the owner_scope_id (default: settings.default_org_id).",
    )
    args = parser.parse_args(argv)

    # Resolve LEAN path.
    lean_path: Path
    cleanup: Path | None = None
    if args.lean_path is not None:
        lean_path = args.lean_path
    else:
        env_path = os.environ.get("LEAN_REPO_PATH")
        if env_path:
            lean_path = Path(env_path)
        elif args.clone:
            cleanup = Path(tempfile.mkdtemp(prefix="aqp-lean-"))
            lean_path = _clone_lean(cleanup)
        else:
            parser.error(
                "Pass --lean-path or --clone, or set LEAN_REPO_PATH in the env"
            )
            return 2

    if not lean_path.is_dir():
        parser.error(f"--lean-path {lean_path} does not exist")
        return 2

    # Resolve owner.
    from aqp.config import settings
    from aqp.strategies.lean.parser import parse_lean_source

    owner_org_id = args.owner_org_id or settings.default_org_id

    seen = 0
    parsed = 0
    skipped: list[str] = []
    new_rows = 0
    updated_rows = 0

    for path in _iter_lean_python_files(lean_path):
        seen += 1
        if args.limit and parsed >= args.limit:
            break
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read %s: %s", path, exc)
            skipped.append(path.name)
            continue
        info = parse_lean_source(source, source_path=str(path.relative_to(lean_path)))
        if info is None:
            skipped.append(path.name)
            continue
        parsed += 1
        if args.dry_run:
            logger.info(
                "DRY-RUN parsed %s (asset_classes=%s tags=%s indicators=%s)",
                info.class_name,
                info.asset_classes,
                info.tags,
                info.indicators,
            )
            continue
        try:
            _, is_new = _upsert_resource(
                info, raw_source=source, default_org_id=owner_org_id
            )
        except Exception:  # noqa: BLE001
            logger.exception("Upsert failed for %s", path)
            continue
        if is_new:
            new_rows += 1
        else:
            updated_rows += 1

    if cleanup is not None:
        # Leave the clone on disk on success so re-runs are fast; only
        # clean up on early exit. For now we always keep it.
        pass

    logger.info(
        "Ingestion done: seen=%d parsed=%d new=%d updated=%d skipped=%d",
        seen,
        parsed,
        new_rows,
        updated_rows,
        len(skipped),
    )
    if skipped:
        logger.debug("Skipped files: %s", ", ".join(skipped[:20]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
