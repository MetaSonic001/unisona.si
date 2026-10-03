"""Knowledge bases, sources, chunks, structured tables and the retrieval test panel."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db, new_id
from ..knowledge.files import save_upload
from ..knowledge.ingest import delete_source_index
from ..knowledge.retrieve import retrieve
from ..models import AgentKnowledge, Chunk, Dataset, KnowledgeBase, KnowledgeSource
from ..security.auth import AuthContext, require_auth
from ..worker.queue import enqueue
from .common import audit, get_scoped, to_dict

async def _invalidate_voice_cache(request: Request):
    yield
    if request.method != "GET":
        from ..voice.session import invalidate_agent

        invalidate_agent()  # knowledge base changes alter agents' table/kb setup


router = APIRouter(prefix="/knowledge", dependencies=[Depends(_invalidate_voice_cache)])
MAX_UPLOAD_MB = 25
TABLE_EXT = (".csv", ".xlsx", ".xls", ".xlsm", ".tsv")
ALLOWED_EXT = (".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".htm", ".json") + TABLE_EXT


@router.get("/bases")
async def list_kbs(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    kbs = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.workspace_id == auth.ws).order_by(KnowledgeBase.created_at))).scalars().all()
    counts = dict((await db.execute(select(KnowledgeSource.kb_id, func.count()).where(KnowledgeSource.workspace_id == auth.ws)
                                    .group_by(KnowledgeSource.kb_id))).all())
    chunks = dict((await db.execute(select(Chunk.kb_id, func.count()).where(Chunk.workspace_id == auth.ws).group_by(Chunk.kb_id))).all())
    agents = {}
    for kb_id, agent_id in (await db.execute(select(AgentKnowledge.kb_id, AgentKnowledge.agent_id).where(AgentKnowledge.workspace_id == auth.ws))).all():
        agents.setdefault(kb_id, []).append(agent_id)
    return {"items": [{**to_dict(k), "sources": counts.get(k.id, 0), "chunks": chunks.get(k.id, 0), "agent_ids": agents.get(k.id, [])} for k in kbs]}


@router.post("/bases")
async def create_kb(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    kb = KnowledgeBase(workspace_id=auth.ws, name=body.get("name") or "Knowledge base", description=body.get("description", ""))
    db.add(kb)
    await db.commit()
    return to_dict(kb)


@router.delete("/bases/{kb_id}")
async def delete_kb(kb_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    kb = await get_scoped(db, KnowledgeBase, kb_id, auth)
    from ..knowledge import store

    await store.delete_where(auth.ws, {"kb_id": kb_id})
    await db.delete(kb)
    await db.commit()
    return {"ok": True}


@router.get("/sources")
async def list_sources(kb_id: str | None = None, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    q = select(KnowledgeSource).where(KnowledgeSource.workspace_id == auth.ws)
    if kb_id:
        q = q.where(KnowledgeSource.kb_id == kb_id)
    rows = (await db.execute(q.order_by(KnowledgeSource.created_at.desc()))).scalars().all()
    return {"items": [to_dict(r) for r in rows]}


async def _default_kb(db: AsyncSession, auth: AuthContext, kb_id: str | None) -> str:
    if kb_id:
        await get_scoped(db, KnowledgeBase, kb_id, auth)
        return kb_id
    kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.workspace_id == auth.ws).order_by(KnowledgeBase.created_at))).scalars().first()
    if not kb:
        kb = KnowledgeBase(workspace_id=auth.ws, name="General knowledge")
        db.add(kb)
        await db.flush()
    return kb.id


@router.post("/sources")
async def add_source(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Add a url | website | text | qa source (JSON). Files use /sources/upload."""
    auth.require("builder")
    typ = body.get("type")
    if typ not in {"url", "website", "text", "qa"}:
        raise HTTPException(422, "type must be url, website, text or qa")
    kb_id = await _default_kb(db, auth, body.get("kb_id"))
    created = []
    if typ in {"url", "website"}:
        urls = body.get("urls") or [body.get("uri") or body.get("url")]
        for u in [u.strip() for u in urls if u and u.strip()]:
            if not u.startswith("http"):
                u = "https://" + u
            src = KnowledgeSource(workspace_id=auth.ws, kb_id=kb_id, type=typ, title=u, uri=u,
                                  meta={"max_pages": int(body.get("max_pages", 25))}, refresh_days=int(body.get("refresh_days", 0)),
                                  when_to_use=body.get("when_to_use", ""))
            db.add(src)
            created.append(src)
    else:
        text = body.get("text") or ""
        if typ == "qa":
            pairs = body.get("pairs") or []
            text = "\n\n".join(f"## {p['question']}\n{p['answer']}" for p in pairs if p.get("question") and p.get("answer"))
        if len(text.strip()) < 5:
            raise HTTPException(422, "Text is empty")
        src = KnowledgeSource(workspace_id=auth.ws, kb_id=kb_id, type=typ, title=body.get("title") or text.strip().split("\n")[0][:80],
                              meta={"text": text}, when_to_use=body.get("when_to_use", ""))
        db.add(src)
        created.append(src)
    await db.flush()
    await audit(db, auth, "knowledge.add", typ, {"count": len(created)})
    await db.commit()
    for s in created:
        await enqueue("knowledge.ingest", {"source_id": s.id}, workspace_id=auth.ws)
    return {"items": [to_dict(s) for s in created]}


