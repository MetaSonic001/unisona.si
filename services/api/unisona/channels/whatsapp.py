"""WhatsApp Cloud API channel (BYOK: each workspace connects its own WABA number)."""
from __future__ import annotations

import hashlib
import hmac
import re

import httpx
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..log import get_logger
from ..models import Agent, Channel, Workspace
from .common import Debouncer, Deduper, channel_secret

log = get_logger("whatsapp")
GRAPH = "https://graph.facebook.com/v22.0"
_dedupe = Deduper()
_debounce = Debouncer(2.0)


def verify_signature(body: bytes, header: str | None) -> bool:
    if not settings.meta_app_secret:
        return settings.is_dev  # allow unsigned only in local development
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


async def send(ch_cfg: dict, token: str, to: str, text: str, options: list[str] | None = None) -> dict:
    phone_number_id = ch_cfg.get("phone_number_id")
    if not (phone_number_id and token):
        raise RuntimeError("WhatsApp channel is missing phone_number_id or access token")
    to = re.sub(r"\D", "", to)
    if options and len(options) <= 3:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "interactive", "interactive": {
            "type": "button", "body": {"text": text[:1024]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": f"opt_{i}", "title": o[:20]}} for i, o in enumerate(options)]}}}
    elif options:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "interactive", "interactive": {
            "type": "list", "body": {"text": text[:1024]},
            "action": {"button": "Choose", "sections": [{"title": "Options", "rows": [{"id": f"opt_{i}", "title": o[:24]} for i, o in enumerate(options[:10])]}]}}}
    else:
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:4096], "preview_url": True}}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH}/{phone_number_id}/messages", json=payload, headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 300:
            raise RuntimeError(f"WhatsApp send failed ({r.status_code}): {r.text[:300]}")
        return r.json()


async def send_template(ch_cfg: dict, token: str, to: str, name: str, language: str = "en", params: list[str] | None = None) -> dict:
    """Business-initiated message using an approved template (required outside the 24h service window)."""
    phone_number_id = ch_cfg.get("phone_number_id")
    if not (phone_number_id and token and name):
        raise RuntimeError("WhatsApp template send needs phone_number_id, access token and template name")
    tpl: dict = {"name": name, "language": {"code": language}}
    if params:
        tpl["components"] = [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:1024]} for p in params]}]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH}/{phone_number_id}/messages", headers={"Authorization": f"Bearer {token}"},
                         json={"messaging_product": "whatsapp", "to": re.sub(r"\D", "", to), "type": "template", "template": tpl})
    if r.status_code >= 300:
        raise RuntimeError(f"WhatsApp template send failed ({r.status_code}): {r.text[:300]}")
    return r.json()


async def list_templates(ch_cfg: dict, token: str) -> list[dict]:
    waba = ch_cfg.get("waba_id")
    if not (waba and token):
        raise RuntimeError("Add the WhatsApp Business Account ID (waba_id) to the channel to manage templates")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{GRAPH}/{waba}/message_templates", headers={"Authorization": f"Bearer {token}"},
                        params={"limit": 200, "fields": "name,language,status,category,components"})
    if r.status_code >= 300:
        raise RuntimeError(f"Could not load templates ({r.status_code}): {r.text[:200]}")
    return r.json().get("data", [])


async def create_template(ch_cfg: dict, token: str, name: str, language: str, category: str, body: str, example: list[str] | None = None) -> dict:
    waba = ch_cfg.get("waba_id")
    if not waba:
        raise RuntimeError("Add the WhatsApp Business Account ID (waba_id) to the channel first")
    comp: dict = {"type": "BODY", "text": body}
    if example:
        comp["example"] = {"body_text": [example]}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH}/{waba}/message_templates", headers={"Authorization": f"Bearer {token}"},
                         json={"name": name, "language": language, "category": category.upper(), "components": [comp]})
    if r.status_code >= 300:
        raise RuntimeError(f"Template submission failed ({r.status_code}): {r.text[:300]}")
    return r.json()


def _extract_text(msg: dict) -> str | None:
    t = msg.get("type")
    if t == "text":
        return msg["text"]["body"]
    if t == "interactive":
        it = msg["interactive"]
        return (it.get("button_reply") or it.get("list_reply") or {}).get("title")
    if t == "button":
        return msg["button"].get("text")
    if t == "location":
        loc = msg["location"]
        return f"[Shared location: {loc.get('name') or ''} {loc.get('latitude')},{loc.get('longitude')}]"
    if t in {"image", "document", "audio", "video"}:
        return f"[Sent a {t}]" + (f": {msg[t].get('caption')}" if msg.get(t, {}).get("caption") else "")
    return None


async def handle_webhook(payload: dict) -> int:
    """Process a Meta webhook payload. Returns number of messages accepted."""
    accepted = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            pnid = (value.get("metadata") or {}).get("phone_number_id")
            contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                if _dedupe.seen(msg.get("id", "")):
                    continue
                text = _extract_text(msg)
                if not text or not pnid:
                    continue
                accepted += 1
                wa_id = msg["from"]
                name = contacts.get(wa_id)
                _debounce.push(f"{pnid}:{wa_id}", text, lambda merged, p=pnid, w=wa_id, n=name, mid=msg.get("id"): process_inbound(p, w, n, merged, mid))
    return accepted


async def process_inbound(phone_number_id: str, wa_id: str, name: str | None, text: str, msg_id: str | None) -> dict | None:
    from ..brain.respond import Turn, respond

    async with SessionLocal() as db:
        ch = (await db.execute(select(Channel).where(Channel.type == "whatsapp", Channel.enabled.is_(True),
                                                     Channel.config["phone_number_id"].astext == phone_number_id))).scalars().first()
        if not ch:
            log.warning(f"No WhatsApp channel for phone_number_id {phone_number_id}")
            return None
        ws = await db.get(Workspace, ch.workspace_id)
        agent = await db.get(Agent, ch.agent_id)
        reply = await respond(db, Turn(ws=ws, agent=agent, channel="whatsapp", text=text, identifiers={"wa_id": wa_id},
                                       name=name, channel_ref=wa_id, channel_msg_id=msg_id))
        if reply.get("text"):
            try:
                await send(ch.config, channel_secret(ws, ch).get("access_token", ""), wa_id, reply["text"], reply.get("options"))
            except Exception as e:
                log.error(str(e))
        return reply
