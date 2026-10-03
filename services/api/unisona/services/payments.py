"""Customer payments: the business's own Razorpay (India, UPI) or Stripe (global) account (BYOK).

Agents and automations create a hosted payment link and send it on WhatsApp / SMS / email. The
provider's webhook marks it paid, which fires the `payment.received` automation trigger and logs it
on the contact timeline. Card details never touch Unisona or the AI.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal, utcnow
from ..log import feature_unavailable, get_logger
from ..models import Activity, Agent, Contact, PaymentLink, Workspace
from ..providers.keys import resolve

log = get_logger("payments")


async def provider_for(db: AsyncSession, ws: Workspace) -> tuple[str, object] | tuple[None, None]:
    preferred = (ws.settings or {}).get("payments_provider")
    order = [preferred] if preferred else []
    order += [p for p in ("razorpay", "stripe") if p not in order]
    for p in order:
        key = await resolve(db, ws, p, feature="customer payments")
        if key.api_key:
            return p, key
    return None, None


async def create_link(db: AsyncSession, ws: Workspace, contact: Contact | None, amount: float, description: str, *,
                      currency: str | None = None, conversation_id: str | None = None) -> PaymentLink:
    provider, key = await provider_for(db, ws)
    if not provider:
        feature_unavailable("Payment links", "a Razorpay or Stripe key in Settings → AI providers / Payments")
        raise RuntimeError("No payment provider connected (add Razorpay or Stripe in Integrations)")
    currency = (currency or ws.settings.get("currency") or ("INR" if provider == "razorpay" else "USD")).upper()
    link = PaymentLink(workspace_id=ws.id, contact_id=contact.id if contact else None, conversation_id=conversation_id, provider=provider,
                       amount=round(float(amount), 2), currency=currency, description=description[:300])
    db.add(link)
    await db.flush()
    minor = int(round(float(amount) * 100))
    async with httpx.AsyncClient(timeout=20) as c:
        if provider == "razorpay":
            key_id, _, secret = (key.api_key or "").partition(":")
            customer = {k: v for k, v in {"name": contact.name if contact else None, "contact": contact.phone if contact else None,
                                          "email": contact.email if contact else None}.items() if v}
            r = await c.post("https://api.razorpay.com/v1/payment_links", auth=(key_id, secret), json={
                "amount": minor, "currency": currency, "description": description[:2048], "reference_id": link.id,
                "customer": customer, "notify": {"sms": False, "email": False}, "reminder_enable": True, "notes": {"unisona_link": link.id}})
            if r.status_code >= 300:
                raise RuntimeError(f"Razorpay error ({r.status_code}): {r.text[:200]}")
            body = r.json()
            link.url, link.provider_ref = body.get("short_url", ""), body.get("id", "")
        else:
            auth = (key.api_key or "", "")
            price = await c.post("https://api.stripe.com/v1/prices", auth=auth, data={
                "currency": currency.lower(), "unit_amount": minor, "product_data[name]": description[:250] or f"Payment to {ws.name}"})
            if price.status_code >= 300:
                raise RuntimeError(f"Stripe error ({price.status_code}): {price.text[:200]}")
            r = await c.post("https://api.stripe.com/v1/payment_links", auth=auth, data={
                "line_items[0][price]": price.json()["id"], "line_items[0][quantity]": 1, "metadata[unisona_link]": link.id})
            if r.status_code >= 300:
                raise RuntimeError(f"Stripe error ({r.status_code}): {r.text[:200]}")
            body = r.json()
            link.url, link.provider_ref = body.get("url", ""), body.get("id", "")
    if contact:
        db.add(Activity(workspace_id=ws.id, contact_id=contact.id, type="payment.link_created",
                        title=f"Payment link {currency} {amount:,.2f}: {description[:80]}", data={"url": link.url, "link_id": link.id}))
    await db.commit()
    return link


async def create_and_send(db: AsyncSession, ws: Workspace, agent: Agent | None, contact: Contact, amount: float, description: str, *,
                          channel: str = "whatsapp", currency: str | None = None, conversation_id: str | None = None) -> tuple[bool, str, PaymentLink | None]:
    try:
        link = await create_link(db, ws, contact, amount, description, currency=currency, conversation_id=conversation_id)
    except Exception as e:
        return False, str(e), None
    from ..channels.outbound import send_to_contact

    text = f"Here is your secure payment link for {description} ({link.currency} {link.amount:,.2f}):\n{link.url}"
    ok, detail = await send_to_contact(db, ws, agent, contact, channel, text)
    link.status = "sent" if ok else "created"
    await db.commit()
    return ok, detail, link


async def mark_paid(provider: str, ref: str | None, link_id: str | None, raw: dict) -> PaymentLink | None:
    async with SessionLocal() as db:
        link = await db.get(PaymentLink, link_id) if link_id else None
        if not link and ref:
            link = (await db.execute(select(PaymentLink).where(PaymentLink.provider_ref == ref))).scalars().first()
        if not link or link.status == "paid":
            return link
        link.status, link.paid_at = "paid", utcnow()
        if link.contact_id:
            db.add(Activity(workspace_id=link.workspace_id, contact_id=link.contact_id, type="payment.received",
                            title=f"Paid {link.currency} {link.amount:,.2f}: {link.description[:80]}", data={"provider": provider}))
        await db.commit()
        from .notify import notify
        from .webhooks import emit

        await emit(link.workspace_id, "payment.received", {"payment_link_id": link.id, "contact_id": link.contact_id, "amount": link.amount,
                                                           "currency": link.currency, "conversation_id": link.conversation_id})
        await notify(link.workspace_id, "payment", f"Payment received: {link.currency} {link.amount:,.2f}", link.description,
                     f"/app/crm/contacts/{link.contact_id}" if link.contact_id else "/app/payments")
        log.info(f"Payment {link.id} marked paid via {provider}")
        return link


def verify_razorpay(body: bytes, signature: str | None, secret: str) -> bool:
    if not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def verify_stripe(body: bytes, header: str | None, secret: str) -> bool:
    if not secret or not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    signed = f"{parts.get('t', '')}.{body.decode()}".encode()
    return hmac.compare_digest(hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest(), parts.get("v1", ""))


async def handle_webhook(provider: str, ws_id: str, body: bytes, headers: dict) -> bool:
    async with SessionLocal() as db:
        ws = await db.get(Workspace, ws_id)
        if not ws:
            return False
        key = await resolve(db, ws, provider)
    secret = ((key.extra or {}).get("webhook_secret") if key else "") or ""
    event = json.loads(body or b"{}")
    if provider == "razorpay":
        if secret and not verify_razorpay(body, headers.get("x-razorpay-signature"), secret):
            return False
        if event.get("event") == "payment_link.paid":
            ent = ((event.get("payload") or {}).get("payment_link") or {}).get("entity") or {}
            await mark_paid("razorpay", ent.get("id"), ent.get("reference_id"), event)
    elif provider == "stripe":
        if secret and not verify_stripe(body, headers.get("stripe-signature"), secret):
            return False
        if event.get("type") == "checkout.session.completed":
            obj = (event.get("data") or {}).get("object") or {}
            await mark_paid("stripe", obj.get("payment_link"), (obj.get("metadata") or {}).get("unisona_link"), event)
    return True
