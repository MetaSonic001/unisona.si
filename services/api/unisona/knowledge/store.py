"""Vector (Chroma) and keyword (bm25s) indexes.

Chroma: one collection per workspace (`ws_<id>`), filtered by `kb_id` metadata.
bm25s: one index per knowledge base on disk, rebuilt after each ingest (local Chroma
cannot index sparse vectors). Both are tenant-isolated by construction.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import threading
from pathlib import Path

from ..config import settings
from ..log import get_logger

log = get_logger("store")
_client = None
_client_lock = threading.Lock()
_bm25_cache: dict[str, tuple[object, list[str]]] = {}


def chroma():
    global _client
    with _client_lock:
        if _client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            if settings.chroma_mode == "server":
                from urllib.parse import urlparse

                u = urlparse(settings.chroma_url)
                _client = chromadb.HttpClient(host=u.hostname, port=u.port or 8000)
            else:
                path = settings.resolve_path(settings.chroma_path)
                path.mkdir(parents=True, exist_ok=True)
                _client = chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))
    return _client


def collection(ws_id: str):
    return chroma().get_or_create_collection(name=f"ws_{ws_id}", metadata={"hnsw:space": "cosine"})


def _upsert_sync(ws_id: str, ids, embeddings, documents, metadatas):
    col = collection(ws_id)
    for i in range(0, len(ids), 256):
        col.upsert(ids=ids[i:i + 256], embeddings=embeddings[i:i + 256], documents=documents[i:i + 256], metadatas=metadatas[i:i + 256])


async def upsert(ws_id: str, ids, embeddings, documents, metadatas):
    await asyncio.to_thread(_upsert_sync, ws_id, ids, embeddings, documents, metadatas)


async def delete_where(ws_id: str, where: dict):
    def _d():
        try:
            collection(ws_id).delete(where=where)
        except Exception as e:
            log.debug(f"chroma delete skipped: {e}")
    await asyncio.to_thread(_d)


def _query_sync(ws_id: str, embedding, kb_ids: list[str], k: int, extra_where: dict | None):
    where: dict = {"kb_id": {"$in": kb_ids}} if len(kb_ids) > 1 else {"kb_id": kb_ids[0]}
    if extra_where:
        where = {"$and": [where, extra_where]}
    col = collection(ws_id)
    if col.count() == 0:
        return []
    r = col.query(query_embeddings=[embedding], n_results=k, where=where, include=["documents", "metadatas", "distances"])
    out = []
    for i, cid in enumerate(r["ids"][0]):
        out.append({"id": cid, "text": r["documents"][0][i], "meta": r["metadatas"][0][i], "similarity": 1 - r["distances"][0][i]})
    return out


async def dense_query(ws_id: str, embedding, kb_ids: list[str], k: int = 12, extra_where: dict | None = None):
    if not kb_ids:
        return []
    return await asyncio.to_thread(_query_sync, ws_id, embedding, kb_ids, k, extra_where)


# ── BM25 ─────────────────────────────────────────────────────────────────────
_TOKEN = re.compile(r"\w+", re.UNICODE)


def _get_sync(ws_id: str, ids: list[str]) -> list[dict]:
    res = collection(ws_id).get(ids=ids, include=["documents", "metadatas"])
    return [{"id": i, "text": d, "meta": m or {}} for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]


async def get_docs(ws_id: str, ids: list[str]) -> list[dict]:
    """Chunk text + metadata straight from the local vector store (no database round-trip)."""
    if not ids:
        return []
    return await asyncio.to_thread(_get_sync, ws_id, ids)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "") if len(t) > 1]


def _bm25_dir(kb_id: str) -> Path:
    return settings.data_path / "bm25" / kb_id


def _build_bm25_sync(kb_id: str, ids: list[str], texts: list[str]):
    import bm25s

    d = _bm25_dir(kb_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    _bm25_cache.pop(kb_id, None)
    if not ids:
        return
    retriever = bm25s.BM25()
    retriever.index([tokenize(t) for t in texts], show_progress=False)
    d.mkdir(parents=True, exist_ok=True)
    retriever.save(str(d))
    (d / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    _bm25_cache[kb_id] = (retriever, ids)


async def build_bm25(kb_id: str, ids: list[str], texts: list[str]):
    await asyncio.to_thread(_build_bm25_sync, kb_id, ids, texts)


def _load_bm25(kb_id: str):
    if kb_id in _bm25_cache:
        return _bm25_cache[kb_id]
    d = _bm25_dir(kb_id)
    if not (d / "ids.json").exists():
        return None
    import bm25s

    retriever = bm25s.BM25.load(str(d))
    ids = json.loads((d / "ids.json").read_text(encoding="utf-8"))
    _bm25_cache[kb_id] = (retriever, ids)
    return _bm25_cache[kb_id]


def _bm25_query_sync(kb_ids: list[str], query: str, k: int):
    q = tokenize(query)
    if not q:
        return []
    out = []
    for kb in kb_ids:
        loaded = _load_bm25(kb)
        if not loaded:
            continue
        retriever, ids = loaded
        vocab = getattr(retriever, "vocab_dict", None) or {}
        q_known = [t for t in q if not vocab or t in vocab]
        if not q_known:
            continue
        try:
            docs, scores = retriever.retrieve([q_known], k=min(k, len(ids)), show_progress=False)
        except Exception as e:
            log.debug(f"bm25 query failed for {kb}: {e}")
            continue
        for idx, score in zip(docs[0], scores[0]):
            if score > 0:
                out.append({"id": ids[int(idx)], "bm25": float(score), "kb_id": kb})
    out.sort(key=lambda x: -x["bm25"])
    return out[:k]


async def bm25_query(kb_ids: list[str], query: str, k: int = 12):
    return await asyncio.to_thread(_bm25_query_sync, kb_ids, query, k)
