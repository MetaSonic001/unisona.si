"""Rebuild local search indexes from Postgres after the disk was wiped.

Hosted platforms (Render, Railway, ...) give the API an ephemeral disk: every deploy or restart starts with
an empty `data/` folder. Chunk text lives in Postgres (`app.chunks`), so on startup each knowledge base
whose vectors or keyword index are missing is re-embedded from the database. Spreadsheet sources whose
DuckDB file is gone are re-ingested from the stored upload.
"""
from __future__ import annotations

import asyncio
import time

from sqlalchemy import func, select

from ..db import SessionLocal
from ..log import get_logger
from ..models import Chunk, Dataset
from . import store
from .embed import embed
from .tables import db_path

log = get_logger("heal")


def _vector_count(ws_id: str, kb_id: str) -> int:
    try:
        return len(store.collection(ws_id).get(where={"kb_id": kb_id}, limit=1, include=[])["ids"])
    except Exception:
        return 0


async def _reembed(ws_id: str, kb_id: str) -> int:
    async with SessionLocal() as db:
        rows = (await db.execute(select(Chunk.id, Chunk.text, Chunk.source_id, Chunk.ordinal, Chunk.meta)
                                 .where(Chunk.workspace_id == ws_id, Chunk.kb_id == kb_id).order_by(Chunk.source_id, Chunk.ordinal))).all()
    for i in range(0, len(rows), 128):
        batch = rows[i:i + 128]
        vectors = await embed([r.text for r in batch])
        metas = [{"kb_id": kb_id, "source_id": r.source_id, "title": (r.meta or {}).get("title") or "",
                  "url": (r.meta or {}).get("url") or "", "chunk": r.ordinal} for r in batch]
        await store.upsert(ws_id, [r.id for r in batch], vectors, [r.text for r in batch], metas)
    return len(rows)


async def heal_indexes() -> int:
    t0 = time.perf_counter()
    try:
        async with SessionLocal() as db:
            kbs = (await db.execute(select(Chunk.workspace_id, Chunk.kb_id, func.count()).group_by(Chunk.workspace_id, Chunk.kb_id))).all()
            datasets = (await db.execute(select(Dataset.kb_id, Dataset.source_id, Dataset.workspace_id))).all()
    except Exception as e:
        log.warning(f"Index check skipped (database unavailable): {str(e).splitlines()[0][:200]}")
        return 0
    healed = 0
    for ws_id, kb_id, n in kbs:
        try:
            missing_vectors = await asyncio.to_thread(_vector_count, ws_id, kb_id) == 0
            missing_bm25 = not (store._bm25_dir(kb_id) / "ids.json").exists()
            if not (missing_vectors or missing_bm25):
                continue
            if missing_vectors:
                log.info(f"Re-embedding {n} chunks for knowledge base {kb_id} (local vector index was empty)")
                await _reembed(ws_id, kb_id)
            from .ingest import _rebuild_bm25

            await _rebuild_bm25(kb_id, ws_id)
            healed += 1
        except Exception as e:
            log.warning(f"Could not rebuild indexes for {kb_id}: {e}")
    missing = {kb_id for kb_id, _, _ in datasets if not db_path(kb_id).exists()}
    for kb_id, source_id, ws_id in datasets:
        if kb_id not in missing:
            continue
        from ..worker.queue import enqueue

        log.info(f"Spreadsheet table for {kb_id} is missing on disk: re-ingesting source {source_id}")
        await enqueue("knowledge.ingest", {"source_id": source_id}, workspace_id=ws_id)
    if healed:
        log.info(f"Index self-heal finished in {time.perf_counter() - t0:.1f}s")
    return healed
