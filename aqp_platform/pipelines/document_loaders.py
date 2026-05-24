"""Document loading helpers for PDF, CSV, and directory-based sources."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LoadedDocument:
    """A loaded document with text content and metadata."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def load_pdf_bytes(data: bytes, source_name: str = "unknown") -> list[LoadedDocument]:
    """Extract text from a PDF byte stream using pymupdf (fitz)."""
    import fitz  # pymupdf

    docs: list[LoadedDocument] = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            text = page.get_text("text")
            if text.strip():
                docs.append(
                    LoadedDocument(
                        text=text,
                        metadata={
                            "source": source_name,
                            "page": page_num + 1,
                            "total_pages": len(pdf),
                        },
                    )
                )
    return docs


def load_pdf_file(path: str | Path) -> list[LoadedDocument]:
    """Load a PDF from the local filesystem."""
    path = Path(path)
    return load_pdf_bytes(path.read_bytes(), source_name=str(path))


def load_csv_bytes(
    data: bytes,
    source_name: str = "unknown",
    text_columns: list[str] | None = None,
) -> list[LoadedDocument]:
    """Load CSV rows as documents.  If *text_columns* is given, only those
    columns are concatenated into the document text; otherwise all columns
    are used.  Each row becomes one document with remaining fields as metadata.
    """
    reader = csv.DictReader(io.StringIO(data.decode("utf-8", errors="replace")))
    docs: list[LoadedDocument] = []
    for row_idx, row in enumerate(reader):
        if text_columns:
            text_parts = [str(row.get(col, "")) for col in text_columns if row.get(col)]
            meta_keys = [k for k in row if k not in text_columns]
        else:
            text_parts = [f"{k}: {v}" for k, v in row.items() if v]
            meta_keys = []

        text = "\n".join(text_parts)
        if not text.strip():
            continue

        meta: dict[str, Any] = {"source": source_name, "row_index": row_idx}
        for k in meta_keys:
            meta[k] = row[k]
        docs.append(LoadedDocument(text=text, metadata=meta))
    return docs


def load_csv_file(
    path: str | Path,
    text_columns: list[str] | None = None,
) -> list[LoadedDocument]:
    """Load a CSV from the local filesystem."""
    path = Path(path)
    return load_csv_bytes(path.read_bytes(), source_name=str(path), text_columns=text_columns)


def load_text_bytes(data: bytes, source_name: str = "unknown") -> list[LoadedDocument]:
    """Load a plain-text or markdown file as a single document."""
    text = data.decode("utf-8", errors="replace")
    if not text.strip():
        return []
    return [LoadedDocument(text=text, metadata={"source": source_name})]


def load_directory(
    directory: str | Path,
    glob_pattern: str = "**/*",
    recursive: bool = True,
) -> list[LoadedDocument]:
    """Load all supported files from a directory tree."""
    directory = Path(directory)
    docs: list[LoadedDocument] = []
    pattern = glob_pattern if recursive else glob_pattern.replace("**/", "")
    for path in sorted(directory.glob(pattern)):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            docs.extend(load_pdf_file(path))
        elif suffix == ".csv":
            docs.extend(load_csv_file(path))
        elif suffix in {".txt", ".md", ".rst", ".json", ".jsonl"}:
            docs.extend(load_text_bytes(path.read_bytes(), source_name=str(path)))
    return docs


def load_minio_object(
    config: Any,
    bucket: str,
    key: str,
) -> list[LoadedDocument]:
    """Download an object from MinIO and load it based on file extension."""
    from .minio_io import get_bytes, get_minio_client

    client = get_minio_client(config)
    data = get_bytes(client=client, bucket=bucket, key=key)
    suffix = Path(key).suffix.lower()
    if suffix == ".pdf":
        return load_pdf_bytes(data, source_name=f"s3://{bucket}/{key}")
    if suffix == ".csv":
        return load_csv_bytes(data, source_name=f"s3://{bucket}/{key}")
    return load_text_bytes(data, source_name=f"s3://{bucket}/{key}")
