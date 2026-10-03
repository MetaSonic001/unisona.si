"""Calling infrastructure routes: answering-machine detection, warm-transfer whispers, Plivo XML,
two-way SMS webhooks, live transfer from the dashboard, call capacity and compliance settings."""
from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..log import get_logger
from ..models import Channel, Contact, DndEntry, Workspace
from ..security.auth import AuthContext, require_auth
from .common import audit, get_scoped

log = get_logger("calling")
router = APIRouter()
XML = "application/xml"

_MACHINE = {"machine_end_beep", "machine_end_silence", "machine_end_other", "machine_start", "fax"}


def _session_for(provider_call_id: str):
    from ..voice.session import ACTIVE

    return next((s for s in ACTIVE.values() if s.meta.get("provider_call_id") == provider_call_id), None)


# ── Answering machine detection (async; the call is already talking to the AI) ──
@router.post("/telephony/{channel_id}/amd")
async def amd_callback(channel_id: str, request: Request):
    ctype = request.headers.get("content-type", "")
    data = dict(await request.form()) if "form" in ctype else (await request.json() if "json" in ctype else {})
    if "data" in data and isinstance(data["data"], dict):  # Telnyx event envelope
        payload = data["data"].get("payload", {})
        call_id, machine = payload.get("call_control_id", ""), payload.get("result") == "machine"
    else:
        call_id = str(data.get("CallSid") or data.get("CallUUID") or "")
        answered = str(data.get("AnsweredBy") or "").lower()
        machine = answered in _MACHINE or str(data.get("Machine", "")).lower() == "true"
    log.info(f"AMD result for {call_id}: {'machine' if machine else 'human'}")
    sess = _session_for(call_id)
    if sess and machine:
        await sess.on_voicemail("provider_amd")
    return {"ok": True}


@router.get("/telephony/{channel_id}/whisper")
@router.post("/telephony/{channel_id}/whisper")
async def whisper(channel_id: str, text: str = ""):
    """Played only to the human receiving a warm transfer, before the caller is connected."""
    say = escape(text or "Incoming transfer from the AI assistant.")
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response><Say>Transfer from your AI assistant. {say}</Say></Response>', media_type=XML)


@router.get("/telephony/{channel_id}/plivo-answer")
async def plivo_answer(channel_id: str, request: Request, target_id: str = ""):
    from ..channels.telephony import ws_url

    url = escape(ws_url(channel_id))
    extra = escape(f'{{"direction":"outbound","target_id":"{target_id}"}}')
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response><Stream bidirectional="true" keepCallAlive="true" '
                    f'contentType="audio/x-mulaw;rate=8000" extraHeaders="{extra}">{url}</Stream></Response>', media_type=XML)


@router.get("/telephony/{channel_id}/plivo-dial")
async def plivo_dial(channel_id: str, to: str, summary: str = ""):
    speak = f"<Speak>{escape(summary)}</Speak>" if summary else ""
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{speak}<Dial><Number>{escape(to)}</Number></Dial></Response>', media_type=XML)


# ── Two-way SMS (Twilio / Plivo form posts, Telnyx JSON) ──────────────────────
@router.post("/telephony/{channel_id}/sms")
async def sms_inbound(channel_id: str, request: Request):
    from ..channels.telephony import handle_inbound_sms
    from ..services.compliance import is_opt_out

    ctype = request.headers.get("content-type", "")
    if "json" in ctype:
        body = await request.json()
        p = (body.get("data") or {}).get("payload") or {}
        if (body.get("data") or {}).get("event_type") != "message.received":
            return {"ok": True}
        sender, text, mid = (p.get("from") or {}).get("phone_number", ""), p.get("text", ""), p.get("id")
    else:
        form = dict(await request.form())
        sender = str(form.get("From") or form.get("from") or "")
        text = str(form.get("Body") or form.get("Text") or "")
        mid = str(form.get("MessageSid") or form.get("MessageUUID") or "")
    if not sender or not text:
        return Response('<?xml version="1.0"?><Response/>', media_type=XML)
    if is_opt_out(text):
        # Carriers handle STOP themselves for Twilio; we also record it so AI campaigns respect it.
        from ..db import SessionLocal
        from ..services.compliance import opt_out

        async with SessionLocal() as db:
            ch = await db.get(Channel, channel_id)
            if ch:
                ws = await db.get(Workspace, ch.workspace_id)
                await opt_out(db, ws, None, "sms", sender, "replied STOP by SMS")
                await db.commit()
        return Response('<?xml version="1.0"?><Response/>', media_type=XML)
    import asyncio

    asyncio.create_task(handle_inbound_sms(channel_id, sender, text, mid))  # reply is sent via the API, not inline TwiML
    return Response('<?xml version="1.0"?><Response/>', media_type=XML)


