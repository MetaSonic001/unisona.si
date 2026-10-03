"""Onboarding, billing, inbound webhooks, custom tools, realtime socket and dev-mode tools."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import feature_matrix, settings
from ..db import SessionLocal, get_db
from ..log import get_logger
from ..models import (Agent, AgentKnowledge, Channel, GoldenAnswer, Job, KnowledgeBase, KnowledgeSource, Subscription, Tool, Workspace)
from ..realtime import hub
from ..security.auth import AuthContext, require_auth, ws_auth
from .common import audit, get_scoped, to_dict

log = get_logger("api")
router = APIRouter()


# ── Onboarding ───────────────────────────────────────────────────────────────
@router.post("/onboarding/analyze")
async def onboarding_analyze(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..providers.llm import get_llm
    from ..services.onboarding import analyze_site

    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(422, "Enter your website URL")
    llm = await get_llm(db, auth.workspace, feature="onboarding website analysis")
    if not llm.available:
        raise HTTPException(400, "Add an AI provider key (e.g. a free Groq key) to analyse your website.")
    try:
        return await asyncio.wait_for(analyze_site(llm, url, max_pages=int(body.get("max_pages", 8))), timeout=150)
    except asyncio.TimeoutError as e:
        raise HTTPException(504, "The website took too long to read. Try again or skip this step.") from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/onboarding/apply")
async def onboarding_apply(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Create the agent from the wizard: profile + template + knowledge + voice + channels."""
    from ..brain.agent_config import deep_merge
    from ..brain.respond import index_golden
    from ..brain.templates import template_config
    from ..worker.queue import enqueue

    auth.require("builder")
    profile = body.get("profile") or {}
    biz = profile.get("business") or body.get("business") or {}
    ag = profile.get("agent") or {}
    template_id = body.get("template_id") or (profile.get("templates") or ["customer-support"])[0]
    cfg = deep_merge(template_config(template_id), {
        "persona": {k: v for k, v in {"name": ag.get("name"), "role": ag.get("role"), "greeting": ag.get("greeting"),
                                       "tone": body.get("tone", ag.get("tone", 60)), "verbosity": body.get("verbosity", 35),
                                       "goals": ag.get("goals")}.items() if v not in (None, "", [])},
        "business": {k: biz.get(k, "") for k in ("name", "description", "website", "hours", "phone", "email", "address")},
        "languages": {"primary": (body.get("languages") or profile.get("languages") or ["en-IN"])[0],
                      "supported": body.get("languages") or profile.get("languages") or ["en-IN", "hi-IN"]},
        "voice": {"voice_id": body.get("voice_id") or "edge:en-IN-NeerjaExpressiveNeural",
                  "per_language": body.get("voice_per_language") or {"hi-IN": "edge:hi-IN-SwaraNeural"}},
    })
    kb = KnowledgeBase(workspace_id=auth.ws, name=f"{biz.get('name') or 'Business'} knowledge")
    db.add(kb)
    await db.flush()
    agent = Agent(workspace_id=auth.ws, name=f"{cfg['persona'].get('name', 'Assistant')} · {biz.get('name') or 'Agent'}"[:120],
                  template_id=template_id, config=cfg, published_config=cfg, published_version=1, status="live")
    db.add(agent)
    await db.flush()
    db.add(AgentKnowledge(agent_id=agent.id, kb_id=kb.id, workspace_id=auth.ws))
    for t in ("web", "widget", "voice"):
        db.add(Channel(workspace_id=auth.ws, agent_id=agent.id, type=t, name=t.title(), enabled=t in (body.get("channels") or ["web", "widget", "voice"])))
    sources = []
    site = biz.get("website") or body.get("url")
    if site:
        sources.append(KnowledgeSource(workspace_id=auth.ws, kb_id=kb.id, type="website", title=site, uri=site, meta={"max_pages": 20}, refresh_days=7))
    faqs = [f for f in (profile.get("faqs") or []) if f.get("question") and f.get("answer")]
    goldens = []
    for f in faqs:
        g = GoldenAnswer(workspace_id=auth.ws, agent_id=agent.id, question=f["question"], answer=f["answer"], source="onboarding")
        db.add(g)
        goldens.append(g)
    db.add_all(sources)
    ws = await db.merge(auth.workspace)
    ws.onboarding = {**ws.onboarding, "completed": True, "agent_id": agent.id}
    await audit(db, auth, "onboarding.complete", agent.id)
    await db.commit()
    for g in goldens:
        await index_golden(db, g)
    for s in sources:
        await enqueue("knowledge.ingest", {"source_id": s.id}, workspace_id=auth.ws)
    return {"agent_id": agent.id, "kb_id": kb.id, "public_key": agent.public_key, "faqs": len(goldens), "sources": len(sources)}


