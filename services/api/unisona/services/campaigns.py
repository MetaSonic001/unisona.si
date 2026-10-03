"""Outbound campaigns: batch AI calls and message broadcasts.

Guardrails (Bolna-style "calling guardrails", TRAI-friendly): calling window in the
recipient timezone, allowed weekdays, DND list, max attempts with retry delay, and a
concurrency cap. Each tick moves due targets forward.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import Agent, Campaign, CampaignTarget, Channel, Contact, DndEntry, Workspace

log = get_logger("campaigns")
DEFAULTS = {"window_start": "09:30", "window_end": "20:30", "timezone": "Asia/Kolkata", "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
            "concurrency": 3, "max_attempts": 2, "retry_minutes": 60, "message": "", "ai_personalize": False,
            "purpose": "transactional", "subject": "", "template_name": "", "template_language": "en"}
IDENTITY_FOR = {"telegram": "telegram_id", "whatsapp": "wa_id", "whatsapp_template": "wa_id", "sms": "phone", "email": "email",
                "instagram": "instagram_id", "messenger": "messenger_id"}


def in_window(s: dict) -> bool:
    tz = ZoneInfo(s.get("timezone") or "Asia/Kolkata")
    now = datetime.now(tz)
    if ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][now.weekday()] not in (s.get("days") or DEFAULTS["days"]):
        return False
    a, b = s.get("window_start", "09:30"), s.get("window_end", "20:30")
    return a <= now.strftime("%H:%M") <= b


async def tick() -> int:
    moved = 0
    async with SessionLocal() as db:
        camps = (await db.execute(select(Campaign).where(Campaign.status.in_(["running", "scheduled"])))).scalars().all()
        for c in camps:
            if c.status == "scheduled":
                if c.scheduled_at and c.scheduled_at > utcnow():
                    continue
                c.status = "running"
            s = {**DEFAULTS, **(c.settings or {})}
            if c.type == "voice" and not in_window(s):
                continue
            in_progress = (await db.execute(select(func.count()).select_from(CampaignTarget).where(
                CampaignTarget.campaign_id == c.id, CampaignTarget.status == "in_progress"))).scalar() or 0
            slots = max(0, int(s["concurrency"]) - (in_progress if c.type == "voice" else 0))
            due = (await db.execute(select(CampaignTarget).where(
                CampaignTarget.campaign_id == c.id, CampaignTarget.status == "queued",
                (CampaignTarget.next_attempt_at.is_(None)) | (CampaignTarget.next_attempt_at <= utcnow())).limit(slots or 0))).scalars().all()
            for t in due:
                moved += await _attempt(db, c, t, s)
            remaining = (await db.execute(select(func.count()).select_from(CampaignTarget).where(
                CampaignTarget.campaign_id == c.id, CampaignTarget.status.in_(["queued", "in_progress"])))).scalar() or 0
            stats = dict((await db.execute(select(CampaignTarget.status, func.count()).where(CampaignTarget.campaign_id == c.id)
                                           .group_by(CampaignTarget.status))).all())
            c.stats = {**stats, "total": sum(stats.values())}
            if remaining == 0 and c.status == "running":
                c.status = "completed"
                from .webhooks import emit

                await emit(c.workspace_id, "campaign.completed", {"campaign_id": c.id, "stats": c.stats})
                log.info(f"Campaign {c.name} completed: {c.stats}")
        await db.commit()
    return moved


async def _attempt(db, c: Campaign, t: CampaignTarget, s: dict) -> int:
    ws = await db.get(Workspace, c.workspace_id)
    dnd = (await db.execute(select(DndEntry).where(DndEntry.workspace_id == ws.id, DndEntry.value == t.address))).scalar_one_or_none()
    if dnd:
        t.status, t.result = "skipped", {"reason": "dnd"}
        return 1
    t.attempts += 1
    try:
        if c.type == "voice":
            ch = (await db.execute(select(Channel).where(Channel.workspace_id == ws.id, Channel.type == "phone", Channel.enabled.is_(True)))).scalars().first()
            if not ch:
                raise RuntimeError("No phone channel connected")
            from ..channels.telephony import dial

            await dial(ws, ch, t.address, target_id=t.id, variables=t.variables, purpose=s.get("purpose", "transactional"))
            t.status = "in_progress"
        else:
            from ..channels.outbound import send_to_contact

            contact = await db.get(Contact, t.contact_id) if t.contact_id else None
            if not contact:
                from ..brain.identity import resolve_contact

                key = IDENTITY_FOR.get(c.type, "phone")
                contact = await resolve_contact(db, ws.id, {key: t.address}, name=t.variables.get("name"),
                                                channel=c.type.replace("_template", ""))
                t.contact_id = contact.id
            text = s.get("message", "")
            for k, v in {"first_name": (contact.name or "there").split()[0], "name": contact.name or "there", **(t.variables or {})}.items():
                text = text.replace("{{" + k + "}}", str(v))
            agent = await db.get(Agent, c.agent_id)
            subject = s.get("subject") or None
            if c.type == "whatsapp_template":
                subject = f"{s.get('template_name')}|{s.get('template_language') or 'en'}"
            ok, detail = await send_to_contact(db, ws, agent, contact, c.type, text, subject=subject, purpose=s.get("purpose", "transactional"))
            if not ok and detail.startswith("blocked:"):
                t.status, t.result = "skipped", {"reason": detail}
                return 1
            if not ok:
                raise RuntimeError(detail)
            t.status, t.result = "done", {"sent": True}
    except Exception as e:
        if t.attempts >= int(s["max_attempts"]):
            t.status, t.result = "failed", {"error": str(e)[:300]}
        else:
            t.status, t.next_attempt_at = "queued", utcnow() + timedelta(minutes=float(s["retry_minutes"]))
            t.result = {"last_error": str(e)[:300]}
    return 1