# ── Dashboard: live transfer + capacity ──────────────────────────────────────
@router.post("/calls/live/{call_id}/transfer")
async def live_transfer(call_id: str, body: dict, auth: AuthContext = Depends(require_auth)):
    from ..voice.session import ACTIVE

    auth.require("agent")
    sess = ACTIVE.get(call_id)
    if not sess or sess.ws_id != auth.ws:
        raise HTTPException(404, "Call is not live")
    to = (body.get("to") or "").strip()
    if not to:
        raise HTTPException(422, "Transfer number required")
    result = await sess.transfer(to, mode=body.get("mode", "warm"), reason=body.get("reason") or "transferred by supervisor")
    return {"result": result}


@router.get("/calls/capacity")
async def capacity(auth: AuthContext = Depends(require_auth)):
    from ..channels.telephony import active_calls, call_limit

    return {"active": active_calls(auth.ws), "limit": call_limit(auth.workspace), "plan": auth.workspace.plan}


# ── Compliance: settings, do-not-contact list, consent ───────────────────────
@router.get("/compliance")
async def compliance_get(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.compliance import settings_for

    count = (await db.execute(select(func.count()).select_from(DndEntry).where(DndEntry.workspace_id == auth.ws))).scalar()
    recent = (await db.execute(select(DndEntry).where(DndEntry.workspace_id == auth.ws).order_by(DndEntry.created_at.desc()).limit(100))).scalars().all()
    return {"settings": settings_for(auth.workspace), "dnd_count": count,
            "dnd": [{"id": d.id, "value": d.value, "reason": d.reason, "created_at": d.created_at.isoformat()} for d in recent]}


@router.patch("/compliance")
async def compliance_set(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    ws = await db.get(Workspace, auth.ws)
    allowed = {"auto_opt_out", "calling_start", "calling_end", "require_consent_for_promotional"}
    ws.settings = {**ws.settings, "compliance": {**(ws.settings.get("compliance") or {}), **{k: v for k, v in body.items() if k in allowed}}}
    if "max_concurrent_calls" in body:
        ws.settings = {**ws.settings, "max_concurrent_calls": int(body["max_concurrent_calls"]) or None}
    await audit(db, auth, "compliance.update", auth.ws, body)
    await db.commit()
    return {"ok": True}


@router.post("/compliance/dnd")
async def dnd_add(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.compliance import normalize

    auth.require("agent")
    values = [v for v in (body.get("values") or [body.get("value")]) if v]
    existing = {normalize(v) for v in (await db.execute(select(DndEntry.value).where(DndEntry.workspace_id == auth.ws))).scalars()}
    added = 0
    for v in values:
        n = normalize(str(v))
        if n and n not in existing:
            db.add(DndEntry(workspace_id=auth.ws, value=n, reason=body.get("reason", "manual")))
            existing.add(n)
            added += 1
    await db.commit()
    return {"added": added}


@router.post("/compliance/dnd/import")
async def dnd_import(file: UploadFile = File(...), auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Upload a scrub list (CSV/TXT, one number or email per line or in the first column)."""
    raw = (await file.read()).decode("utf-8", errors="ignore")
    values = [row[0].strip() for row in csv.reader(io.StringIO(raw)) if row and row[0].strip() and not row[0].lower().startswith(("phone", "number", "email"))]
    return await dnd_add({"values": values, "reason": f"imported {file.filename}"}, auth, db)


@router.delete("/compliance/dnd/{entry_id}")
async def dnd_remove(entry_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    await db.execute(delete(DndEntry).where(DndEntry.id == entry_id, DndEntry.workspace_id == auth.ws))
    await db.commit()
    return {"ok": True}


@router.post("/contacts/{contact_id}/consent")
async def set_consent(contact_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.compliance import opt_out, record_consent

    contact = await get_scoped(db, Contact, contact_id, auth)
    channel, status = body.get("channel", "marketing"), body.get("status", "opted_in")
    if status == "opted_out":
        await opt_out(db, auth.workspace, contact, channel, reason=body.get("reason", "set by team"))
    else:
        record_consent(contact, channel, status, body.get("source", f"set by {auth.email or auth.user_id}"))
    await db.commit()
    return {"consent": contact.consent}