# ── Billing ──────────────────────────────────────────────────────────────────
@router.get("/billing/plans")
async def plans():
    from ..services.billing import OVERAGE, PLANS

    return {"plans": PLANS, "overage": OVERAGE, "payments_enabled": bool(settings.dodo_payments_api_key)}


@router.get("/billing/usage")
async def billing_usage(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from datetime import timedelta

    from ..db import utcnow
    from ..models import Conversation, Message, UsageEvent
    from ..services.billing import PLAN_BY_ID

    since = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    minutes = (await db.execute(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(UsageEvent.workspace_id == auth.ws, UsageEvent.kind == "voice_minute", UsageEvent.created_at >= since))).scalar()
    msgs = (await db.execute(select(func.count()).select_from(Message).join(Conversation, Conversation.id == Message.conversation_id)
                             .where(Message.workspace_id == auth.ws, Message.role == "assistant", Message.created_at >= since, Conversation.channel != "playground"))).scalar()
    agents = (await db.execute(select(func.count()).select_from(Agent).where(Agent.workspace_id == auth.ws))).scalar()
    cost = (await db.execute(select(func.coalesce(func.sum(UsageEvent.cost_usd), 0)).where(UsageEvent.workspace_id == auth.ws, UsageEvent.created_at >= since))).scalar()
    plan = PLAN_BY_ID.get(auth.workspace.plan, PLAN_BY_ID["free"])
    sub = (await db.execute(select(Subscription).where(Subscription.workspace_id == auth.ws).order_by(Subscription.created_at.desc()))).scalars().first()
    return {"plan": plan, "usage": {"voice_minutes": round(float(minutes), 1), "messages": msgs, "agents": agents, "provider_spend_usd": round(float(cost), 4)},
            "subscription": to_dict(sub) if sub else None, "period_start": since.isoformat(), "period_end": (since + timedelta(days=32)).replace(day=1).isoformat()}


@router.post("/billing/checkout")
async def checkout(body: dict, auth: AuthContext = Depends(require_auth)):
    from ..services.billing import create_checkout

    try:
        return await create_checkout(body.get("plan", "growth"), body.get("currency", "INR"), auth.email, auth.ws)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/webhooks/dodo")
async def dodo_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    from ..services.billing import verify_webhook

    body = await request.body()
    if not verify_webhook(body, request.headers):
        raise HTTPException(401, "Invalid signature")
    event = await request.json()
    data = event.get("data", {})
    meta = data.get("metadata") or {}
    ws_id, plan = meta.get("workspace_id"), meta.get("plan")
    if ws_id and plan:
        ws = await db.get(Workspace, ws_id)
        if ws:
            status = "active" if event.get("type", "").endswith(("active", "renewed", "succeeded")) else data.get("status", event.get("type"))
            db.add(Subscription(workspace_id=ws.id, plan=plan, status=status, provider_ref=data.get("subscription_id") or data.get("payment_id"), data=event))
            if status == "active":
                ws.plan = plan
            await db.commit()
    return {"ok": True}


# ── Inbound channel webhooks ─────────────────────────────────────────────────
@router.get("/webhooks/whatsapp")
async def wa_verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == settings.meta_webhook_verify_token and settings.meta_webhook_verify_token:
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp")
async def wa_inbound(request: Request):
    from ..channels.whatsapp import handle_webhook, verify_signature

    body = await request.body()
    if not verify_signature(body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "Bad signature")
    n = await handle_webhook(await request.json())
    return {"accepted": n}


@router.post("/telephony/{channel_id}/incoming")
async def tel_incoming(channel_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from ..channels.common import channel_secret
    from ..channels.telephony import twiml_stream, verify_twilio

    ch = await db.get(Channel, channel_id)
    if not ch or not ch.enabled:
        return Response('<?xml version="1.0"?><Response><Say>This number is not in service.</Say></Response>', media_type="application/xml")
    form = dict(await request.form())
    ws = await db.get(Workspace, ch.workspace_id)
    url = f"{settings.public_webhook_url.rstrip('/')}/telephony/{channel_id}/incoming"
    if not verify_twilio(channel_secret(ws, ch).get("auth_token", ""), url, form, request.headers.get("x-twilio-signature")):
        raise HTTPException(403, "Invalid Twilio signature")
    from ..channels.telephony import is_blocked

    caller = str(form.get("From", ""))
    blocked = [b.strip() for b in (ch.config.get("blocked_prefixes") or [])]
    if any(caller.startswith(b) for b in blocked if b) or await is_blocked(ws.id, caller):
        return Response('<?xml version="1.0"?><Response><Reject/></Response>', media_type="application/xml")
    return Response(twiml_stream(channel_id, caller, str(form.get("To", ""))), media_type="application/xml")


@router.post("/telephony/{channel_id}/status")
async def tel_status(channel_id: str, request: Request):
    form = dict(await request.form())
    log.info(f"Call status {form.get('CallSid')}: {form.get('CallStatus')} answered_by={form.get('AnsweredBy')}")
    return {"ok": True}


@router.websocket("/telephony/{channel_id}/ws")
async def tel_ws(websocket: WebSocket, channel_id: str):
    from ..channels.telephony import handle_media_ws

    try:
        await handle_media_ws(websocket, channel_id)
    except WebSocketDisconnect:
        pass


@router.post("/telephony/dial")
async def tel_dial(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Place a single outbound AI call (test call from the dashboard)."""
    from ..channels.telephony import dial

    ch = await get_scoped(db, Channel, body["channel_id"], auth)
    try:
        return await dial(auth.workspace, ch, body["to"])
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


# ── Custom tools (HTTP + MCP) ────────────────────────────────────────────────
@router.get("/tools")
async def list_tools(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Tool).where(Tool.workspace_id == auth.ws).order_by(Tool.created_at.desc()))).scalars().all()
    return {"items": [to_dict(t, {"enc_secret"}) for t in rows]}


@router.post("/tools")
async def create_tool(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    import re

    from ..security.crypto import encrypt_json

    auth.require("builder")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", body.get("name", "")).strip("_")[:60]
    if not name:
        raise HTTPException(422, "Tool name is required")
    t = Tool(workspace_id=auth.ws, name=name, description=body.get("description", ""), type=body.get("type", "http"), config=body.get("config") or {})
    db.add(t)
    await db.flush()
    if body.get("secret"):
        ws = await db.merge(auth.workspace)
        t.enc_secret = encrypt_json(ws.id, ws.settings["dek"], f"tool:{t.id}", body["secret"])
    await db.commit()
    return to_dict(t, {"enc_secret"})


@router.post("/tools/mcp/discover")
async def mcp_discover(body: dict, auth: AuthContext = Depends(require_auth)):
    from ..services.mcp_client import list_remote_tools

    try:
        return {"tools": await asyncio.wait_for(list_remote_tools(body["url"], body.get("token")), timeout=20)}
    except Exception as e:
        raise HTTPException(400, f"Could not reach MCP server: {e}") from e


@router.post("/tools/{tool_id}/test")
async def test_tool(tool_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..brain.tools import ToolContext, execute
    from ..models import Conversation

    t = await get_scoped(db, Tool, tool_id, auth)
    agent = (await db.execute(select(Agent).where(Agent.workspace_id == auth.ws))).scalars().first()
    if not agent:
        raise HTTPException(422, "Create an agent first")
    conv = Conversation(workspace_id=auth.ws, agent_id=agent.id, channel="playground")
    db.add(conv)
    await db.flush()
    from ..brain.agent_config import normalize

    ctx = ToolContext(db=db, ws=auth.workspace, agent=agent, cfg=normalize(agent.config), conversation=conv, contact=None, channel="playground")
    out = await execute(ctx, t.name, body.get("args") or {})
    await db.rollback()
    return {"result": out}


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    t = await get_scoped(db, Tool, tool_id, auth)
    await db.delete(t)
    await db.commit()
    return {"ok": True}


# ── Realtime dashboard socket ────────────────────────────────────────────────
@router.websocket("/ws")
async def realtime(websocket: WebSocket):
    async with SessionLocal() as db:
        try:
            auth = await ws_auth(websocket, db)
        except HTTPException:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    q = hub.subscribe(auth.ws)
    await websocket.send_json({"type": "ready", "workspace_id": auth.ws})
    try:
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=25)
                await websocket.send_json(ev)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unsubscribe(auth.ws, q)


# ── Dev mode (local only) ────────────────────────────────────────────────────
dev = APIRouter(prefix="/dev")


def _dev_only(auth: AuthContext):
    if not (settings.is_dev and settings.dev_mode):
        raise HTTPException(404)


@dev.get("/status")
async def dev_status(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    _dev_only(auth)
    from ..channels.telegram import _pollers
    from ..voice.session import ACTIVE

    jobs = dict((await db.execute(select(Job.status, func.count()).group_by(Job.status))).all())
    recent = (await db.execute(select(Job).order_by(Job.created_at.desc()).limit(25))).scalars().all()
    return {"features": [f.__dict__ for f in feature_matrix()], "jobs": jobs, "recent_jobs": [to_dict(j, {"payload"}) | {"payload_keys": list(j.payload.keys())} for j in recent],
            "active_calls": len(ACTIVE), "telegram_pollers": len([t for t in _pollers.values() if not t.done()]),
            "realtime_listeners": hub.listeners(auth.ws), "workspace": auth.ws}


@dev.post("/seed-demo")
async def dev_seed(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    _dev_only(auth)
    from ..services.demo import seed_demo

    ws = await db.merge(auth.workspace)
    return await seed_demo(db, ws)


@dev.post("/simulate")
async def dev_simulate(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Pretend to be a customer on any channel (no WhatsApp/Telegram account needed)."""
    _dev_only(auth)
    from ..brain.respond import Turn, respond

    agent = await get_scoped(db, Agent, body["agent_id"], auth)
    channel = body.get("channel", "whatsapp")
    sender = str(body.get("from") or "+919876543210")
    key = {"whatsapp": "wa_id", "telegram": "telegram_id", "phone": "phone", "voice": "phone", "email": "email"}.get(channel, "web_session")
    identifiers = {key: sender}
    if body.get("email"):
        identifiers["email"] = body["email"]
    return await respond(db, Turn(ws=auth.workspace, agent=agent, channel=channel if channel != "phone" else "voice", text=body["text"],
                                  identifiers=identifiers, name=body.get("name"), channel_ref=f"sim:{channel}:{sender}",
                                  conversation_id=body.get("conversation_id")))


@dev.post("/reset-onboarding")
async def dev_reset_onboarding(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    _dev_only(auth)
    ws = await db.merge(auth.workspace)
    ws.onboarding = {}
    await db.commit()
    return {"ok": True}


@dev.post("/tick")
async def dev_tick(auth: AuthContext = Depends(require_auth)):
    _dev_only(auth)
    from ..services.campaigns import tick
    from ..worker.queue import enqueue

    moved = await tick()
    job = await enqueue("improve.workspace", {"workspace_id": auth.ws}, workspace_id=auth.ws, max_attempts=1)
    return {"campaign_targets_moved": moved, "improve_job": job}


@dev.post("/run-evals")
async def dev_run_evals(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    _dev_only(auth)
    from ..models import EvalRun, EvalSuite
    from ..worker.queue import enqueue

    agent = await get_scoped(db, Agent, body["agent_id"], auth)
    suite = (await db.execute(select(EvalSuite).where(EvalSuite.agent_id == agent.id, EvalSuite.kind == "qa"))).scalars().first()
    runs = []
    for kind, sid in (("qa", suite.id if suite else None), ("redteam", None), ("simulation", None)):
        if kind == "qa" and not sid:
            continue
        r = EvalRun(workspace_id=auth.ws, agent_id=agent.id, suite_id=sid, kind=kind)
        db.add(r)
        await db.flush()
        runs.append(r.id)
    await db.commit()
    for rid in runs:
        await enqueue("eval.run", {"run_id": rid}, workspace_id=auth.ws, max_attempts=1)
    return {"runs": runs}
