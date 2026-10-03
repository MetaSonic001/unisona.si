"""Unified inbox, human takeover, traces, calls and live monitor controls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..brain import handoff as handoff_mod
from ..brain.respond import store_message
from ..db import get_db, utcnow
from ..models import Agent, Call, Contact, ContactFact, ContactIdentity, Conversation, Handoff, Message, Trace
from ..security.auth import AuthContext, require_auth
from .common import get_scoped, to_dict

router = APIRouter()


@router.get("/conversations")
async def list_conversations(status: str | None = None, channel: str | None = None, agent_id: str | None = None,
                             contact_id: str | None = None, q: str | None = None, mine: bool = False, limit: int = 100,
                             auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    stmt = select(Conversation, Contact).outerjoin(Contact, Contact.id == Conversation.contact_id).where(Conversation.workspace_id == auth.ws)
    if status == "open":
        stmt = stmt.where(Conversation.status != "closed")
    elif status:
        stmt = stmt.where(Conversation.status == status)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    else:
        stmt = stmt.where(Conversation.channel != "playground")
    if agent_id:
        stmt = stmt.where(Conversation.agent_id == agent_id)
    if contact_id:
        stmt = stmt.where(Conversation.contact_id == contact_id)
    if mine:
        stmt = stmt.where(Conversation.assignee_id == auth.user_id)
    if q:
        stmt = stmt.where(or_(Conversation.subject.ilike(f"%{q}%"), Contact.name.ilike(f"%{q}%"), Contact.phone.ilike(f"%{q}%")))
    rows = (await db.execute(stmt.order_by(Conversation.last_message_at.desc()).limit(min(limit, 300)))).all()
    ids = [c.id for c, _ in rows]
    last: dict[str, Message] = {}
    if ids:
        sub = select(Message.conversation_id, func.max(Message.created_at).label("mx")).where(Message.conversation_id.in_(ids)).group_by(Message.conversation_id).subquery()
        for m in (await db.execute(select(Message).join(sub, (Message.conversation_id == sub.c.conversation_id) & (Message.created_at == sub.c.mx)))).scalars():
            last[m.conversation_id] = m
    agents = {a.id: a.name for a in (await db.execute(select(Agent).where(Agent.workspace_id == auth.ws))).scalars()}
    items = []
    for c, ct in rows:
        lm = last.get(c.id)
        items.append({**to_dict(c), "agent_name": agents.get(c.agent_id), "contact": {"id": ct.id, "name": ct.name, "phone": ct.phone, "email": ct.email} if ct else None,
                      "last_message": {"role": lm.role, "content": lm.content[:160], "created_at": lm.created_at.isoformat()} if lm else None})
    counts = dict((await db.execute(select(Conversation.status, func.count()).where(Conversation.workspace_id == auth.ws, Conversation.channel != "playground")
                                    .group_by(Conversation.status))).all())
    return {"items": items, "counts": counts}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Conversation, conv_id, auth)
    msgs = (await db.execute(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at))).scalars().all()
    contact = await db.get(Contact, c.contact_id) if c.contact_id else None
    facts, identities = [], []
    if contact:
        facts = [to_dict(f) for f in (await db.execute(select(ContactFact).where(ContactFact.contact_id == contact.id, ContactFact.valid_to.is_(None)))).scalars()]
        identities = [to_dict(i) for i in (await db.execute(select(ContactIdentity).where(ContactIdentity.contact_id == contact.id))).scalars()]
    hos = [to_dict(h) for h in (await db.execute(select(Handoff).where(Handoff.conversation_id == c.id).order_by(Handoff.requested_at.desc()))).scalars()]
    call = (await db.execute(select(Call).where(Call.conversation_id == c.id))).scalars().first()
    other = []
    if contact:
        other = [{"id": o.id, "channel": o.channel, "summary": o.summary, "last_message_at": o.last_message_at.isoformat(), "status": o.status}
                 for o in (await db.execute(select(Conversation).where(Conversation.contact_id == contact.id, Conversation.id != c.id)
                                            .order_by(Conversation.last_message_at.desc()).limit(10))).scalars()]
    agent = await db.get(Agent, c.agent_id)
    return {"conversation": to_dict(c), "agent": {"id": agent.id, "name": agent.name} if agent else None,
            "messages": [to_dict(m) for m in msgs], "contact": to_dict(contact) if contact else None, "facts": facts,
            "identities": identities, "handoffs": hos, "call": to_dict(call) if call else None, "other_conversations": other}


async def deliver_human_message(db: AsyncSession, auth: AuthContext, c: Conversation, text: str) -> dict:
    """Route a human agent's reply to the customer's channel."""
    from ..channels.outbound import send_to_contact
    from ..realtime import hub
    from ..voice.session import ACTIVE

    delivered, detail = True, "delivered"
    if c.channel in {"whatsapp", "telegram"} and c.contact_id:
        contact = await db.get(Contact, c.contact_id)
        agent = await db.get(Agent, c.agent_id)
        delivered, detail = await send_to_contact(db, auth.workspace, agent, contact, c.channel, text)
    elif c.channel in {"voice", "phone"}:
        sess = next((s for s in ACTIVE.values() if s.conversation_id == c.id), None)
        if sess:
            await sess.say(text)
        else:
            delivered, detail = False, "call has ended"
    msg = await store_message(db, c, "human", text, author_id=auth.user_id, ir={"author": auth.name or auth.email})
    await db.commit()
    await hub.publish(f"conv:{c.id}", {"type": "human.message", "text": text, "author": auth.name or "Team"})
    return {"message": to_dict(msg), "delivered": delivered, "detail": detail}


@router.post("/conversations/{conv_id}/messages")
async def human_reply(conv_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("agent")
    c = await get_scoped(db, Conversation, conv_id, auth)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Message is empty")
    if c.status != "human":  # replying implies taking over
        await handoff_mod.accept(db, c, auth.user_id)
    return await deliver_human_message(db, auth, c, text)


@router.post("/conversations/{conv_id}/suggest")
async def suggest_reply(conv_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """AI copilot for the human agent: drafts a reply grounded in the knowledge base."""
    from ..brain.respond import agent_cfg, agent_kb_ids
    from ..knowledge.retrieve import retrieve
    from ..providers.llm import get_llm

    c = await get_scoped(db, Conversation, conv_id, auth)
    msgs = (await db.execute(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at.desc()).limit(12))).scalars().all()
    last_user = next((m.content for m in msgs if m.role == "user"), "")
    agent = await db.get(Agent, c.agent_id)
    cfg = agent_cfg(agent, False)
    res = await retrieve(db, auth.ws, await agent_kb_ids(db, agent, cfg), last_user, k=4) if last_user else None
    llm = await get_llm(db, auth.workspace, feature="reply suggestions")
    if not llm.available:
        raise HTTPException(400, "No LLM key configured")
    transcript = "\n".join(f"{m.role}: {m.content}" for m in reversed(msgs))
    kb = "\n\n".join(ch.text[:700] for ch in (res.chunks if res else []))
    r = await llm.chat([{"role": "system", "content": f"Draft a short, helpful reply a human support agent can send on {c.channel}. Use only facts from the knowledge. Reply with the message text only."},
                        {"role": "user", "content": f"Knowledge:\n{kb}\n\nConversation:\n{transcript}"}], max_tokens=300)
    return {"suggestion": r.content}


@router.post("/conversations/{conv_id}/accept")
async def accept(conv_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("agent")
    c = await get_scoped(db, Conversation, conv_id, auth)
    await handoff_mod.accept(db, c, auth.user_id)
    from ..voice.session import ACTIVE

    for s in ACTIVE.values():
        if s.conversation_id == c.id:
            s.human_mode = True
    return to_dict(c)


@router.post("/conversations/{conv_id}/release")
async def release(conv_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Conversation, conv_id, auth)
    await handoff_mod.release_to_ai(db, c)
    from ..voice.session import ACTIVE

    for s in ACTIVE.values():
        if s.conversation_id == c.id:
            s.human_mode = False
    return to_dict(c)


@router.post("/conversations/{conv_id}/close")
async def close(conv_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Conversation, conv_id, auth)
    c.status, c.ended_at = "closed", utcnow()
    for ho in (await db.execute(select(Handoff).where(Handoff.conversation_id == c.id, Handoff.status.in_(["pending", "accepted"])))).scalars():
        ho.status, ho.resolved_at = "resolved", utcnow()
    await db.commit()
    from ..worker.queue import enqueue

    await enqueue("conversation.analyze", {"conversation_id": c.id}, workspace_id=auth.ws)
    return to_dict(c)


@router.post("/conversations/{conv_id}/assign")
async def assign(conv_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Conversation, conv_id, auth)
    c.assignee_id = body.get("user_id")
    await db.commit()
    return to_dict(c)


@router.post("/conversations/{conv_id}/analyze")
async def analyze(conv_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    await get_scoped(db, Conversation, conv_id, auth)
    from ..brain.analysis import analyze_conversation

    return await analyze_conversation(db, conv_id)


@router.post("/messages/{message_id}/feedback")
async def feedback(message_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    m = await get_scoped(db, Message, message_id, auth)
    m.feedback = int(body.get("value", -1))
    if body.get("flag") or m.feedback == -1:
        m.flagged, m.flag_reason = True, body.get("reason", "flagged_by_team")
    await db.commit()
    return {"ok": True}


@router.get("/traces/{trace_id}")
async def trace(trace_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    return to_dict(await get_scoped(db, Trace, trace_id, auth))


# ── Calls & live monitor ─────────────────────────────────────────────────────
@router.get("/calls")
async def calls(limit: int = 100, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Call, Conversation, Contact).outerjoin(Conversation, Conversation.id == Call.conversation_id)
                             .outerjoin(Contact, Contact.id == Conversation.contact_id)
                             .where(Call.workspace_id == auth.ws).order_by(Call.started_at.desc()).limit(limit))).all()
    agents = {a.id: a.name for a in (await db.execute(select(Agent).where(Agent.workspace_id == auth.ws))).scalars()}
    return {"items": [{**to_dict(c), "agent_name": agents.get(c.agent_id), "summary": cv.summary if cv else "", "outcome": cv.outcome if cv else None,
                       "sentiment": cv.sentiment if cv else None, "contact": {"id": ct.id, "name": ct.name, "phone": ct.phone} if ct else None}
                      for c, cv, ct in rows]}


@router.get("/calls/live")
async def live(auth: AuthContext = Depends(require_auth)):
    from ..voice.session import ACTIVE

    return {"items": [s.status() | {"meta": s.meta} for s in ACTIVE.values() if s.ws_id == auth.ws]}


@router.post("/calls/{call_id}/{action}")
async def call_action(call_id: str, action: str, body: dict | None = None, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..voice.session import ACTIVE

    sess = ACTIVE.get(call_id)
    if not sess or sess.ws_id != auth.ws:
        raise HTTPException(404, "Call is not live")
    text = (body or {}).get("text", "")
    if action == "whisper":
        await sess.whisper(text)
    elif action == "takeover":
        sess.human_mode = True
        c = await db.get(Conversation, sess.conversation_id)
        await handoff_mod.accept(db, c, auth.user_id)
        await sess.say(text or "Hi, I'm a member of the team and I'm joining the call now.")
    elif action == "release":
        sess.human_mode = False
        c = await db.get(Conversation, sess.conversation_id)
        await handoff_mod.release_to_ai(db, c)
    elif action == "say":
        await sess.say(text)
    elif action == "end":
        await sess.end(text or None)
    else:
        raise HTTPException(422, "Unknown action")
    return {"ok": True, "call": sess.status()}


@router.get("/calls/{call_id}/recording")
async def recording(call_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Call, call_id, auth)
    if not c.recording_path:
        raise HTTPException(404, "No recording")
    return FileResponse(c.recording_path, media_type="audio/wav")
