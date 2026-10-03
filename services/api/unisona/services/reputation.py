"""Reputation management: review requests with feedback gating.

After a good interaction (booked, paid, resolved) a short message asks the customer to rate the
experience on a one-tap page. Happy customers (rating >= threshold) are sent to the business's
Google/other review page; unhappy ones leave private feedback, which creates an urgent task and
alert so the team can recover the customer before they post publicly.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import Activity, Contact, ReviewRequest, Task, Workspace

log = get_logger("reputation")
DEFAULTS = {"threshold": 4, "review_url": "", "channel": "whatsapp",
            "message": "Hi {{first_name}}, thanks for choosing {{business}}! How was your experience? Tap to rate us (takes 5 seconds): {{link}}"}


def settings_for(ws: Workspace) -> dict:
    return {**DEFAULTS, **((ws.settings or {}).get("reputation") or {})}


def public_link(token: str) -> str:
    return f"{settings.app_url.rstrip('/')}/r/{token}"


async def send_request(ws_id: str, contact_id: str, channel: str | None = None) -> dict:
    from ..channels.outbound import send_to_contact

    async with SessionLocal() as db:
        ws = await db.get(Workspace, ws_id)
        contact = await db.get(Contact, contact_id)
        if not contact or contact.workspace_id != ws_id:
            return {"error": "contact not found"}
        s = settings_for(ws)
        channel = channel or s["channel"]
        recent = (await db.execute(select(func.count()).select_from(ReviewRequest).where(
            ReviewRequest.contact_id == contact.id, ReviewRequest.sent_at > utcnow().replace(day=1)))).scalar() or 0
        if recent >= 2:
            return {"skipped": "already asked twice this month"}
        rr = ReviewRequest(workspace_id=ws.id, contact_id=contact.id, channel=channel)
        db.add(rr)
        await db.flush()
        first = (contact.name or "there").split()[0]
        text = s["message"].replace("{{first_name}}", first).replace("{{business}}", ws.branding.get("name") or ws.name).replace("{{link}}", public_link(rr.token))
        ok, detail = await send_to_contact(db, ws, None, contact, channel, text)
        rr.status = "sent" if ok else "failed"
        db.add(Activity(workspace_id=ws.id, contact_id=contact.id, type="review.requested", title=f"Review request via {channel}",
                        data={"ok": ok, "detail": detail}, actor="automation"))
        await db.commit()
        return {"id": rr.id, "sent": ok, "detail": detail, "link": public_link(rr.token)}


async def public_view(db: AsyncSession, token: str) -> dict | None:
    rr = (await db.execute(select(ReviewRequest).where(ReviewRequest.token == token))).scalar_one_or_none()
    if not rr:
        return None
    ws = await db.get(Workspace, rr.workspace_id)
    if rr.status == "sent":
        rr.status = "opened"
        await db.commit()
    s = settings_for(ws)
    return {"business": ws.branding.get("name") or ws.name, "logo": ws.branding.get("logo_url"), "color": ws.branding.get("primary_color"),
            "threshold": int(s["threshold"]), "status": rr.status, "rating": rr.rating}


async def submit(db: AsyncSession, token: str, rating: int, feedback: str = "") -> dict:
    rr = (await db.execute(select(ReviewRequest).where(ReviewRequest.token == token))).scalar_one_or_none()
    if not rr:
        return {"error": "not found"}
    ws = await db.get(Workspace, rr.workspace_id)
    s = settings_for(ws)
    rr.rating, rr.feedback, rr.responded_at = max(1, min(5, int(rating))), feedback[:4000], utcnow()
    happy = rr.rating >= int(s["threshold"])
    rr.status = "reviewed" if happy else "feedback"
    if rr.contact_id:
        db.add(Activity(workspace_id=ws.id, contact_id=rr.contact_id, type="review.received", title=f"Rated {rr.rating}/5",
                        data={"feedback": feedback[:500]}))
        if not happy:
            db.add(Task(workspace_id=ws.id, title=f"Unhappy customer rated {rr.rating}/5: call back", notes=feedback[:2000],
                        contact_id=rr.contact_id, priority="high", created_by="automation"))
    await db.commit()
    from ..brain.respond import background
    from .webhooks import emit

    # The customer gets an instant response; alerts and automations follow in the background.
    background(emit(ws.id, "review.received", {"contact_id": rr.contact_id, "rating": rr.rating, "happy": happy, "feedback": feedback[:500]}))
    if not happy:
        from .notify import notify

        background(notify(ws.id, "review", f"{rr.rating}★ feedback received", feedback[:200] or "No comment",
                          f"/app/crm/contacts/{rr.contact_id}" if rr.contact_id else "/app/reputation", urgent=True))
    return {"happy": happy, "review_url": s["review_url"] if happy else None}


async def stats(db: AsyncSession, ws_id: str) -> dict:
    rows = (await db.execute(select(ReviewRequest.status, func.count()).where(ReviewRequest.workspace_id == ws_id).group_by(ReviewRequest.status))).all()
    by = dict(rows)
    avg = (await db.execute(select(func.avg(ReviewRequest.rating)).where(ReviewRequest.workspace_id == ws_id, ReviewRequest.rating.isnot(None)))).scalar()
    sent = sum(by.values())
    responded = by.get("reviewed", 0) + by.get("feedback", 0)
    return {"sent": sent, "responded": responded, "response_rate": round(responded / sent, 3) if sent else 0,
            "avg_rating": round(float(avg), 2) if avg else None, "sent_to_review_site": by.get("reviewed", 0), "private_feedback": by.get("feedback", 0)}
