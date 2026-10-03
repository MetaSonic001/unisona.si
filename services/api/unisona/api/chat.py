"""Chat (SSE streaming) and voice (WebRTC) entry points: authenticated playground + public widget."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..brain.agent_config import normalize
from ..brain.respond import Turn, greeting, respond_events
from ..config import settings
from ..db import SessionLocal, get_db
from ..log import get_logger
from ..models import Agent, Channel, Conversation, Message, Workspace
from ..realtime import hub
from ..security import ratelimit
from ..security.auth import AuthContext, require_auth
from .common import get_scoped

log = get_logger("chat")
router = APIRouter()
_webrtc_handler = None


def webrtc_handler():
    global _webrtc_handler
    if _webrtc_handler is None:
        from pipecat.transports.smallwebrtc.connection import IceServer
        from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequestHandler

        _webrtc_handler = SmallWebRTCRequestHandler(ice_servers=[IceServer(urls="stun:stun.l.google.com:19302")])
    return _webrtc_handler


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def _stream_turn(turn_factory, ws_id: str, agent_id: str):
    """Run respond_events in its own DB session (the request session closes when streaming starts)."""
    async with SessionLocal() as db:
        ws = await db.get(Workspace, ws_id)
        agent = await db.get(Agent, agent_id)
        try:
            async for ev in respond_events(db, turn_factory(ws, agent)):
                yield _sse(ev)
        except Exception as e:
            log.error(f"chat stream failed: {e}")
            yield _sse({"type": "error", "message": "Something went wrong. Please try again."})


# ── Authenticated (playground, simulators, API) ──────────────────────────────
@router.post("/chat/{agent_id}")
async def chat(agent_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    agent = await get_scoped(db, Agent, agent_id, auth)
    ratelimit.check(f"chat:{auth.ws}", 120)
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "text is required")
    channel = body.get("channel") or "playground"
    if channel not in {"playground", "web", "widget", "whatsapp", "telegram", "email", "voice"}:
        raise HTTPException(422, "unsupported channel")
    identifiers = body.get("identifiers") or {}
    use_draft = bool(body.get("use_draft", channel == "playground"))
    ws_id, a_id = auth.ws, agent.id

    def factory(ws, ag):
        return Turn(ws=ws, agent=ag, channel=channel, text=text, identifiers=identifiers, name=body.get("name"),
                    channel_ref=body.get("channel_ref") or (list(identifiers.values())[0] if identifiers else None),
                    conversation_id=body.get("conversation_id"), use_draft=use_draft, variables=body.get("variables") or {})

    if body.get("stream", True):
        return StreamingResponse(_stream_turn(factory, ws_id, a_id), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    reply = {}
    async for ev in respond_events(db, factory(auth.workspace, agent)):
        if ev["type"] == "final":
            reply = ev["reply"]
    return reply


@router.get("/chat/{agent_id}/greeting")
async def chat_greeting(agent_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    agent = await get_scoped(db, Agent, agent_id, auth)
    return {"text": await greeting(db, agent, use_draft=True)}


@router.post("/voice/offer")
async def voice_offer(request: Request, background: BackgroundTasks, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):

    body = await request.json()
    data = body.get("request_data") or body.get("requestData") or {}
    agent = await get_scoped(db, Agent, data.get("agent_id", ""), auth)
    return await _offer(body, background, auth.ws, agent.id, use_draft=bool(data.get("use_draft", True)),
                        identifiers=data.get("identifiers") or {"web_session": f"dash-{auth.user_id}"}, name=auth.name)


@router.patch("/voice/offer")
async def voice_ice(request: Request, auth: AuthContext = Depends(require_auth)):
    return await _patch(await request.json())


_CALL_TASKS: set[asyncio.Task] = set()  # strong refs so running calls aren't garbage-collected


async def _offer(body: dict, background: BackgroundTasks, ws_id: str, agent_id: str, *, use_draft: bool, identifiers: dict, name: str | None):
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.request_handler import SmallWebRTCRequest
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    from ..voice.session import prepare_call, run_voice_session

    t_offer = time.perf_counter()
    req = SmallWebRTCRequest.from_dict({k: v for k, v in body.items() if k in {"sdp", "type", "pc_id", "restart_pc", "request_data", "requestData"}})
    # Load the agent, keys and greeting audio now, in parallel with the WebRTC handshake, instead of after it.
    prepared = asyncio.create_task(prepare_call(ws_id=ws_id, agent_id=agent_id, channel="voice", use_draft=use_draft, identifiers=identifiers,
                                                caller_name=name, call_meta={"transport": "webrtc", "t_offer": t_offer}))
    _CALL_TASKS.add(prepared)
    prepared.add_done_callback(_CALL_TASKS.discard)

    async def on_connection(connection):
        params = TransportParams(audio_in_enabled=True, audio_out_enabled=True)
        try:  # browsers suppress noise too, but not every client does (kiosks, SDKs, simulators)
            prep = await asyncio.wait_for(asyncio.shield(prepared), timeout=5)
            if prep.snap["cfg"]["voice"].get("noise_filter", True):
                from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

                params.audio_in_filter = RNNoiseFilter()
        except Exception as e:
            log.warning(f"Noise filter not applied: {e}")
        transport = SmallWebRTCTransport(webrtc_connection=connection, params=params)
        task = asyncio.create_task(run_voice_session(transport, ws_id=ws_id, agent_id=agent_id, channel="voice", prepared=prepared))
        _CALL_TASKS.add(task)
        task.add_done_callback(_CALL_TASKS.discard)

    return await webrtc_handler().handle_web_request(request=req, webrtc_connection_callback=on_connection)


async def _patch(body: dict):
    from pipecat.transports.smallwebrtc.request_handler import IceCandidate, SmallWebRTCPatchRequest

    await webrtc_handler().handle_patch_request(SmallWebRTCPatchRequest(
        pc_id=body["pc_id"], candidates=[IceCandidate(**c) for c in body.get("candidates", [])]))
    return {"status": "success"}


# ── Public widget / hosted page ──────────────────────────────────────────────
async def _public_agent(db: AsyncSession, public_key: str, request: Request) -> tuple[Agent, Workspace, dict]:
    agent = (await db.execute(select(Agent).where(Agent.public_key == public_key))).scalar_one_or_none()
    if not agent or agent.status == "paused":
        raise HTTPException(404, "Agent not found or paused")
    cfg = normalize(agent.published_config or agent.config)
    allowed = [d.strip().lower() for d in cfg["widget"].get("allowed_domains") or [] if d.strip()]
    origin = (request.headers.get("origin") or "").lower()
    if allowed and origin and not any(origin.endswith(d) for d in allowed) and not origin.startswith(settings.app_url.lower()):
        raise HTTPException(403, "This domain is not allowed to use this agent")
    ws = await db.get(Workspace, agent.workspace_id)
    return agent, ws, cfg


@router.get("/public/agents/{public_key}")
async def public_config(public_key: str, request: Request, db: AsyncSession = Depends(get_db)):
    agent, ws, cfg = await _public_agent(db, public_key, request)
    chans = {c.type: c.enabled for c in (await db.execute(select(Channel).where(Channel.agent_id == agent.id))).scalars()}
    return {"name": cfg["persona"].get("name") or agent.name, "business": cfg["business"].get("name") or ws.name,
            "greeting": await greeting(db, agent), "widget": cfg["widget"], "voice_enabled": bool(chans.get("voice", True) and cfg["widget"].get("voice", True)),
            "chat_enabled": bool(chans.get("widget", True) or chans.get("web", True)), "languages": cfg["languages"],
            "branding": ws.branding or {}, "status": agent.status}


def _verify_identity(ws: Workspace, user_id: str | None, user_hash: str | None) -> bool:
    secret = ws.settings.get("identity_secret")
    if not (user_id and user_hash and secret):
        return False
    expected = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, user_hash)


@router.post("/public/chat/{public_key}")
async def public_chat(public_key: str, body: dict, request: Request, db: AsyncSession = Depends(get_db)):
    agent, ws, cfg = await _public_agent(db, public_key, request)
    ip = request.client.host if request.client else "?"
    ratelimit.check(f"pub:ip:{ip}", 40)
    session_id = (body.get("session_id") or "")[:64] or str(uuid.uuid4())
    ratelimit.check(f"pub:sess:{session_id}", 20)
    text = (body.get("text") or "").strip()[:4000]
    if not text:
        raise HTTPException(422, "text is required")
    identifiers = {"web_session": session_id}
    if body.get("email"):
        identifiers["email"] = body["email"]
    if body.get("phone"):
        identifiers["phone"] = body["phone"]
    if _verify_identity(ws, body.get("user_id"), body.get("user_hash")):
        identifiers["external_id"] = body["user_id"]
    channel = body.get("channel") if body.get("channel") in {"web", "widget"} else "widget"
    ws_id, a_id = ws.id, agent.id

    def factory(w, ag):
        return Turn(ws=w, agent=ag, channel=channel, text=text, identifiers=identifiers, name=body.get("name"),
                    channel_ref=session_id, conversation_id=body.get("conversation_id"), variables=body.get("variables") or {})

    return StreamingResponse(_stream_turn(factory, ws_id, a_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/public/conversations/{conversation_id}/events")
async def public_events(conversation_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    """Live stream of human-agent replies for a widget visitor."""
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.channel_ref != session_id:
        raise HTTPException(404)
    topic = f"conv:{conversation_id}"

    async def gen():
        q = hub.subscribe(topic)
        try:
            yield _sse({"type": "ready"})
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=20)
                    if ev.get("type") in {"human.message", "agent.joined"}:
                        yield _sse(ev)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            hub.unsubscribe(topic, q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/public/conversations/{conversation_id}/messages")
async def public_history(conversation_id: str, session_id: str, db: AsyncSession = Depends(get_db)):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.channel_ref != session_id:
        raise HTTPException(404)
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conversation_id, Message.role.in_(["user", "assistant", "human"]))
                             .order_by(Message.created_at).limit(100))).scalars().all()
    return {"items": [{"role": m.role, "content": m.content, "ir": m.ir, "created_at": m.created_at.isoformat()} for m in msgs], "status": conv.status}


@router.post("/public/voice/{public_key}/offer")
async def public_voice(public_key: str, request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    agent, ws, cfg = await _public_agent(db, public_key, request)
    ip = request.client.host if request.client else "?"
    ratelimit.check(f"pubvoice:{ip}", 6, 60)
    body = await request.json()
    data = body.get("request_data") or body.get("requestData") or {}
    session_id = (data.get("session_id") or str(uuid.uuid4()))[:64]
    return await _offer(body, background, ws.id, agent.id, use_draft=False, identifiers={"web_session": session_id}, name=data.get("name"))


@router.patch("/public/voice/{public_key}/offer")
async def public_voice_ice(public_key: str, request: Request):
    return await _patch(await request.json())
