"""Outbound webhooks: HMAC-SHA256 signed, retried by the worker, logged per delivery.

Events: conversation.started, conversation.ended, message.created, call.ended, handoff.requested,
contact.created, contact.updated, deal.stage_changed, appointment.booked, analysis.completed,
campaign.completed, lead.captured.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx
from sqlalchemy import select

from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import WebhookDelivery, WebhookEndpoint

log = get_logger("webhooks")
EVENTS = ["conversation.started", "conversation.ended", "message.created", "call.ended", "handoff.requested",
          "contact.created", "contact.updated", "deal.stage_changed", "appointment.booked", "analysis.completed",
          "campaign.completed", "lead.captured", "form.submitted", "payment.received", "review.received", "contact.opted_out",
          "call.transferred", "agent.transferred", "webhook.received"]


def sign(secret: str, body: bytes, ts: str) -> str:
    return hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


async def emit(ws_id: str, event: str, data: dict) -> None:
    """Queue a delivery for every endpoint subscribed to this event. Also feeds automations."""
    async with SessionLocal() as db:
        eps = (await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == ws_id, WebhookEndpoint.enabled.is_(True)))).scalars().all()
        targets = [e for e in eps if not e.events or event in e.events or "*" in e.events]
        ids = []
        for ep in targets:
            d = WebhookDelivery(workspace_id=ws_id, endpoint_id=ep.id, event=event,
                                payload={"event": event, "workspace_id": ws_id, "created_at": utcnow().isoformat(), "data": data})
            db.add(d)
            await db.flush()
            ids.append(d.id)
        await db.commit()
    from ..worker.queue import enqueue

    for did in ids:
        await enqueue("webhook.deliver", {"delivery_id": did}, workspace_id=ws_id, max_attempts=4)
    await enqueue("automation.event", {"_ws": ws_id, "event": event, "data": data}, workspace_id=ws_id, max_attempts=1)
    from .integrations import SYNC_EVENTS

    if event in SYNC_EVENTS:
        await enqueue("integration.sync", {"_ws": ws_id, "event": event, "data": data}, workspace_id=ws_id, max_attempts=3)


async def deliver(delivery_id: str) -> dict:
    async with SessionLocal() as db:
        d = await db.get(WebhookDelivery, delivery_id)
        if not d:
            return {"skipped": True}
        ep = await db.get(WebhookEndpoint, d.endpoint_id)
        body = json.dumps(d.payload, default=str).encode()
        ts = str(int(time.time()))
        d.attempts += 1
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(ep.url, content=body, headers={
                    "content-type": "application/json", "x-unisona-event": d.event, "x-unisona-timestamp": ts,
                    "x-unisona-signature": f"sha256={sign(ep.secret, body, ts)}"})
            d.response_code = r.status_code
            d.status = "delivered" if r.status_code < 300 else "failed"
        except Exception as e:
            d.status = "failed"
            log.warning(f"Webhook to {ep.url} failed: {e}")
        await db.commit()
        if d.status != "delivered":
            raise RuntimeError(f"delivery failed ({d.response_code})")
        return {"status": d.status}
