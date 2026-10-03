"""Send a message to a contact on a specific channel (used by tools, campaigns, automations, humans)."""
from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..log import feature_unavailable, get_logger
from ..models import Agent, Channel, Contact, ContactIdentity, Workspace
from .common import channel_secret

log = get_logger("outbound")


async def _identity(db: AsyncSession, contact: Contact, types: list[str]) -> str | None:
    row = (await db.execute(select(ContactIdentity).where(ContactIdentity.contact_id == contact.id, ContactIdentity.type.in_(types)))).scalars().first()
    return row.value if row else None


async def _channel(db: AsyncSession, ws: Workspace, agent: Agent | None, type_: str) -> Channel | None:
    q = select(Channel).where(Channel.workspace_id == ws.id, Channel.type == type_, Channel.enabled.is_(True))
    rows = (await db.execute(q)).scalars().all()
    if not rows:
        return None
    if agent:
        for r in rows:
            if r.agent_id == agent.id:
                return r
    return rows[0]


def unsubscribe_token(ws_id: str, contact_id: str) -> str:
    import hashlib
    import hmac

    sig = hmac.new(settings.unisona_master_key.encode(), f"{ws_id}:{contact_id}".encode(), hashlib.sha256).hexdigest()[:20]
    return f"{contact_id}.{sig}"


async def send_email(ws: Workspace, to: str, subject: str, text: str, *, contact_id: str | None = None, marketing: bool = False) -> tuple[bool, str]:
    if not (settings.resend_api_key and settings.alert_from_email):
        feature_unavailable("Sending email to customers", "RESEND_API_KEY + ALERT_FROM_EMAIL")
        return False, "email sending is not configured"
    sender_name = (ws.branding or {}).get("name") or ws.name
    body = text
    if marketing and contact_id:
        body += f"\n\n--\nDon't want these emails? Unsubscribe: {settings.app_url.rstrip('/')}/u/{unsubscribe_token(ws.id, contact_id)}"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                         json={"from": f"{sender_name} <{settings.alert_from_email}>", "to": [to], "subject": subject[:200], "text": body,
                               **({"reply_to": ws.settings.get("support_email")} if ws.settings.get("support_email") else {})})
    return (r.status_code < 300), f"HTTP {r.status_code}"


async def send_to_contact(db: AsyncSession, ws: Workspace, agent: Agent | None, contact: Contact, channel: str, text: str,
                          options: list[str] | None = None, *, subject: str | None = None, purpose: str = "transactional",
                          check_compliance: bool = True) -> tuple[bool, str]:
    if check_compliance:
        from ..services.compliance import check_outbound

        ok, why = await check_outbound(db, ws, contact, contact.phone or contact.email or "", channel, purpose)
        if not ok:
            return False, f"blocked: {why}"
    try:
        if channel == "whatsapp":
            to = await _identity(db, contact, ["wa_id", "phone"]) or contact.phone
            ch = await _channel(db, ws, agent, "whatsapp")
            if not ch:
                return False, "WhatsApp is not connected for this workspace"
            if not to:
                return False, "customer's WhatsApp number is unknown"
            from .whatsapp import send

            await send(ch.config, channel_secret(ws, ch).get("access_token", ""), to, text, options)
            return True, "sent"
        if channel == "telegram":
            chat_id = await _identity(db, contact, ["telegram_id"])
            ch = await _channel(db, ws, agent, "telegram")
            if not ch or not chat_id:
                return False, "customer has not messaged the Telegram bot yet"
            from .telegram import send

            await send(channel_secret(ws, ch).get("bot_token", ""), chat_id, text, options)
            return True, "sent"
        if channel == "email":
            to = contact.email or await _identity(db, contact, ["email"])
            if not to:
                return False, "customer's email is unknown"
            return await send_email(ws, to, subject or f"Message from {(ws.branding or {}).get('name') or ws.name}", text,
                                    contact_id=contact.id, marketing=purpose == "promotional")
        if channel in {"instagram", "messenger"}:
            ident = "instagram_id" if channel == "instagram" else "messenger_id"
            rid = await _identity(db, contact, [ident])
            ch = await _channel(db, ws, agent, channel)
            if not ch or not rid:
                return False, f"customer has not messaged the {channel} account yet (Meta only allows replies within 24h)"
            from .meta_messaging import send as meta_send

            await meta_send(channel, ch.config, channel_secret(ws, ch).get("page_token", ""), rid, text, options)
            return True, "sent"
        if channel == "whatsapp_template":
            to = await _identity(db, contact, ["wa_id", "phone"]) or contact.phone
            ch = await _channel(db, ws, agent, "whatsapp")
            if not ch or not to:
                return False, "WhatsApp not connected or number unknown"
            from .whatsapp import send_template

            name, _, lang = (subject or "").partition("|")
            await send_template(ch.config, channel_secret(ws, ch).get("access_token", ""), to, name, lang or "en", [text] if text else [])
            return True, "sent"
        if channel == "sms":
            ch = await _channel(db, ws, agent, "phone")
            to = contact.phone
            if not ch or not to:
                return False, "SMS needs a connected phone number"
            from .telephony import send_sms

            await send_sms(ws, ch, to, text)
            return True, "sent"
        if channel in {"web", "widget"}:
            return False, "web visitors can only be reached while they're on the site"
        return False, f"unsupported channel {channel}"
    except Exception as e:
        log.warning(f"send_to_contact {channel} failed: {e}")
        return False, str(e)[:200]
