"""Dataset + code lineage tracking."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


def hash_dataframe(df: pd.DataFrame) -> str:
    buf = pd.util.hash_pandas_object(df, index=False).values.tobytes()
    return hashlib.sha256(buf).hexdigest()


def hash_parquet_dir(path: str | Path) -> str:
    """Stable hash across all parquet files in a directory."""
    root = Path(path)
    hasher = hashlib.sha256()
    for p in sorted(root.rglob("*.parquet")):
        hasher.update(p.name.encode())
        stat = p.stat()
        hasher.update(str(stat.st_size).encode())
        hasher.update(str(int(stat.st_mtime)).encode())
    return hasher.hexdigest()


def hash_file(path: str | Path) -> str:
    p = Path(path)
    hasher = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
