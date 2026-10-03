"""Outbound compliance: opt-outs, do-not-contact lists, consent and calling hours.

India (TRAI TCCCPR) and most regulators expect: honour opt-outs immediately, never call numbers on the
do-not-disturb list for promotions, call only during permitted hours, and record consent. Every
outbound path (campaigns, automations, agent tools, dialer) goes through `check_outbound`.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import utcnow
from ..log import get_logger
from ..models import Activity, Contact, ContactIdentity, DndEntry, Workspace

log = get_logger("compliance")

# "stop", "unsubscribe", "don't call me again", Hindi/Hinglish "call mat karo", "message band karo", "मत करो"
_OPT_OUT = re.compile(
    r"^\s*(stop|stop all|unsubscribe|opt[\s-]?out|cancel)\s*[.!]*\s*$"
    r"|\b(don'?t|do not|never|stop)\s+(call|calling|message|messaging|text|texting|contact|contacting|email|emailing)\s+(me|us)\b"
    r"|\b(remove|delete|take)\s+(me|my number|my details)\s+(from|off)\b"
    r"|\b(call|message|msg|sms|phone)\s+(mat|na)\s+(karo|karna|kijiye|kariye|bhejo|bhejna)\b"
    r"|\b(band|bandh)\s+(karo|kar do|kijiye)\b.*\b(call|message|msg|sms)\b|\b(call|message|msg|sms)\b.*\b(band|bandh)\s+(karo|kar do|kijiye)\b"
    r"|(कॉल|फोन|मैसेज|संदेश)\s*(मत|ना)\s*(करें|करो|कीजिए|भेजें|भेजो)",
    re.I,
)

DEFAULTS = {"auto_opt_out": True, "calling_start": "09:00", "calling_end": "21:00", "require_consent_for_promotional": True}
OPT_OUT_REPLY = {
    "en": "Understood. You won't receive any more calls or messages from us. Take care!",
    "hi": "ठीक है, अब आपको हमारी तरफ़ से कोई कॉल या मैसेज नहीं आएगा। धन्यवाद!",
    "hinglish": "Theek hai, ab aapko humari taraf se koi call ya message nahi aayega. Dhanyavaad!",
}


def settings_for(ws: Workspace) -> dict:
    return {**DEFAULTS, **((ws.settings or {}).get("compliance") or {})}


def is_opt_out(text: str) -> bool:
    return bool(text and len(text) < 240 and _OPT_OUT.search(text))


def normalize(value: str) -> str:
    v = (value or "").strip().lower()
    if "@" in v:
        return v
    digits = re.sub(r"[^\d+]", "", v)
    return digits[-10:] if len(re.sub(r"\D", "", digits)) >= 10 else digits


async def _addresses(db: AsyncSession, contact: Contact | None) -> set[str]:
    if not contact:
        return set()
    vals = {contact.phone or "", contact.email or ""}
    rows = (await db.execute(select(ContactIdentity.value).where(ContactIdentity.contact_id == contact.id))).scalars().all()
    return {normalize(v) for v in (vals | set(rows)) if v}


async def on_dnd(db: AsyncSession, ws_id: str, *addresses: str) -> bool:
    norm = {normalize(a) for a in addresses if a}
    if not norm:
        return False
    rows = (await db.execute(select(DndEntry.value).where(DndEntry.workspace_id == ws_id))).scalars().all()
    return any(normalize(r) in norm for r in rows)


async def opt_out(db: AsyncSession, ws: Workspace, contact: Contact | None, channel: str, address: str | None = None,
                  reason: str = "customer opted out") -> None:
    """Record an opt-out on every known address of the contact, immediately."""
    addrs = await _addresses(db, contact)
    if address:
        addrs.add(normalize(address))
    existing = {normalize(v) for v in (await db.execute(select(DndEntry.value).where(DndEntry.workspace_id == ws.id))).scalars()}
    for a in addrs - existing:
        db.add(DndEntry(workspace_id=ws.id, value=a, reason=reason[:120]))
    if contact:
        consent = dict(contact.consent or {})
        consent["all"] = {"status": "opted_out", "at": utcnow().isoformat(), "channel": channel, "reason": reason}
        contact.consent = consent
        contact.tags = sorted(set(contact.tags or []) | {"opted-out"})
        db.add(Activity(workspace_id=ws.id, contact_id=contact.id, type="consent.opted_out", title=f"Opted out via {channel}",
                        data={"reason": reason}, actor="system"))
    log.info(f"Opt-out recorded for {len(addrs)} address(es) in {ws.id} via {channel}")
    from .webhooks import emit

    await emit(ws.id, "contact.opted_out", {"contact_id": contact.id if contact else None, "channel": channel})


def record_consent(contact: Contact, channel: str, status: str, source: str) -> None:
    consent = dict(contact.consent or {})
    consent[channel] = {"status": status, "at": utcnow().isoformat(), "source": source}
    contact.consent = consent


def within_hours(ws: Workspace, tz: str | None = None) -> bool:
    s = settings_for(ws)
    now = datetime.now(ZoneInfo(tz or ws.settings.get("timezone", "Asia/Kolkata")))
    return s["calling_start"] <= now.strftime("%H:%M") <= s["calling_end"]


async def check_outbound(db: AsyncSession, ws: Workspace, contact: Contact | None, address: str, channel: str,
                         purpose: str = "transactional") -> tuple[bool, str]:
    """Return (allowed, reason). Call before any AI call or message the customer didn't start."""
    if await on_dnd(db, ws.id, address, *(await _addresses(db, contact))):
        return False, "on the do-not-contact list"
    consent = (contact.consent or {}) if contact else {}
    if (consent.get("all") or {}).get("status") == "opted_out" or (consent.get(channel) or {}).get("status") == "opted_out":
        return False, "customer opted out"
    s = settings_for(ws)
    if purpose == "promotional" and s["require_consent_for_promotional"]:
        if (consent.get(channel) or consent.get("marketing") or {}).get("status") != "opted_in":
            return False, "no marketing consent on record"
    if channel in {"voice", "phone"} and not within_hours(ws):
        return False, f"outside calling hours ({s['calling_start']}-{s['calling_end']})"
    return True, "ok"
