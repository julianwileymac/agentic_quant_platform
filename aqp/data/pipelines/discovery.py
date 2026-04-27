"""Discover logical datasets from a path (file, folder, or ZIP archive).

The discovery step walks a user-supplied path, opens any zip archives
(without fully extracting them), and groups the tabular members by stable
filename prefix so that file families like::

    2022_public_lar_csv.zip   2023_public_lar_csv.zip   2024_public_lar_csv.zip
    device-event-0001-of-0007.json.zip … 0007-of-0007.json.zip
    drug-event-0001-of-0028.json.zip   …

collapse into a single logical dataset (``lar``, ``device_event``,
``drug_event``) ready to be materialized into Iceberg.

Discovery is read-only and bounded: we only sniff the first 32 KB of any
member to detect format / delimiter so even multi-gigabyte archives
return quickly.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_TABULAR_EXTS = {".csv", ".tsv", ".psv", ".txt", ".json", ".ndjson", ".jsonl"}
_ARCHIVE_EXTS = {".zip"}
_NON_TABULAR_EXTS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".tiff", ".tif",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z",
    ".html", ".htm", ".xml",
    ".bin", ".dat",
}

_FAMILY_STRIP_PATTERNS = [
    # CFPB / generic year + section markers: 2022_public_lar_csv → public_lar_csv
    re.compile(r"^\d{4}[_-]"),
    # Trailing year/year-month suffixes: foo_2024-09 / foo_2023 → foo
    re.compile(r"[_-]\d{4}(?:[-_]\d{2})?$"),
    # Numeric "part of" variants: ipa240711 → ipa, _r1, (1)
    re.compile(r"_r\d+$", re.IGNORECASE),
    re.compile(r"\s*\(\d+\)$"),
    # "0001-of-0007" / "0001_of_0007"
    re.compile(r"[_-]\d+[_-]of[_-]\d+", re.IGNORECASE),
    # USPTO-style ipaYYMMDD → ipa
    re.compile(r"^(ipa|usrec|patgrant)\d{6,8}$", re.IGNORECASE),
    # Trailing _csv / _pipe / _psv / _json / _ndjson / _jsonl format markers
    re.compile(r"[_-](csv|pipe|psv|tsv|json|ndjson|jsonl)$", re.IGNORECASE),
    # Trailing part numbers
    re.compile(r"[_-](?:part|pt|chunk|seg)[_-]?\d+$", re.IGNORECASE),
]

_NAME_SAFE_RE = re.compile(r"[^a-z0-9_]+")
# Trailing ``(1)`` / `` (2)`` browser-style disambiguation suffix used to
# detect downloaded duplicates.
_DUP_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")


def _normalize_family(stem: str) -> str:
    """Reduce ``stem`` to a stable family key by stripping noise patterns."""
    raw = stem.lower().strip()
    raw = raw.replace(" ", "_")
    for pat in _FAMILY_STRIP_PATTERNS:
        prev = None
        while prev != raw:
            prev = raw
            raw = pat.sub("", raw).strip("_-. ")
    raw = _NAME_SAFE_RE.sub("_", raw).strip("_") or stem.lower()
    return raw


def _normalize_dir_segment(segment: str) -> str:
    """Sanitise a directory name into a snake_case segment for family keys."""
    seg = (segment or "").strip().lower().replace(" ", "_")
    seg = _NAME_SAFE_RE.sub("_", seg).strip("_")
    return seg or "dir"


def _dedup_key(file_name: str) -> str:
    """Strip the trailing ``(N)`` browser-disambiguator from a basename.

    Example::

        device-event-0001-of-0007.json (1).zip -> device-event-0001-of-0007.json.zip
    """
    p = Path(file_name)
    stem = _DUP_SUFFIX_RE.sub("", p.stem)
    return f"{stem}{p.suffix}".lower()


def _guess_format_and_delim(sample_bytes: bytes, name: str) -> tuple[str, str | None]:
    """Return ``(format, delimiter)``: format ∈ csv|json|ndjson|unknown."""
    lower = name.lower()
    if lower.endswith((".ndjson", ".jsonl")):
        return "ndjson", None
    if lower.endswith(".json"):
        head = sample_bytes.lstrip()[:1]
        if head == b"{":
            # Heuristic: NDJSON files often start with '{' too. Check for
            # newline-separated objects vs a single root object.
            if b"\n{" in sample_bytes[:8192]:
                return "ndjson", None
            return "json_array", None
        if head == b"[":
            return "json_array", None
        return "ndjson", None
    if lower.endswith((".tsv",)):
        return "csv", "\t"
    if lower.endswith((".psv",)):
        return "csv", "|"
    if lower.endswith((".csv", ".txt")):
        return "csv", _sniff_delimiter(sample_bytes)
    # Unknown extension: sniff
    head = sample_bytes.lstrip()[:1]
    if head in (b"{", b"["):
        return "ndjson" if head == b"{" else "json_array", None
    if sample_bytes:
        return "csv", _sniff_delimiter(sample_bytes)
    return "unknown", None


def _sniff_delimiter(sample_bytes: bytes) -> str | None:
    if not sample_bytes:
        return None
    try:
        text = sample_bytes.decode("utf-8", errors="replace")
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",|\t;")
        return dialect.delimiter
    except Exception:  # noqa: BLE001
        return ","


@dataclass
class DiscoveredMember:
    """A single tabular file inside a discovered dataset."""

    path: str
    archive_path: str | None
    format: str  # csv | ndjson | json_array | unknown
    delimiter: str | None
    size_bytes: int
    row_estimate: int | None = None
    # Immediate-parent directory of ``path`` relative to the discovery
    # root (empty when the file/zip is at the root level). Used for
    # SEC-style subdirectory disambiguation so that
    # ``financial_statement_data_sets/2024q1.zip`` and
    # ``business_development_companies_data_sets/2024q1_bdc.zip`` keep
    # different family keys instead of collapsing on ``q1``/``bdc``.
    subdir: str = ""
    # mtime of the *outer* host file (the zip itself, or the plain file
    # when not in an archive). Used by the duplicate-suppression step in
    # :func:`discover_datasets` to keep the most recently downloaded
    # copy when multiple files map to the same dedup key.
    outer_mtime: float = 0.0


@dataclass
class DiscoveredDataset:
    """A collection of one or more :class:`DiscoveredMember` rows.

    Members are grouped by a stable filename family so that downstream
    materialization writes them all into a single Iceberg table.
    """

    family: str
    members: list[DiscoveredMember] = field(default_factory=list)
    total_bytes: int = 0
    sample_columns: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    inventory_extra: list[dict[str, Any]] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.members)

    @property
    def member_format(self) -> str:
        if not self.members:
            return "unknown"
        # Members of one family should share format; pick the first.
        return self.members[0].format

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "file_count": self.file_count,
            "format": self.member_format,
            "delimiter": self.members[0].delimiter if self.members else None,
            "total_bytes": int(self.total_bytes),
            "sample_columns": list(self.sample_columns),
            "notes": list(self.notes),
            "inventory_extra": list(self.inventory_extra),
            "members": [
                {
                    "path": m.path,
                    "archive_path": m.archive_path,
                    "format": m.format,
                    "delimiter": m.delimiter,
                    "size_bytes": int(m.size_bytes),
                }
                for m in self.members
            ],
        }


# ---------------------------------------------------------------------------
# Path walkers
# ---------------------------------------------------------------------------


def _iter_filesystem(root: Path) -> list[tuple[Path, str, int]]:
    """Yield ``(path, subdir, size)`` for every file under ``root``.

    ``subdir`` is the immediate-parent directory name relative to
    ``root`` (e.g. ``"financial_statement_data_sets"``). Empty string
    when the file lives directly under ``root`` (or when ``root`` itself
    is a file). Deeper sub-paths collapse to the *first* segment so
    grouping stays human-readable; the LLM Director can split further.
    """
    out: list[tuple[Path, str, int]] = []
    if root.is_file():
        out.append((root, "", root.stat().st_size))
        return out
    for dirpath, _dirs, files in os.walk(root):
        rel: Path
        try:
            rel = Path(dirpath).resolve().relative_to(root.resolve())
        except ValueError:  # pragma: no cover
            rel = Path("")
        first_seg = rel.parts[0] if rel.parts else ""
        for fname in files:
            p = Path(dirpath) / fname
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            out.append((p, first_seg, size))
    return out


def _peek_sample(zf: zipfile.ZipFile | None, member: str, *, real_path: Path | None) -> bytes:
    """Read up to 32 KB from a member or filesystem file for sniffing."""
    try:
        if zf is not None:
            with zf.open(member) as fh:
                return fh.read(32 * 1024)
        if real_path is not None:
            with real_path.open("rb") as fh:
                return fh.read(32 * 1024)
    except Exception:  # noqa: BLE001
        return b""
    return b""


def _detect_columns(sample_bytes: bytes, fmt: str, delimiter: str | None) -> list[str]:
    if not sample_bytes:
        return []
    text = sample_bytes.decode("utf-8", errors="replace")
    if fmt == "csv":
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter or ",")
            row = next(reader, None)
            return [c.strip() for c in (row or []) if c.strip()]
        except Exception:  # noqa: BLE001
            return []
    if fmt == "ndjson":
        first_line = text.splitlines()[0] if text.splitlines() else ""
        try:
            import json

            obj = json.loads(first_line) if first_line else {}
            if isinstance(obj, dict):
                return list(obj.keys())
        except Exception:  # noqa: BLE001
            return []
    if fmt == "json_array":
        try:
            import json

            obj = json.loads(text)
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                return list(obj[0].keys())
            if isinstance(obj, dict):
                # OpenFDA wraps objects under {"results": [...]}.
                for key in ("results", "data", "items", "records"):
                    if key in obj and isinstance(obj[key], list) and obj[key]:
                        first = obj[key][0]
                        if isinstance(first, dict):
                            return list(first.keys())
        except Exception:  # noqa: BLE001
            return []
    return []


def _file_family(file_name: str) -> str:
    stem = Path(file_name).stem
    # Strip double-extension cases like ``foo.json.zip``.
    if "." in stem:
        stem = stem.split(".")[0]
    return _normalize_family(stem)


def _classify_member(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in _TABULAR_EXTS:
        return "tabular"
    if suffix in _ARCHIVE_EXTS:
        return "archive"
    return "other"


def _walk_zip_members(
    zip_path: Path,
    *,
    subdir: str = "",
    max_archive_recursion: int = 1,
) -> list[DiscoveredMember]:
    """Walk a zip's members, descending one level into nested archives."""
    members: list[DiscoveredMember] = []
    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except (zipfile.BadZipFile, OSError):  # pragma: no cover
        logger.warning("could not open %s as zip", zip_path)
        return members
    try:
        try:
            outer_mtime = zip_path.stat().st_mtime
        except OSError:
            outer_mtime = 0.0
        for info in zf.infolist():
            if info.is_dir():
                continue
            kind = _classify_member(info.filename)
            if kind == "tabular":
                sample = _peek_sample(zf, info.filename, real_path=None)
                fmt, delim = _guess_format_and_delim(sample, info.filename)
                members.append(
                    DiscoveredMember(
                        path=str(zip_path),
                        archive_path=info.filename,
                        format=fmt,
                        delimiter=delim,
                        size_bytes=int(info.file_size),
                        subdir=subdir,
                        outer_mtime=outer_mtime,
                    )
                )
            elif kind == "archive" and max_archive_recursion > 0:
                # Spool the nested archive to a temp file so zipfile can re-open it.
                with zf.open(info.filename) as src:
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        prefix="aqp_zip_", suffix=".zip", delete=False
                    ) as tmp:
                        tmp.write(src.read())
                        tmp_path = Path(tmp.name)
                try:
                    nested = _walk_zip_members(
                        tmp_path,
                        subdir=subdir,
                        max_archive_recursion=max_archive_recursion - 1,
                    )
                except Exception:  # noqa: BLE001
                    nested = []
                for nm in nested:
                    nm.archive_path = f"{info.filename}::{nm.archive_path or ''}"
                    nm.path = str(zip_path)
                    nm.subdir = subdir
                    nm.outer_mtime = outer_mtime
                members.extend(nested)
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
            else:
                # Non-tabular members are tracked separately at the dataset level.
                members.append(
                    DiscoveredMember(
                        path=str(zip_path),
                        archive_path=info.filename,
                        format="other",
                        delimiter=None,
                        size_bytes=int(info.file_size),
                        subdir=subdir,
                        outer_mtime=outer_mtime,
                    )
                )
    finally:
        zf.close()
    return members


