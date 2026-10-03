"""Agents: CRUD, templates, publish/versions, channels, golden answers, review queue."""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..brain.agent_config import deep_merge, normalize
from ..brain.respond import index_golden
from ..brain.templates import template_config
from ..db import get_db
from ..models import (Agent, AgentKnowledge, AgentVersion, Channel, Conversation, GoldenAnswer, KnowledgeBase, Message, ReviewItem)
from ..security.auth import AuthContext, require_auth
from .common import audit, get_scoped, to_dict

async def _invalidate_voice_cache(request: Request):
    """Any write under /agents/{id} drops that agent's cached voice setup once the handler has run."""
    yield
    if request.method != "GET":
        from ..voice.session import invalidate_agent

        invalidate_agent(request.path_params.get("agent_id"))


router = APIRouter(prefix="/agents", dependencies=[Depends(_invalidate_voice_cache)])
CHANNEL_TYPES = {"web", "widget", "voice", "whatsapp", "telegram", "phone", "email", "instagram", "messenger"}


async def _agent_out(db: AsyncSession, a: Agent) -> dict:
    d = to_dict(a)
    d["config"] = normalize(a.config)
    d["kb_ids"] = (await db.execute(select(AgentKnowledge.kb_id).where(AgentKnowledge.agent_id == a.id))).scalars().all()
    chans = (await db.execute(select(Channel).where(Channel.agent_id == a.id))).scalars().all()
    d["channels"] = [to_dict(c, {"enc_secret"}) for c in chans]
    d["has_unpublished_changes"] = a.config != a.published_config
    return d


@router.get("")
async def list_agents(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    agents = (await db.execute(select(Agent).where(Agent.workspace_id == auth.ws).order_by(Agent.created_at.desc()))).scalars().all()
    stats = dict((await db.execute(select(Conversation.agent_id, func.count()).where(Conversation.workspace_id == auth.ws).group_by(Conversation.agent_id))).all())
    out = []
    for a in agents:
        d = await _agent_out(db, a)
        d["conversations"] = stats.get(a.id, 0)
        out.append(d)
    return {"items": out}


@router.post("")
async def create_agent(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    template_id = body.get("template_id") or "blank"
    cfg = deep_merge(template_config(template_id), body.get("config") or {})
    a = Agent(workspace_id=auth.ws, name=(body.get("name") or cfg.get("persona", {}).get("name") or "New agent")[:120],
              description=body.get("description", ""), template_id=template_id, config=cfg, status="draft")
    db.add(a)
    await db.flush()
    kb_ids = body.get("kb_ids")
    if kb_ids is None:
        default_kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.workspace_id == auth.ws).order_by(KnowledgeBase.created_at))).scalars().first()
        kb_ids = [default_kb.id] if default_kb else []
    for kb in kb_ids:
        db.add(AgentKnowledge(agent_id=a.id, kb_id=kb, workspace_id=auth.ws))
    for ch in ("web", "widget", "voice"):
        db.add(Channel(workspace_id=auth.ws, agent_id=a.id, type=ch, name=ch.title(), enabled=True))
    await audit(db, auth, "agent.create", a.id, {"template": template_id})
    await db.commit()
    return await _agent_out(db, a)


