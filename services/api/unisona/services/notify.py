"""Notifications: in-app (realtime + bell), Slack, email. Missing keys are skipped with a log."""
from __future__ import annotations

import asyncio

import httpx

from ..config import settings
from ..db import SessionLocal
from ..log import feature_unavailable, get_logger
from ..models import Member, Notification
from ..realtime import hub

log = get_logger("notify")


async def notify(ws_id: str, type_: str, title: str, body: str = "", link: str | None = None, *, urgent: bool = False,
                 email_roles: tuple[str, ...] = ("owner", "admin", "agent")) -> None:
    async with SessionLocal() as db:
        n = Notification(workspace_id=ws_id, type=type_, title=title, body=body, link=link)
        db.add(n)
        await db.commit()
        payload = {"type": "notification", "notification": {"id": n.id, "type": type_, "title": title, "body": body,
                                                            "link": link, "urgent": urgent, "created_at": n.created_at.isoformat()}}
        emails: list[str] = []
        if urgent:
            from sqlalchemy import select

            emails = [m.email for m in (await db.execute(select(Member).where(Member.workspace_id == ws_id, Member.role.in_(email_roles)))).scalars() if m.email]
    await hub.publish(ws_id, payload)
    if urgent:
        asyncio.create_task(_slack(title, body, link))
        asyncio.create_task(_email(emails, title, body, link))


async def _slack(title: str, body: str, link: str | None) -> None:
    if not settings.slack_alert_webhook_url:
        feature_unavailable("Slack handoff alerts", "SLACK_ALERT_WEBHOOK_URL")
        return
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            await c.post(settings.slack_alert_webhook_url, json={"text": f"*{title}*\n{body}\n{settings.app_url}{link or ''}"})
    except Exception as e:
        log.warning(f"Slack alert failed: {e}")


async def _email(to: list[str], title: str, body: str, link: str | None) -> None:
    if not to:
        return
    if not (settings.resend_api_key and settings.alert_from_email):
        feature_unavailable("Email handoff alerts", "RESEND_API_KEY + ALERT_FROM_EMAIL")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                         json={"from": settings.alert_from_email, "to": to[:20], "subject": title,
                               "html": f"<p>{body}</p><p><a href='{settings.app_url}{link or ''}'>Open in Unisona</a></p>"})
    except Exception as e:
        log.warning(f"Email alert failed: {e}")