def _family_key(subdir: str, leaf_name: str) -> str:
    """Combine optional subdir prefix with the normalised leaf family.

    When the file lives directly under the discovery root (``subdir``
    empty), this is just :func:`_file_family`. When it lives under a
    sub-directory, the directory name is folded in with a ``__`` joiner
    so SEC-style sibling subdirs ([``financial_statement_data_sets``,
    ``business_development_companies_data_sets``, ...]) keep their own
    family namespaces even when leaf names collide.
    """
    leaf_family = _file_family(leaf_name)
    if not subdir:
        return leaf_family
    sub_norm = _normalize_dir_segment(subdir)
    if not sub_norm:
        return leaf_family
    return f"{sub_norm}__{leaf_family}"


def _member_dedup_signature(m: DiscoveredMember) -> str:
    """Stable signature for collapsing duplicate downloads.

    Combines the outer file's basename (with ``(N)`` browser suffix
    stripped) and the inner-archive leaf name (when applicable). Two
    members sharing this signature are treated as duplicates of each
    other in :func:`discover_datasets`.
    """
    outer_dedup = _dedup_key(Path(m.path).name)
    if not m.archive_path:
        return outer_dedup
    inner_leaf = m.archive_path.split("::", 1)[0].split("/")[-1]
    return f"{outer_dedup}::{inner_leaf.lower()}"