@router.get("/{agent_id}")
async def get_agent(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    return await _agent_out(db, await get_scoped(db, Agent, agent_id, auth))


@router.patch("/{agent_id}")
async def update_agent(agent_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    a = await get_scoped(db, Agent, agent_id, auth)
    if "name" in body:
        a.name = body["name"][:120]
    if "description" in body:
        a.description = body["description"]
    if "status" in body and body["status"] in {"draft", "live", "paused"}:
        a.status = body["status"]
    if "config" in body:
        a.config = deep_merge(a.config or {}, body["config"])
    if "kb_ids" in body:
        await db.execute(delete(AgentKnowledge).where(AgentKnowledge.agent_id == a.id))
        for kb in body["kb_ids"]:
            db.add(AgentKnowledge(agent_id=a.id, kb_id=kb, workspace_id=auth.ws))
    await db.commit()
    return await _agent_out(db, a)


@router.post("/{agent_id}/publish")
async def publish(agent_id: str, body: dict | None = None, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    a = await get_scoped(db, Agent, agent_id, auth)
    a.published_version += 1
    a.published_config = copy.deepcopy(a.config)
    if a.status == "draft":
        a.status = "live"
    db.add(AgentVersion(workspace_id=auth.ws, agent_id=a.id, version=a.published_version, config=a.published_config,
                        notes=(body or {}).get("notes", ""), created_by=auth.email or auth.user_id))
    await audit(db, auth, "agent.publish", a.id, {"version": a.published_version})
    await db.commit()
    return await _agent_out(db, a)


@router.get("/{agent_id}/versions")
async def versions(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    await get_scoped(db, Agent, agent_id, auth)
    rows = (await db.execute(select(AgentVersion).where(AgentVersion.agent_id == agent_id).order_by(AgentVersion.version.desc()))).scalars().all()
    return {"items": [to_dict(v) for v in rows]}


@router.post("/{agent_id}/versions/{version}/restore")
async def restore(agent_id: str, version: int, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    a = await get_scoped(db, Agent, agent_id, auth)
    v = (await db.execute(select(AgentVersion).where(AgentVersion.agent_id == agent_id, AgentVersion.version == version))).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Version not found")
    a.config = copy.deepcopy(v.config)
    await db.commit()
    return await _agent_out(db, a)


@router.post("/{agent_id}/duplicate")
async def duplicate(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    a = await get_scoped(db, Agent, agent_id, auth)
    b = Agent(workspace_id=auth.ws, name=f"{a.name} (copy)", description=a.description, template_id=a.template_id, config=copy.deepcopy(a.config))
    db.add(b)
    await db.flush()
    for kb in (await db.execute(select(AgentKnowledge.kb_id).where(AgentKnowledge.agent_id == a.id))).scalars():
        db.add(AgentKnowledge(agent_id=b.id, kb_id=kb, workspace_id=auth.ws))
    for ch in ("web", "widget", "voice"):
        db.add(Channel(workspace_id=auth.ws, agent_id=b.id, type=ch, name=ch.title()))
    await db.commit()
    return await _agent_out(db, b)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    a = await get_scoped(db, Agent, agent_id, auth)
    await db.delete(a)
    await audit(db, auth, "agent.delete", agent_id)
    await db.commit()
    return {"ok": True}


@router.get("/{agent_id}/stats")
async def agent_stats(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    await get_scoped(db, Agent, agent_id, auth)
    from .analytics import agent_metrics

    return await agent_metrics(db, auth.ws, agent_id)


# ── Channels ─────────────────────────────────────────────────────────────────
@router.post("/{agent_id}/channels")
async def upsert_channel(agent_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Enable/configure a channel. Secrets (tokens) are validated and stored encrypted."""
    auth.require("builder")
    await get_scoped(db, Agent, agent_id, auth)
    typ = body.get("type")
    if typ not in CHANNEL_TYPES:
        raise HTTPException(422, "Unknown channel type")
    ch = None
    if body.get("id"):
        ch = await get_scoped(db, Channel, body["id"], auth)
    elif typ in {"web", "widget", "voice", "email"}:
        ch = (await db.execute(select(Channel).where(Channel.agent_id == agent_id, Channel.type == typ))).scalars().first()
    if not ch:
        ch = Channel(workspace_id=auth.ws, agent_id=agent_id, type=typ, name=body.get("name") or typ.title())
        db.add(ch)
        await db.flush()
    if "enabled" in body:
        ch.enabled = bool(body["enabled"])
    if "config" in body:
        ch.config = {**(ch.config or {}), **body["config"]}
    if body.get("name"):
        ch.name = body["name"]
    secret = body.get("secret") or {}
    ws = await db.merge(auth.workspace)
    ch.error, ch.status = None, "active"
    if typ == "telegram" and (secret.get("bot_token") or ch.enabled):
        from ..channels.common import channel_secret, set_channel_secret
        from ..channels.telegram import get_me, start_poller, stop_poller

        token = secret.get("bot_token") or channel_secret(ws, ch).get("bot_token")
        if not token:
            raise HTTPException(422, "Telegram needs a bot token from @BotFather")
        try:
            me = await get_me(token)
            ch.config = {**ch.config, "bot_username": me.get("username"), "bot_name": me.get("first_name")}
            set_channel_secret(ws, ch, {"bot_token": token})
        except Exception as e:
            raise HTTPException(422, f"Telegram rejected the token: {e}") from e
        await db.commit()
        if ch.enabled:
            start_poller(ch.id)
        else:
            stop_poller(ch.id)
    elif typ == "whatsapp" and secret:
        from ..channels.common import set_channel_secret

        if not (ch.config or {}).get("phone_number_id"):
            raise HTTPException(422, "WhatsApp needs phone_number_id")
        import httpx

        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://graph.facebook.com/v22.0/{ch.config['phone_number_id']}", headers={"Authorization": f"Bearer {secret.get('access_token', '')}"})
        if r.status_code != 200:
            ch.status, ch.error = "error", f"Meta rejected the token ({r.status_code})"
        else:
            ch.config = {**ch.config, "display_phone": r.json().get("display_phone_number")}
        set_channel_secret(ws, ch, {"access_token": secret.get("access_token", "")})
    elif typ == "phone" and secret:
        from ..channels.common import set_channel_secret

        set_channel_secret(ws, ch, secret)
    elif typ in {"instagram", "messenger"} and secret:
        from ..channels.common import set_channel_secret

        key = "ig_user_id" if typ == "instagram" else "page_id"
        if not (ch.config or {}).get(key):
            raise HTTPException(422, f"{typ.title()} needs {key}")
        import httpx

        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"https://graph.facebook.com/v22.0/{ch.config[key]}", params={"access_token": secret.get("page_token", ""), "fields": "name,username"})
        if r.status_code != 200:
            ch.status, ch.error = "error", f"Meta rejected the page token ({r.status_code})"
        else:
            ch.config = {**ch.config, "account_name": r.json().get("name") or r.json().get("username")}
        set_channel_secret(ws, ch, {"page_token": secret.get("page_token", "")})
    await db.commit()
    return to_dict(ch, {"enc_secret"})


@router.delete("/{agent_id}/channels/{channel_id}")
async def delete_channel(agent_id: str, channel_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    ch = await get_scoped(db, Channel, channel_id, auth)
    if ch.type == "telegram":
        from ..channels.telegram import stop_poller

        stop_poller(ch.id)
    await db.delete(ch)
    await db.commit()
    return {"ok": True}


# ── Golden answers ───────────────────────────────────────────────────────────
@router.get("/{agent_id}/answers")
async def list_answers(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(GoldenAnswer).where(GoldenAnswer.workspace_id == auth.ws, GoldenAnswer.agent_id == agent_id)
                             .order_by(GoldenAnswer.created_at.desc()))).scalars().all()
    return {"items": [to_dict(r) for r in rows]}


@router.post("/{agent_id}/answers")
async def add_answer(agent_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    await get_scoped(db, Agent, agent_id, auth)
    items = body.get("items") or [body]
    out = []
    for it in items:
        if not (it.get("question") and it.get("answer")):
            continue
        ga = GoldenAnswer(workspace_id=auth.ws, agent_id=agent_id, question=it["question"][:1000], answer=it["answer"][:4000],
                          source=it.get("source", "manual"))
        db.add(ga)
        await db.flush()
        await index_golden(db, ga)
        out.append(to_dict(ga))
    await db.commit()
    return {"items": out}


@router.delete("/{agent_id}/answers/{answer_id}")
async def del_answer(agent_id: str, answer_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    ga = await get_scoped(db, GoldenAnswer, answer_id, auth)
    ga.status = "deleted"
    await index_golden(db, ga)
    await db.delete(ga)
    await db.commit()
    return {"ok": True}


# ── Review queue (improve loop) ──────────────────────────────────────────────
@router.get("/{agent_id}/review")
async def review_items(agent_id: str, status: str = "pending", auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ReviewItem).where(ReviewItem.workspace_id == auth.ws, ReviewItem.agent_id == agent_id,
                                                      ReviewItem.status == status).order_by(ReviewItem.created_at.desc()))).scalars().all()
    return {"items": [to_dict(r) for r in rows]}


@router.post("/{agent_id}/review/run")
async def run_improve(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..worker.queue import enqueue

    job = await enqueue("improve.workspace", {"workspace_id": auth.ws}, workspace_id=auth.ws, max_attempts=1)
    return {"job_id": job}


@router.post("/{agent_id}/review/{item_id}")
async def decide(agent_id: str, item_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("builder")
    item = await get_scoped(db, ReviewItem, item_id, auth)
    decision = body.get("decision")
    if decision == "approve":
        answer = body.get("answer") or item.proposed_answer
        if not answer:
            raise HTTPException(422, "An answer is required to approve")
        ga = GoldenAnswer(workspace_id=auth.ws, agent_id=agent_id, question=item.question, answer=answer, source="improve_loop")
        db.add(ga)
        await db.flush()
        await index_golden(db, ga)
        item.status = "approved"
    elif decision == "reject":
        item.status = "rejected"
    else:
        raise HTTPException(422, "decision must be approve or reject")
    await db.commit()
    return to_dict(item)


@router.post("/messages/{message_id}/feedback")
async def feedback(message_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    m = await get_scoped(db, Message, message_id, auth)
    m.feedback = int(body.get("value", -1))
    if body.get("flag"):
        m.flagged, m.flag_reason = True, body.get("reason", "flagged_by_team")
    await db.commit()
    return {"ok": True}