@router.post("/sources/upload")
async def upload(files: list[UploadFile] = File(...), kb_id: str | None = Form(None), when_to_use: str = Form(""),
                 auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    kb = await _default_kb(db, auth, kb_id)
    created = []
    for f in files:
        name = f.filename or "upload"
        if not name.lower().endswith(ALLOWED_EXT):
            raise HTTPException(422, f"{name}: unsupported file type")
        data = await f.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"{name} is larger than {MAX_UPLOAD_MB} MB")
        src_id = new_id("src")
        save_upload(auth.ws, src_id, data)
        typ = "table" if name.lower().endswith(TABLE_EXT) else "file"
        src = KnowledgeSource(id=src_id, workspace_id=auth.ws, kb_id=kb, type=typ, title=name, uri=name,
                              meta={"filename": name, "bytes": len(data)}, when_to_use=when_to_use)
        db.add(src)
        created.append(src)
    await db.commit()
    for s in created:
        await enqueue("knowledge.ingest", {"source_id": s.id}, workspace_id=auth.ws)
    return {"items": [to_dict(s) for s in created]}


@router.post("/sources/{source_id}/reindex")
async def reindex(source_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    src = await get_scoped(db, KnowledgeSource, source_id, auth)
    src.status = "pending"
    await db.commit()
    await enqueue("knowledge.ingest", {"source_id": src.id}, workspace_id=auth.ws)
    return to_dict(src)


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    src = await get_scoped(db, KnowledgeSource, source_id, auth)
    for k in ("title", "when_to_use", "refresh_days"):
        if k in body:
            setattr(src, k, body[k])
    await db.commit()
    return to_dict(src)


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    src = await get_scoped(db, KnowledgeSource, source_id, auth)
    kb_id = src.kb_id
    await db.delete(src)
    await db.commit()
    await delete_source_index(auth.ws, kb_id, source_id)
    return {"ok": True}


@router.get("/sources/{source_id}/chunks")
async def chunks(source_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    await get_scoped(db, KnowledgeSource, source_id, auth)
    rows = (await db.execute(select(Chunk).where(Chunk.source_id == source_id).order_by(Chunk.ordinal).limit(500))).scalars().all()
    ds = (await db.execute(select(Dataset).where(Dataset.source_id == source_id))).scalar_one_or_none()
    return {"items": [to_dict(c) for c in rows], "dataset": to_dict(ds) if ds else None}


@router.post("/search")
async def search(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """The glass-box test panel: shows every retrieval stage for a query."""
    kb_ids = body.get("kb_ids")
    if not kb_ids and body.get("agent_id"):
        kb_ids = (await db.execute(select(AgentKnowledge.kb_id).where(AgentKnowledge.agent_id == body["agent_id"]))).scalars().all()
    if not kb_ids:
        kb_ids = (await db.execute(select(KnowledgeBase.id).where(KnowledgeBase.workspace_id == auth.ws))).scalars().all()
    res = await retrieve(db, auth.ws, list(kb_ids), body.get("query", ""), k=int(body.get("k", 6)), mode=body.get("mode", "deep"),
                         policies=body.get("policies"))
    return res.to_dict()
