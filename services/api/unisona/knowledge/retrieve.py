"""Hybrid retrieval with full diagnostics ("glass box").

dense (Chroma, cosine) ∪ sparse (bm25s) → Reciprocal Rank Fusion → policy multipliers
(restrict ×0.05, require ×2.0, allow ×1.0) → optional cross-encoder rerank (deep mode)
→ top-k. Every stage's numbers are kept on each chunk so the UI can show why a chunk
was or wasn't used.
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..log import get_logger
from ..models import Chunk, KnowledgeSource
from . import store
from .embed import embed

log = get_logger("rag")
RRF_K = 60
POLICY_MULT = {"restrict": 0.05, "require": 2.0, "allow": 1.0}
_ranker = None
_ranker_lock = threading.Lock()


@dataclass
class Retrieved:
    id: str
    text: str
    source_id: str
    title: str
    url: str | None
    kb_id: str
    dense: float | None = None
    dense_rank: int | None = None
    bm25: float | None = None
    bm25_rank: int | None = None
    rrf: float = 0.0
    rerank: float | None = None
    policy: float = 1.0
    policy_rules: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class RetrievalResult:
    query: str
    chunks: list[Retrieved]
    candidates: list[Retrieved]
    confidence: float
    mode: str
    timings_ms: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "query": self.query, "mode": self.mode, "confidence": round(self.confidence, 3),
            "timings_ms": self.timings_ms,
            "chunks": [asdict(c) for c in self.chunks],
            "candidates": [asdict(c) for c in self.candidates[:20]],
        }


def _ranker_sync():
    global _ranker
    with _ranker_lock:
        if _ranker is None:
            from flashrank import Ranker

            _ranker = Ranker(model_name="ms-marco-MultiBERT-L-12", cache_dir=str(settings.data_path / "models"))
    return _ranker


def _rerank_sync(query: str, items: list[Retrieved]) -> list[float]:
    from flashrank import RerankRequest

    ranker = _ranker_sync()
    res = ranker.rerank(RerankRequest(query=query, passages=[{"id": i, "text": c.text[:1200]} for i, c in enumerate(items)]))
    scores = [0.0] * len(items)
    for r in res:
        scores[int(r["id"])] = float(r["score"])
    return scores


def _apply_policies(c: Retrieved, policies: list[dict]) -> None:
    text = c.text.lower()
    for p in policies or []:
        target = (p.get("target") or "").lower().strip()
        if not target:
            continue
        match = p.get("match", "topic")
        hit = (match == "topic" and target in text) or (match == "source" and (target in c.title.lower() or target in (c.url or "").lower()))
        if hit:
            mult = POLICY_MULT.get(p.get("action", "allow"), 1.0)
            c.policy *= mult
            c.policy_rules.append(f"{p.get('action')}:{target}")


async def retrieve(db: AsyncSession | None, ws_id: str, kb_ids: list[str], query: str, *, k: int = 6, mode: str = "fast",
                   policies: list[dict] | None = None, qvec: list[float] | None = None) -> RetrievalResult:
    t0 = time.perf_counter()
    timings: dict[str, int] = {}
    if not kb_ids or not query.strip():
        return RetrievalResult(query, [], [], 0.0, mode, timings)

    if qvec is None:
        [qvec] = await embed([query])
    timings["embed"] = int((time.perf_counter() - t0) * 1000)
    t1 = time.perf_counter()
    dense, sparse = await asyncio.gather(
        store.dense_query(ws_id, qvec, kb_ids, k=16),
        store.bm25_query(kb_ids, query, k=16),
    )
    timings["search"] = int((time.perf_counter() - t1) * 1000)

    by_id: dict[str, Retrieved] = {}
    for rank, d in enumerate(dense):
        m = d["meta"] or {}
        by_id[d["id"]] = Retrieved(id=d["id"], text=d["text"], source_id=m.get("source_id", ""), title=m.get("title", ""),
                                   url=m.get("url") or None, kb_id=m.get("kb_id", ""), dense=round(d["similarity"], 4), dense_rank=rank + 1)
    missing = [s["id"] for s in sparse if s["id"] not in by_id]
    if missing:  # keyword-only hits: read their text from the local vector store, fall back to Postgres
        for d in await store.get_docs(ws_id, missing):
            m = d["meta"]
            by_id[d["id"]] = Retrieved(id=d["id"], text=d["text"], source_id=m.get("source_id", ""), title=m.get("title", ""),
                                       url=m.get("url") or None, kb_id=m.get("kb_id", ""))
        missing = [i for i in missing if i not in by_id]
    if missing and db is not None:
        rows = (await db.execute(select(Chunk).where(Chunk.id.in_(missing), Chunk.workspace_id == ws_id))).scalars().all()
        for row in rows:
            by_id[row.id] = Retrieved(id=row.id, text=row.text, source_id=row.source_id, title=row.meta.get("title", ""),
                                      url=row.meta.get("url"), kb_id=row.kb_id)
    for rank, s in enumerate(sparse):
        if s["id"] in by_id:
            by_id[s["id"]].bm25 = round(s["bm25"], 3)
            by_id[s["id"]].bm25_rank = rank + 1

    for c in by_id.values():
        c.rrf = (1 / (RRF_K + c.dense_rank) if c.dense_rank else 0) + (1 / (RRF_K + c.bm25_rank) if c.bm25_rank else 0)
        _apply_policies(c, policies or [])
        c.score = c.rrf * c.policy

    candidates = sorted(by_id.values(), key=lambda c: -c.score)
    top = candidates[: max(k * 2, 10)]
    if mode == "deep" and len(top) > 1:
        t2 = time.perf_counter()
        try:
            scores = await asyncio.to_thread(_rerank_sync, query, top)
            for c, s in zip(top, scores):
                c.rerank = round(s, 4)
                c.score = (0.5 * s + 0.5 * min(c.rrf * 30, 1.0)) * c.policy
            top.sort(key=lambda c: -c.score)
        except Exception as e:
            log.warning(f"Rerank skipped: {e}")
        timings["rerank"] = int((time.perf_counter() - t2) * 1000)

    chosen = [c for c in top if c.policy >= 0.5][:k]
    confidence = max((c.dense or 0) for c in chosen) if chosen else 0.0
    timings["total"] = int((time.perf_counter() - t0) * 1000)
    return RetrievalResult(query, chosen, candidates, confidence, mode, timings)


async def source_titles(db: AsyncSession, ws_id: str, ids: list[str]) -> dict[str, KnowledgeSource]:
    if not ids:
        return {}
    rows = (await db.execute(select(KnowledgeSource).where(KnowledgeSource.id.in_(ids), KnowledgeSource.workspace_id == ws_id))).scalars().all()
    return {r.id: r for r in rows}