def discover_datasets(path: Path | str) -> list[DiscoveredDataset]:
    """Walk ``path`` and return one :class:`DiscoveredDataset` per family."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)

    raw_members: list[DiscoveredMember] = []

    if root.is_file():
        suffix = root.suffix.lower()
        outer_mtime = 0.0
        try:
            outer_mtime = root.stat().st_mtime
        except OSError:
            pass
        if suffix in _ARCHIVE_EXTS:
            raw_members.extend(_walk_zip_members(root))
        else:
            sample = _peek_sample(None, root.name, real_path=root)
            fmt, delim = _guess_format_and_delim(sample, root.name)
            raw_members.append(
                DiscoveredMember(
                    path=str(root),
                    archive_path=None,
                    format=fmt,
                    delimiter=delim,
                    size_bytes=root.stat().st_size,
                    subdir="",
                    outer_mtime=outer_mtime,
                )
            )
    else:
        for fpath, subdir, size in _iter_filesystem(root):
            suffix = fpath.suffix.lower()
            try:
                outer_mtime = fpath.stat().st_mtime
            except OSError:
                outer_mtime = 0.0
            if suffix in _ARCHIVE_EXTS:
                raw_members.extend(_walk_zip_members(fpath, subdir=subdir))
            elif suffix in _TABULAR_EXTS:
                sample = _peek_sample(None, fpath.name, real_path=fpath)
                fmt, delim = _guess_format_and_delim(sample, fpath.name)
                raw_members.append(
                    DiscoveredMember(
                        path=str(fpath),
                        archive_path=None,
                        format=fmt,
                        delimiter=delim,
                        size_bytes=size,
                        subdir=subdir,
                        outer_mtime=outer_mtime,
                    )
                )
            elif suffix in _NON_TABULAR_EXTS:
                raw_members.append(
                    DiscoveredMember(
                        path=str(fpath),
                        archive_path=None,
                        format="other",
                        delimiter=None,
                        size_bytes=size,
                        subdir=subdir,
                        outer_mtime=outer_mtime,
                    )
                )

    # Bucket each member into either the tabular stream (which we then
    # group by family) or the ``other`` stream (which feeds
    # ``__assets__``).  We dedupe along the way: members that share the
    # same ``(subdir, family, dedup_signature)`` are treated as multiple
    # copies of the same logical thing — keep the most recent download
    # and record the rest in per-dataset notes.
    by_family: dict[tuple[str, str], DiscoveredDataset] = {}
    seen_dedup: dict[tuple[str, str, str], DiscoveredMember] = {}
    duplicates_per_family: dict[tuple[str, str], list[dict[str, Any]]] = {}
    extras: list[dict[str, Any]] = []
    extras_seen: set[str] = set()
    has_xml_assets = False

    for m in raw_members:
        # Other (non-tabular) members go to extras, also deduped.
        if m.format == "other":
            extras_key = _member_dedup_signature(m)
            inner_leaf = (m.archive_path or m.path).split("/")[-1].lower()
            if inner_leaf.endswith(".xml"):
                has_xml_assets = True
            if extras_key in extras_seen:
                continue
            extras_seen.add(extras_key)
            extras.append(
                {
                    "path": m.path,
                    "archive_path": m.archive_path,
                    "size_bytes": m.size_bytes,
                    "subdir": m.subdir,
                }
            )
            continue

        # Family from archive_path member name when present, else file stem.
        leaf = (m.archive_path or m.path).split("/")[-1]
        family = _family_key(m.subdir, leaf)
        family_key = (m.subdir, family)
        sig = _member_dedup_signature(m)
        dedup_key = (m.subdir, family, sig)
        existing = seen_dedup.get(dedup_key)
        if existing is not None:
            # Newer mtime wins; older one becomes a recorded duplicate.
            losing = m if existing.outer_mtime >= m.outer_mtime else existing
            winner = existing if losing is m else m
            seen_dedup[dedup_key] = winner
            duplicates_per_family.setdefault(family_key, []).append(
                {
                    "path": losing.path,
                    "archive_path": losing.archive_path,
                    "size_bytes": int(losing.size_bytes),
                    "kept_path": winner.path,
                    "reason": "duplicate-suffix-suppressed",
                }
            )
            if winner is not existing:
                # The previously-kept one is now the loser; remove from
                # the dataset and replace with the new winner.
                ds = by_family.get(family_key)
                if ds is not None:
                    ds.members = [mb for mb in ds.members if mb is not existing]
                    ds.total_bytes -= int(existing.size_bytes)
                ds = by_family.setdefault(
                    family_key, DiscoveredDataset(family=family)
                )
                ds.members.append(winner)
                ds.total_bytes += int(winner.size_bytes)
            continue

        seen_dedup[dedup_key] = m
        ds = by_family.setdefault(family_key, DiscoveredDataset(family=family))
        ds.members.append(m)
        ds.total_bytes += int(m.size_bytes)

    # Stamp duplicate-suppression notes onto each affected dataset.
    for family_key, dups in duplicates_per_family.items():
        ds = by_family.get(family_key)
        if ds is None:
            continue
        ds.notes.append(
            f"Suppressed {len(dups)} duplicate-suffixed copy/copies "
            "(kept newest mtime per dedup key)."
        )
        ds.inventory_extra.extend(dups)

    # Sniff sample columns from the first member of each family.
    for ds in by_family.values():
        if not ds.members:
            continue
        first = ds.members[0]
        zf = None
        try:
            if first.archive_path:
                zf = zipfile.ZipFile(first.path, "r")
                # archive_path may be nested (``foo.zip::bar.csv``); we sniff
                # only the outermost member here so initial discovery stays fast.
                outer = first.archive_path.split("::", 1)[0]
                sample = _peek_sample(zf, outer, real_path=None)
            else:
                sample = _peek_sample(None, first.path, real_path=Path(first.path))
            ds.sample_columns = _detect_columns(sample, first.format, first.delimiter)
        except Exception:  # noqa: BLE001
            ds.sample_columns = []
        finally:
            if zf is not None:
                zf.close()

    # Attach the non-tabular inventory to a synthetic ``__assets`` group when
    # it isn't empty, so the wizard can still surface "we saw 10 PDFs / 3
    # XLSX files alongside the data" without polluting the dataset list.
    out = sorted(by_family.values(), key=lambda d: d.family)
    if extras:
        synthetic = DiscoveredDataset(family="__assets__")
        synthetic.notes.append(
            f"Tracked {len(extras)} non-tabular asset(s); skipped at materialize time."
        )
        if has_xml_assets:
            synthetic.notes.append(
                "USPTO-style patent XML detected; XML extractor not enabled "
                "in this run — XML assets are inventoried but not ingested."
            )
        synthetic.inventory_extra = extras
        out.append(synthetic)
    return out
