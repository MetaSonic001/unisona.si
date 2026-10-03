"""Instagram DMs and Facebook Messenger (same Meta app as WhatsApp; each business connects its own
Facebook Page / Instagram professional account with a Page access token = BYOK).

Webhook objects: "page" (Messenger) and "instagram". The same brain answers; identities are
`messenger_id` / `instagram_id`, merged into the shared contact when the customer shares a phone/email.
"""
from __future__ import annotations

import httpx
from sqlalchemy import select

from ..db import SessionLocal
from ..log import get_logger
from ..models import Agent, Channel, Workspace
from .common import Debouncer, Deduper, channel_secret

log = get_logger("meta")
GRAPH = "https://graph.facebook.com/v22.0"
_dedupe = Deduper()
_debounce = Debouncer(1.5)


async def send(kind: str, cfg: dict, token: str, recipient_id: str, text: str, options: list[str] | None = None) -> dict:
    if not token:
        raise RuntimeError(f"{kind} channel has no page access token")
    msg: dict = {"text": text[:1000]}
    if options:
        msg["quick_replies"] = [{"content_type": "text", "title": o[:20], "payload": f"opt_{i}"} for i, o in enumerate(options[:13])]
    path = f"{cfg.get('ig_user_id')}/messages" if kind == "instagram" and cfg.get("ig_user_id") else "me/messages"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH}/{path}", params={"access_token": token},
                         json={"recipient": {"id": recipient_id}, "messaging_type": "RESPONSE", "message": msg})
    if r.status_code >= 300:
        raise RuntimeError(f"{kind} send failed ({r.status_code}): {r.text[:200]}")
    return r.json()


async def profile_name(token: str, user_id: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{GRAPH}/{user_id}", params={"access_token": token, "fields": "name,username"})
        j = r.json() if r.status_code < 300 else {}
        return j.get("name") or j.get("username")
    except Exception:
        return None


async def handle_webhook(payload: dict) -> int:
    obj = payload.get("object")
    if obj not in {"page", "instagram"}:
        return 0
    kind = "instagram" if obj == "instagram" else "messenger"
    accepted = 0
    for entry in payload.get("entry", []):
        account_id = str(entry.get("id", ""))
        for ev in entry.get("messaging", []):
            msg = ev.get("message") or {}
            if msg.get("is_echo") or _dedupe.seen(msg.get("mid", "")):
                continue
            text = msg.get("text")
            if not text and msg.get("attachments"):
                text = f"[Sent a {msg['attachments'][0].get('type', 'file')}]"
            sender = (ev.get("sender") or {}).get("id")
            if not text or not sender:
                continue
            accepted += 1
            _debounce.push(f"{kind}:{account_id}:{sender}", text,
                           lambda merged, k=kind, a=account_id, s=sender, mid=msg.get("mid"): process_inbound(k, a, s, merged, mid))
    return accepted


async def process_inbound(kind: str, account_id: str, sender: str, text: str, mid: str | None) -> dict | None:
    from ..brain.respond import Turn, respond

    key = "ig_user_id" if kind == "instagram" else "page_id"
    async with SessionLocal() as db:
        ch = (await db.execute(select(Channel).where(Channel.type == kind, Channel.enabled.is_(True),
                                                     Channel.config[key].astext == account_id))).scalars().first()
        if not ch:
            log.warning(f"No {kind} channel for account {account_id}")
            return None
        ws = await db.get(Workspace, ch.workspace_id)
        agent = await db.get(Agent, ch.agent_id)
        token = channel_secret(ws, ch).get("page_token", "")
        name = await profile_name(token, sender)
        ident = "instagram_id" if kind == "instagram" else "messenger_id"
        reply = await respond(db, Turn(ws=ws, agent=agent, channel=kind, text=text, identifiers={ident: sender}, name=name,
                                       channel_ref=f"{kind}:{sender}", channel_msg_id=mid))
        if reply.get("text"):
            try:
                await send(kind, ch.config, token, sender, reply["text"], reply.get("options"))
            except Exception as e:
                log.error(str(e))
        return reply
