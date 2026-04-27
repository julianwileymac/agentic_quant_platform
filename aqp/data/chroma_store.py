"""ChromaDB metadata & semantic-discovery layer.

Exposes two collections:

- ``datasets`` — file-level metadata + schema + sample rows, so the Data Scout
  can ask natural-language questions like *"find me minute-level volatility
  data for tech sector"*.
- ``memories`` — long-term agent memory (strategy notes, research findings).

Uses Chroma's in-process client when running locally, HTTP client in docker.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)

_DATASETS_COLLECTION = "aqp_datasets"
_MEMORY_COLLECTION = "aqp_memory"
_CODE_COLLECTION = "aqp_code_snippets"


def _client():
    """Prefer an embedded PersistentClient — no network, no version mismatch.

    If ``AQP_CHROMA_HOST`` is explicitly set to a non-localhost value we
    try an HTTP client and **fail loudly** if it cannot be reached. This
    matters because our ``/health`` probe constructs ``ChromaStore()``
    and we want a misconfigured port to surface visibly rather than
    silently fall back to embedded mode (which would mask the bug).
    """
    import chromadb

    host = settings.chroma_host
    if host and host not in {"localhost", "127.0.0.1", "0.0.0.0", ""}:
        client = chromadb.HttpClient(host=host, port=settings.chroma_port)
        # Force a round-trip so we surface unreachable servers immediately
        # rather than at the first collection access.
        try:
            client.heartbeat()
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Chroma HTTP client unreachable at %s:%d", host, settings.chroma_port
            )
            raise RuntimeError(
                f"Chroma server at {host}:{settings.chroma_port} is unreachable: {exc}"
            ) from exc
        return client
    Path(settings.chroma_dir).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def _embedding_fn():
    """Pick the lightest available embedder.

    - ``sentence-transformers`` if installed (best quality).
    - Chroma's built-in ONNX ``DefaultEmbeddingFunction`` otherwise.
    """
    from chromadb.utils import embedding_functions

    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.chroma_embedding_model
        )
    except Exception:
        try:
            return embedding_functions.DefaultEmbeddingFunction()
        except Exception:
            logger.warning("No embedding function available — Chroma will use stub vectors.")
            return None


class ChromaStore:
    """Thin wrapper over ChromaDB with application-specific collections."""

    def __init__(self) -> None:
        self.client = _client()
        self.ef = _embedding_fn()
        self.datasets = self.client.get_or_create_collection(
            _DATASETS_COLLECTION, embedding_function=self.ef
        )
        self.memory = self.client.get_or_create_collection(
            _MEMORY_COLLECTION, embedding_function=self.ef
        )
        self.code = self.client.get_or_create_collection(
            _CODE_COLLECTION, embedding_function=self.ef
        )

    # ---- datasets ---------------------------------------------------------

    def index_parquet_dir(self, parquet_dir: Path | str | None = None) -> int:
        """Walk a Parquet directory and index each file's schema + date range."""
        root = Path(parquet_dir or (Path(settings.parquet_dir) / "bars"))
        if not root.exists():
            logger.warning("No parquet dir at %s", root)
            return 0

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        for file in sorted(root.glob("*.parquet")):
            try:
                df = pd.read_parquet(file)
            except Exception:
                logger.exception("Failed to read %s", file)
                continue
            if df.empty:
                continue
            vt_symbol = df["vt_symbol"].iloc[0] if "vt_symbol" in df.columns else file.stem
            first_ts = str(df["timestamp"].min()) if "timestamp" in df.columns else ""
            last_ts = str(df["timestamp"].max()) if "timestamp" in df.columns else ""
            summary = (
                f"Dataset for {vt_symbol}. "
                f"Columns: {', '.join(df.columns)}. "
                f"Rows: {len(df)}. "
                f"Date range: {first_ts} to {last_ts}."
            )
            ids.append(str(file))
            docs.append(summary)
            metas.append(
                {
                    "path": str(file),
                    "vt_symbol": str(vt_symbol),
                    "rows": int(len(df)),
                    "first_ts": first_ts,
                    "last_ts": last_ts,
                    "columns": ",".join(df.columns),
                }
            )

        if not ids:
            return 0
        self.datasets.upsert(ids=ids, documents=docs, metadatas=metas)
        logger.info("Indexed %d parquet datasets into ChromaDB", len(ids))
        return len(ids)

    def search_datasets(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        res = self.datasets.query(query_texts=[query], n_results=k)
        return _pack_results(res)

    # ---- memory (agent reflections / notes) -------------------------------

    def remember(
        self,
        text: str,
        role: str = "agent",
        tags: Iterable[str] = (),
        extra: dict[str, Any] | None = None,
    ) -> str:
        import uuid

        mid = str(uuid.uuid4())
        meta = {"role": role, "tags": ",".join(tags), **(extra or {})}
        meta = {k: str(v) if not isinstance(v, (int, float, bool, str)) else v for k, v in meta.items()}
        self.memory.add(ids=[mid], documents=[text], metadatas=[meta])
        return mid

    def recall(self, query: str, k: int = 5, role: str | None = None) -> list[dict[str, Any]]:
        where = {"role": role} if role else None
        res = self.memory.query(query_texts=[query], n_results=k, where=where)
        return _pack_results(res)

    # ---- code snippets ----------------------------------------------------

    def index_code(self, snippets: Iterable[dict[str, Any]]) -> int:
        payload = list(snippets)
        if not payload:
            return 0
        self.code.upsert(
            ids=[p["id"] for p in payload],
            documents=[p["text"] for p in payload],
            metadatas=[{k: v for k, v in p.items() if k not in ("id", "text")} for p in payload],
        )
        return len(payload)

    def search_code(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        res = self.code.query(query_texts=[query], n_results=k)
        return _pack_results(res)


def _pack_results(res: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not res.get("ids") or not res["ids"][0]:
        return out
    ids = res["ids"][0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for i, id_ in enumerate(ids):
        out.append(
            {
                "id": id_,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return out


def _redact_json(x: Any) -> str:
    try:
        return json.dumps(x, default=str)
    except Exception:
        return str(x)
