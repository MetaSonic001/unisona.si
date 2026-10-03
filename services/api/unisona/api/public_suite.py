"""Public (unauthenticated) endpoints for the growth suite: hosted forms, landing pages, review pages,
unsubscribe links, payment/Meta webhooks, incoming automation hooks and the Google OAuth callback.
Every write is rate-limited and scoped by an unguessable slug/token."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db, utcnow
from ..log import get_logger
from ..models import Agent, Contact, Form, IncomingHook, Integration, Page, Workspace
from ..security import ratelimit

log = get_logger("public")
router = APIRouter()


def _brand(ws: Workspace) -> dict:
    b = ws.branding or {}
    return {"name": b.get("name") or ws.name, "logo_url": b.get("logo_url"), "primary_color": b.get("primary_color"),
            "hide_powered_by": bool(b.get("hide_powered_by"))}


# ── Forms ────────────────────────────────────────────────────────────────────
@router.get("/public/forms/{slug}")
async def public_form(slug: str, db: AsyncSession = Depends(get_db)):
    form = (await db.execute(select(Form).where(Form.slug == slug, Form.enabled.is_(True)))).scalar_one_or_none()
    if not form:
        raise HTTPException(404, "Form not found")
    ws = await db.get(Workspace, form.workspace_id)
    return {"name": form.name, "kind": form.kind, "fields": form.fields, "thank_you": (form.settings or {}).get("thank_you"),
            "redirect_url": (form.settings or {}).get("redirect_url"), "brand": _brand(ws)}


@router.post("/public/forms/{slug}")
async def public_form_submit(slug: str, body: dict, request: Request, db: AsyncSession = Depends(get_db)):
    from ..services.forms import submit, validate

    ratelimit.check(f"form:{request.client.host if request.client else '?'}", 10, 60)
    form = (await db.execute(select(Form).where(Form.slug == slug, Form.enabled.is_(True)))).scalar_one_or_none()
    if not form:
        raise HTTPException(404, "Form not found")
    if body.get("_hp"):  # honeypot field: bots fill it, humans never see it
        return {"ok": True}
    data = {k: v for k, v in (body.get("data") or {}).items() if isinstance(k, str) and len(str(v)) < 5000}
    errors = validate(form, data)
    if errors:
        raise HTTPException(422, "; ".join(errors))
    sub = await submit(db, form, data, {"ip": request.client.host if request.client else None, "ua": request.headers.get("user-agent", "")[:200],
                                        "referrer": request.headers.get("referer")})
    return {"ok": True, "id": sub.id, "thank_you": (form.settings or {}).get("thank_you"), "redirect_url": (form.settings or {}).get("redirect_url")}


# ── Landing pages ────────────────────────────────────────────────────────────
@router.get("/public/pages/{slug}")
async def public_page(slug: str, db: AsyncSession = Depends(get_db)):
    page = (await db.execute(select(Page).where(Page.slug == slug, Page.published.is_(True)))).scalar_one_or_none()
    if not page:
        raise HTTPException(404, "Page not found")
    page.views = (page.views or 0) + 1
    await db.commit()
    ws = await db.get(Workspace, page.workspace_id)
    forms = {}
    for b in page.blocks or []:
        if b.get("type") == "form" and b.get("props", {}).get("form_id"):
            f = await db.get(Form, b["props"]["form_id"])
            if f and f.workspace_id == ws.id:
                forms[f.id] = f.slug
    return {"name": page.name, "blocks": page.blocks, "theme": page.theme, "seo": page.seo, "brand": _brand(ws), "form_slugs": forms}


# ── Reviews ──────────────────────────────────────────────────────────────────
@router.get("/public/reviews/{token}")
async def public_review(token: str, db: AsyncSession = Depends(get_db)):
    from ..services.reputation import public_view

    data = await public_view(db, token)
    if not data:
        raise HTTPException(404, "Link expired")
    return data


@router.post("/public/reviews/{token}")
async def public_review_submit(token: str, body: dict, request: Request, db: AsyncSession = Depends(get_db)):
    from ..services.reputation import submit

    ratelimit.check(f"review:{request.client.host if request.client else '?'}", 10, 60)
    return await submit(db, token, int(body.get("rating", 0)), str(body.get("feedback", "")))


# ── Unsubscribe ──────────────────────────────────────────────────────────────
@router.post("/public/unsubscribe/{token}")
async def unsubscribe(token: str, db: AsyncSession = Depends(get_db)):
    from ..channels.outbound import unsubscribe_token
    from ..services.compliance import opt_out

    contact_id = token.partition(".")[0]
    contact = await db.get(Contact, contact_id)
    if not contact or not hmac.compare_digest(unsubscribe_token(contact.workspace_id, contact.id), token):
        raise HTTPException(404, "Invalid link")
    ws = await db.get(Workspace, contact.workspace_id)
    await opt_out(db, ws, contact, "email", contact.email, "unsubscribe link")
    await db.commit()
    return {"ok": True, "business": _brand(ws)["name"]}


# ── Payment webhooks (the business's own Razorpay/Stripe) ────────────────────
@router.post("/webhooks/payments/{provider}/{ws_id}")
async def payments_webhook(provider: str, ws_id: str, request: Request):
    from ..services.payments import handle_webhook

    if provider not in {"razorpay", "stripe"}:
        raise HTTPException(404)
    ok = await handle_webhook(provider, ws_id, await request.body(), {k.lower(): v for k, v in request.headers.items()})
    if not ok:
        raise HTTPException(400, "Invalid signature")
    return {"ok": True}


# ── Meta: Instagram + Messenger (+ WhatsApp) on one callback URL ─────────────
@router.get("/webhooks/meta")
async def meta_verify(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and settings.meta_webhook_verify_token and p.get("hub.verify_token") == settings.meta_webhook_verify_token:
        return PlainTextResponse(p.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/meta")
async def meta_inbound(request: Request):
    from ..channels import meta_messaging, whatsapp

    body = await request.body()
    if not whatsapp.verify_signature(body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(401, "Bad signature")
    payload = await request.json()
    if payload.get("object") == "whatsapp_business_account":
        return {"accepted": await whatsapp.handle_webhook(payload)}
    return {"accepted": await meta_messaging.handle_webhook(payload)}


# ── Incoming webhooks: Zapier / Make / n8n / any app → contacts, calls, events ──
_FIELD_ALIASES = {"name": ["name", "full_name", "fullname", "first_name", "contact_name"], "phone": ["phone", "phone_number", "mobile", "whatsapp", "number"],
                  "email": ["email", "email_address", "mail"]}


def _pick(payload: dict, key: str, mapping: dict) -> str | None:
    if mapping.get(key):
        cur = payload
        for part in str(mapping[key]).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return str(cur) if cur not in (None, "") else None
    for alias in _FIELD_ALIASES[key]:
        if payload.get(alias):
            return str(payload[alias])
    return None


@router.post("/hooks/{token}")
async def incoming_hook(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    from ..brain.identity import resolve_contact
    from ..services.webhooks import emit

    ratelimit.check(f"hook:{token}", 120, 60)
    hook = (await db.execute(select(IncomingHook).where(IncomingHook.token == token))).scalar_one_or_none()
    if not hook:
        raise HTTPException(404, "Unknown hook")
    try:
        payload = await request.json()
    except Exception:
        payload = dict(await request.form())
    if not isinstance(payload, dict):
        payload = {"data": payload}
    ws = await db.get(Workspace, hook.workspace_id)
    cfg = hook.config or {}
    mapping = cfg.get("mapping") or {}
    name, phone, email = _pick(payload, "name", mapping), _pick(payload, "phone", mapping), _pick(payload, "email", mapping)
    contact = None
    if phone or email:
        contact = await resolve_contact(db, ws.id, {k: v for k, v in {"phone": phone, "email": email}.items() if v}, name=name, channel="api")
        if cfg.get("tags"):
            contact.tags = sorted(set(contact.tags or []) | set(cfg["tags"]))
    hook.calls, hook.last_payload = (hook.calls or 0) + 1, {k: payload[k] for k in list(payload)[:40]}
    await db.commit()
    result = {"ok": True, "contact_id": contact.id if contact else None}
    if hook.action == "start_call" and contact and contact.phone:
        from ..channels.telephony import dial
        from ..models import Channel

        ch = (await db.execute(select(Channel).where(Channel.workspace_id == ws.id, Channel.type == "phone", Channel.enabled.is_(True),
                                                     *( [Channel.agent_id == cfg["agent_id"]] if cfg.get("agent_id") else [])))).scalars().first()
        try:
            if not ch:
                raise RuntimeError("no phone channel connected")
            await dial(ws, ch, contact.phone, variables={k: str(v) for k, v in payload.items() if isinstance(v, (str, int, float))})
            result["call"] = "started"
        except Exception as e:
            result["call"] = f"not started: {e}"
    elif hook.action == "send_message" and contact:
        from ..channels.outbound import send_to_contact

        agent = await db.get(Agent, cfg.get("agent_id")) if cfg.get("agent_id") else None
        text = (cfg.get("message") or "Hi {{first_name}}, thanks for your interest!").replace("{{first_name}}", (contact.name or "there").split()[0])
        ok, detail = await send_to_contact(db, ws, agent, contact, cfg.get("channel", "whatsapp"), text)
        result["message"] = detail
    await emit(ws.id, "webhook.received", {"hook": hook.name, "contact_id": result["contact_id"], "payload": hook.last_payload})
    return result


# ── Google Calendar OAuth callback ───────────────────────────────────────────
@router.get("/integrations/google/callback")
async def google_callback(code: str = "", state: str = "", error: str = "", db: AsyncSession = Depends(get_db)):
    from ..services.integrations import google_exchange, set_secret

    if error:
        return RedirectResponse(f"{settings.app_url}/app/integrations?google=error")
    ws_id, _, sig = state.partition(".")
    expected = hmac.new(settings.unisona_master_key.encode(), ws_id.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(400, "Invalid state")
    ws = await db.get(Workspace, ws_id)
    tokens = await google_exchange(code)
    it = (await db.execute(select(Integration).where(Integration.workspace_id == ws_id, Integration.type == "google_calendar"))).scalar_one_or_none()
    if not it:
        it = Integration(workspace_id=ws_id, type="google_calendar")
        db.add(it)
        await db.flush()
    it.config, it.status, it.error, it.last_sync_at = {"calendar_id": "primary"}, "connected", None, utcnow()
    set_secret(ws, it, {"refresh_token": tokens.get("refresh_token", "")})
    await db.commit()
    return RedirectResponse(f"{settings.app_url}/app/integrations?google=connected")
