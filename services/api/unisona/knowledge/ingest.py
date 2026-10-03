"""Ingestion pipeline (runs in the worker): extract → chunk → embed → index."""
from __future__ import annotations

import base64

from sqlalchemy import delete, select

from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import Chunk, Dataset, KnowledgeSource
from ..realtime import hub
from . import store
from .chunk import chunk_markdown
from .embed import embed
from .extract import Doc, TableDoc, crawl_website, extract_file, extract_url
from .tables import load_table, safe_name

log = get_logger("ingest")
MAX_TABLE_ROW_CHUNKS = 2000


async def _set(source_id: str, **fields):
    async with SessionLocal() as db:
        src = await db.get(KnowledgeSource, source_id)
        if src:
            for k, v in fields.items():
                setattr(src, k, v)
            await db.commit()
            await hub.publish(src.workspace_id, {"type": "knowledge.source", "source": {
                "id": src.id, "kb_id": src.kb_id, "status": src.status, "chunks": src.chunks, "error": src.error,
                "progress": src.meta.get("progress")}})


async def _rebuild_bm25(kb_id: str, ws_id: str):
    async with SessionLocal() as db:
        rows = (await db.execute(select(Chunk.id, Chunk.text).where(Chunk.kb_id == kb_id, Chunk.workspace_id == ws_id))).all()
    await store.build_bm25(kb_id, [r[0] for r in rows], [r[1] for r in rows])


def _table_rows_as_docs(table: TableDoc, title: str) -> list[Doc]:
    docs = []
    for i, row in enumerate(table.rows[:MAX_TABLE_ROW_CHUNKS]):
        line = "; ".join(f"{k}: {v}" for k, v in row.items() if str(v).strip())
        if line:
            docs.append(Doc(title=f"{title} · row {i + 1}", text=line, meta={"row": i + 1}))
    return docs


async def ingest_source(source_id: str, file_b64: str | None = None) -> dict:
    async with SessionLocal() as db:
        src = await db.get(KnowledgeSource, source_id)
        if not src:
            return {"error": "source not found"}
        ws_id, kb_id, typ, uri, title = src.workspace_id, src.kb_id, src.type, src.uri, src.title
        text_body = src.meta.get("text", "")
        filename = src.meta.get("filename", title)
    await _set(source_id, status="processing", error=None)
    log.info(f"Ingesting {typ} source '{title}' ({source_id})")

    try:
        docs: list[Doc] = []
        table: TableDoc | None = None
        if typ == "url":
            docs = await extract_url(uri)
        elif typ == "website":
            async def progress(n, url):
                async with SessionLocal() as db:
                    s = await db.get(KnowledgeSource, source_id)
                    if s:
                        s.meta = {**s.meta, "progress": f"{n} pages"}
                        await db.commit()
                await hub.publish(ws_id, {"type": "knowledge.progress", "source_id": source_id, "pages": n, "url": url})
            docs = await crawl_website(uri, max_pages=int((src.meta or {}).get("max_pages", 25)), on_progress=progress)
        elif typ in ("text", "qa"):
            docs = [Doc(title=title, text=text_body)]
        elif typ in ("file", "table"):
            data = base64.b64decode(file_b64) if file_b64 else None
            if data is None:
                from .files import read_upload

                data = read_upload(ws_id, source_id)
            result = extract_file(data, filename)
            if isinstance(result, TableDoc):
                table = result
                docs = _table_rows_as_docs(table, title)
            else:
                docs = result
        if not docs and not table:
            raise ValueError("No readable text found in this source.")

        # Structured tables → DuckDB
        if table:
            tname = safe_name(filename)
            card = await load_table(kb_id, tname, table.columns, table.rows)
            async with SessionLocal() as db:
                await db.execute(delete(Dataset).where(Dataset.source_id == source_id))
                db.add(Dataset(workspace_id=ws_id, kb_id=kb_id, source_id=source_id, table_name=tname,
                               path=f"tables/{kb_id}.duckdb", schema_card=card, row_count=card["row_count"]))
                await db.commit()

        pieces: list[tuple[str, Doc, int, str]] = []
        for doc in docs:
            for ch in chunk_markdown(doc.text, doc.title or title):
                pieces.append((ch.text, doc, ch.ordinal, ch.heading))
        if not pieces:
            raise ValueError("Source produced no chunks.")

        vectors = await embed([p[0] for p in pieces])
        async with SessionLocal() as db:
            await db.execute(delete(Chunk).where(Chunk.source_id == source_id))
            rows = []
            for i, (text, doc, ordinal, heading) in enumerate(pieces):
                meta = {"title": doc.title or title, "url": doc.url or (uri if typ == "url" else None), "heading": heading, **doc.meta}
                rows.append(Chunk(workspace_id=ws_id, kb_id=kb_id, source_id=source_id, ordinal=i, text=text, meta=meta))
            db.add_all(rows)
            await db.flush()
            ids = [r.id for r in rows]
            metas = [{"kb_id": kb_id, "source_id": source_id, "title": r.meta.get("title") or "", "url": r.meta.get("url") or "",
                      "chunk": r.ordinal} for r in rows]
            await db.commit()
        await store.delete_where(ws_id, {"source_id": source_id})
        await store.upsert(ws_id, ids, vectors, [p[0] for p in pieces], metas)
        await _rebuild_bm25(kb_id, ws_id)
        await _set(source_id, status="ready", chunks=len(pieces), last_ingested_at=utcnow(),
                   meta={**(src.meta or {}), "documents": len(docs), "progress": None,
                         **({"table": safe_name(filename), "rows": len(table.rows)} if table else {})})
        log.info(f"Ingested '{title}': {len(docs)} docs → {len(pieces)} chunks")
        return {"chunks": len(pieces), "documents": len(docs)}
    except Exception as e:
        log.error(f"Ingest failed for {source_id}: {e}")
        await _set(source_id, status="error", error=str(e)[:500])
        raise


async def delete_source_index(ws_id: str, kb_id: str, source_id: str):
    await store.delete_where(ws_id, {"source_id": source_id})
    await _rebuild_bm25(kb_id, ws_id)
