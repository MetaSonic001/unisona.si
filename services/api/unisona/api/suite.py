"""Growth suite API: forms & surveys, landing pages, reputation, payments, integrations, incoming webhooks,
WhatsApp templates, agency (client sub-accounts, white-label, blueprints, rebilling) and branding."""
from __future__ import annotations

import copy
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db, new_id, utcnow
from ..log import get_logger
from ..models import (Agent, Automation, Channel, Contact, Form, FormSubmission, IncomingHook, Integration, Member, Page, PaymentLink,
                      ReviewRequest, UsageEvent, Workspace)
from ..security.auth import AuthContext, require_auth
from ..security.crypto import new_wrapped_dek
from .common import audit, crud_router, get_scoped, to_dict

log = get_logger("suite")
router = APIRouter()


# ── Forms & surveys ──────────────────────────────────────────────────────────
router.include_router(crud_router(Form, "/forms", writable={"name", "kind", "fields", "settings", "enabled"}, required={"name"}, filters={"kind"}))


@router.get("/forms-meta")
async def forms_meta():
    from ..services.forms import FIELD_TYPES, TEMPLATES

    return {"field_types": FIELD_TYPES, "templates": TEMPLATES}


@router.post("/forms/from-template/{template_id}")
async def form_from_template(template_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.forms import TEMPLATES

    t = TEMPLATES.get(template_id)
    if not t:
        raise HTTPException(404, "Unknown template")
    f = Form(workspace_id=auth.ws, name=t["name"], kind=t["kind"], fields=copy.deepcopy(t["fields"]),
             settings={"thank_you": "Thanks! We'll be in touch shortly.", "tags": [template_id]})
    db.add(f)
    await db.commit()
    return to_dict(f)


@router.get("/forms/{form_id}/submissions")
async def form_submissions(form_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    form = await get_scoped(db, Form, form_id, auth)
    rows = (await db.execute(select(FormSubmission).where(FormSubmission.form_id == form.id).order_by(FormSubmission.created_at.desc()).limit(500))).scalars().all()
    out = {"items": [to_dict(r) for r in rows], "form": to_dict(form)}
    if form.kind == "survey":  # NPS / rating aggregates
        stats = {}
        for f in form.fields or []:
            if f.get("type") in {"nps", "rating"}:
                vals = [float(r.data.get(f["id"])) for r in rows if str(r.data.get(f["id"], "")).replace(".", "", 1).isdigit()]
                if vals:
                    entry = {"avg": round(sum(vals) / len(vals), 2), "count": len(vals)}
                    if f["type"] == "nps":
                        pro, det = sum(v >= 9 for v in vals), sum(v <= 6 for v in vals)
                        entry["nps"] = round(100 * (pro - det) / len(vals))
                    stats[f["id"]] = entry
        out["stats"] = stats
    return out


# ── Landing pages ────────────────────────────────────────────────────────────
router.include_router(crud_router(Page, "/pages", writable={"name", "blocks", "theme", "seo", "published"}, required={"name"}, order_by="updated_at"))

PAGE_PROMPT = """You design a high-converting one-page website for a small business. Return JSON:
{"seo": {"title": str, "description": str},
 "blocks": [
  {"type": "hero", "props": {"eyebrow": str, "title": str, "subtitle": str, "cta": str}},
  {"type": "features", "props": {"title": str, "items": [{"title": str, "text": str}]}},   (3-6 items)
  {"type": "text", "props": {"title": str, "body": str}},
  {"type": "testimonials", "props": {"title": str, "items": [{"quote": str, "name": str}]}},  (2-3 plausible-sounding, clearly sample)
  {"type": "faq", "props": {"title": str, "items": [{"q": str, "a": str}]}},  (4-6 from the business facts)
  {"type": "cta", "props": {"title": str, "subtitle": str, "button": str}}
 ]}
Use only facts provided. Warm, specific, benefit-led copy. No placeholders like [Name]."""


@router.post("/pages/generate")
async def generate_page(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """AI page builder: drafts a complete landing page from the business profile (+ optional brief)."""
    from ..providers.llm import get_llm

    agent = await db.get(Agent, body.get("agent_id")) if body.get("agent_id") else (
        await db.execute(select(Agent).where(Agent.workspace_id == auth.ws).limit(1))).scalars().first()
    biz = (agent.config or {}).get("business", {}) if agent else {}
    llm = await get_llm(db, auth.workspace, feature="AI page builder")
    if not llm.available:
        raise HTTPException(400, "Add an LLM key (Groq is free) to generate pages")
    facts = json.dumps({**biz, "brief": body.get("brief", ""), "goal": body.get("goal", "get enquiries and bookings")}, ensure_ascii=False)
    data = await llm.json(PAGE_PROMPT, facts, purpose="page builder")
    if isinstance(data, list):  # some models return just the block list
        data = {"blocks": data}
    blocks = [{"id": new_id("blk"), **b} for b in data.get("blocks", []) if isinstance(b, dict) and b.get("type")]
    if not blocks:
        raise HTTPException(502, "The AI returned an empty page; please try again")
    # Live sections that make the page an agent-powered funnel
    if body.get("form_id"):
        blocks.insert(2, {"id": new_id("blk"), "type": "form", "props": {"title": "Get in touch", "form_id": body["form_id"]}})
    if body.get("calendar_slug"):
        blocks.insert(-1, {"id": new_id("blk"), "type": "booking", "props": {"title": "Book an appointment", "slug": body["calendar_slug"]}})
    if agent:
        blocks.append({"id": new_id("blk"), "type": "chat", "props": {"public_key": agent.public_key}})
    page = Page(workspace_id=auth.ws, name=body.get("name") or f"{biz.get('name') or auth.workspace.name} landing page", blocks=blocks,
                seo=data.get("seo") or {}, theme={"color": (agent.config or {}).get("widget", {}).get("color", "#6D5EF8") if agent else "#6D5EF8"})
    db.add(page)
    await db.commit()
    return to_dict(page)


# ── Reputation ───────────────────────────────────────────────────────────────
@router.get("/reputation")
async def reputation_overview(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.reputation import settings_for, stats

    rows = (await db.execute(select(ReviewRequest, Contact).outerjoin(Contact, Contact.id == ReviewRequest.contact_id)
                             .where(ReviewRequest.workspace_id == auth.ws).order_by(ReviewRequest.sent_at.desc()).limit(200))).all()
    return {"settings": settings_for(auth.workspace), "stats": await stats(db, auth.ws),
            "items": [{**to_dict(r), "contact": {"id": c.id, "name": c.name, "phone": c.phone} if c else None} for r, c in rows]}


@router.patch("/reputation/settings")
async def reputation_settings(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    ws = await db.get(Workspace, auth.ws)
    allowed = {"threshold", "review_url", "channel", "message"}
    ws.settings = {**ws.settings, "reputation": {**(ws.settings.get("reputation") or {}), **{k: v for k, v in body.items() if k in allowed}}}
    await db.commit()
    return {"ok": True}


@router.post("/reputation/request")
async def reputation_request(body: dict, auth: AuthContext = Depends(require_auth)):
    from ..services.reputation import send_request

    ids = body.get("contact_ids") or ([body["contact_id"]] if body.get("contact_id") else [])
    return {"results": [await send_request(auth.ws, cid, body.get("channel")) for cid in ids[:500]]}


# ── Payments ─────────────────────────────────────────────────────────────────
@router.get("/payments")
async def payments(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.payments import provider_for

    rows = (await db.execute(select(PaymentLink, Contact).outerjoin(Contact, Contact.id == PaymentLink.contact_id)
                             .where(PaymentLink.workspace_id == auth.ws).order_by(PaymentLink.created_at.desc()).limit(300))).all()
    provider, _ = await provider_for(db, auth.workspace)
    paid = [p for p, _ in rows if p.status == "paid"]
    return {"provider": provider, "webhook_urls": {p: f"{(settings.public_webhook_url or settings.api_url).rstrip('/')}/webhooks/payments/{p}/{auth.ws}"
                                                   for p in ("razorpay", "stripe")},
            "totals": {"paid_count": len(paid), "paid_amount": round(sum(p.amount for p in paid), 2), "links": len(rows)},
            "items": [{**to_dict(p), "contact": {"id": c.id, "name": c.name} if c else None} for p, c in rows]}


@router.post("/payments/links")
async def payment_link(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.payments import create_and_send, create_link

    contact = await get_scoped(db, Contact, body["contact_id"], auth) if body.get("contact_id") else None
    try:
        if contact and body.get("channel"):
            ok, detail, link = await create_and_send(db, auth.workspace, None, contact, float(body["amount"]), body.get("description", "Payment"),
                                                     channel=body["channel"], currency=body.get("currency"))
            if not link:
                raise RuntimeError(detail)
        else:
            link = await create_link(db, auth.workspace, contact, float(body["amount"]), body.get("description", "Payment"), currency=body.get("currency"))
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    return to_dict(link)


# ── Integrations (HubSpot, Salesforce, Cal.com, Google Calendar) ─────────────
@router.get("/integrations")
async def integrations(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.integrations import CATALOG

    rows = {r.type: r for r in (await db.execute(select(Integration).where(Integration.workspace_id == auth.ws))).scalars()}
    hooks = (await db.execute(select(IncomingHook).where(IncomingHook.workspace_id == auth.ws).order_by(IncomingHook.created_at.desc()))).scalars().all()
    base = (settings.public_webhook_url or settings.api_url).rstrip("/")
    return {"catalog": [{"id": k, **v, "connected": k in rows and rows[k].status == "connected",
                         "config": rows[k].config if k in rows else {}, "error": rows[k].error if k in rows else None,
                         "last_sync_at": rows[k].last_sync_at.isoformat() if k in rows and rows[k].last_sync_at else None,
                         "available": k != "google_calendar" or bool(settings.google_oauth_client_id)} for k, v in CATALOG.items()],
            "hooks": [{**to_dict(h), "url": f"{base}/hooks/{h.token}"} for h in hooks]}


@router.post("/integrations/{type_}")
async def connect_integration(type_: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.integrations import CATALOG, set_secret, test

    auth.require("admin")
    spec = CATALOG.get(type_)
    if not spec or spec.get("oauth"):
        raise HTTPException(404, "Use the Connect button for this integration")
    secret_keys = {f["key"] for f in spec["fields"] if f.get("secret")}
    config = {f["key"]: body.get(f["key"]) for f in spec["fields"] if not f.get("secret") and body.get(f["key"])}
    secret = {k: body.get(k) for k in secret_keys if body.get(k)}
    try:
        message = await test(type_, config, secret)
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}") from e
    it = (await db.execute(select(Integration).where(Integration.workspace_id == auth.ws, Integration.type == type_))).scalar_one_or_none()
    if not it:
        it = Integration(workspace_id=auth.ws, type=type_)
        db.add(it)
        await db.flush()
    it.config, it.status, it.error = config, "connected", None
    set_secret(auth.workspace, it, secret)
    await audit(db, auth, "integration.connect", type_)
    await db.commit()
    return {"ok": True, "message": message}


@router.delete("/integrations/{type_}")
async def disconnect_integration(type_: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    it = (await db.execute(select(Integration).where(Integration.workspace_id == auth.ws, Integration.type == type_))).scalar_one_or_none()
    if it:
        await db.delete(it)
        await db.commit()
    return {"ok": True}


@router.get("/integrations/google/start")
async def google_start(auth: AuthContext = Depends(require_auth)):
    import hashlib
    import hmac

    from ..services.integrations import google_auth_url

    sig = hmac.new(settings.unisona_master_key.encode(), auth.ws.encode(), hashlib.sha256).hexdigest()[:24]
    try:
        return {"url": google_auth_url(f"{auth.ws}.{sig}")}
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


router.include_router(crud_router(IncomingHook, "/incoming-hooks", writable={"name", "action", "config"}, required={"name"}))


# ── WhatsApp templates (for broadcasts outside the 24h window) ───────────────
@router.get("/whatsapp/{channel_id}/templates")
async def wa_templates(channel_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..channels.common import channel_secret
    from ..channels.whatsapp import list_templates

    ch = await get_scoped(db, Channel, channel_id, auth)
    try:
        return {"items": await list_templates(ch.config, channel_secret(auth.workspace, ch).get("access_token", ""))}
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/whatsapp/{channel_id}/templates")
async def wa_template_create(channel_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..channels.common import channel_secret
    from ..channels.whatsapp import create_template

    ch = await get_scoped(db, Channel, channel_id, auth)
    try:
        return await create_template(ch.config, channel_secret(auth.workspace, ch).get("access_token", ""), body["name"].lower().replace(" ", "_"),
                                     body.get("language", "en"), body.get("category", "UTILITY"), body["body"], body.get("example"))
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e


# ── Branding (white-label) ───────────────────────────────────────────────────
BRAND_FIELDS = {"name", "logo_url", "primary_color", "hide_powered_by", "support_email", "custom_domain", "favicon_url"}


@router.get("/workspace/branding")
async def get_branding(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    ws = await db.get(Workspace, auth.ws)
    agency = await db.get(Workspace, ws.parent_id) if ws.parent_id else None
    return {"branding": ws.branding or {}, "inherited": (agency.branding or {}) if agency else {}, "plan": ws.plan}


@router.patch("/workspace/branding")
async def set_branding(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    ws = await db.get(Workspace, auth.ws)
    if body.get("hide_powered_by") and ws.plan in {"free", "starter"} and not settings.is_dev:
        raise HTTPException(402, "Removing 'Powered by' needs the Growth plan or higher")
    ws.branding = {**(ws.branding or {}), **{k: v for k, v in body.items() if k in BRAND_FIELDS}}
    await audit(db, auth, "branding.update", ws.id, body)
    await db.commit()
    return {"branding": ws.branding}


# ── Agency: client sub-accounts, blueprints, rebilling ───────────────────────
def _agency_ws(auth: AuthContext) -> str:
    """Agency actions always run from the agency workspace itself (not while inside a client)."""
    if auth.via.startswith("agency:"):
        raise HTTPException(400, "Switch back to your agency workspace first")
    return auth.ws


async def _usage(db: AsyncSession, ws_id: str) -> dict:
    since = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mins = (await db.execute(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
        UsageEvent.workspace_id == ws_id, UsageEvent.kind == "voice_minute", UsageEvent.created_at >= since))).scalar()
    cost = (await db.execute(select(func.coalesce(func.sum(UsageEvent.cost_usd), 0)).where(
        UsageEvent.workspace_id == ws_id, UsageEvent.created_at >= since))).scalar()
    convs = (await db.execute(select(func.count()).select_from(UsageEvent).where(
        UsageEvent.workspace_id == ws_id, UsageEvent.kind == "llm", UsageEvent.created_at >= since))).scalar()
    return {"voice_minutes": round(float(mins), 1), "ai_calls": convs, "provider_cost_usd": round(float(cost), 4)}


@router.get("/agency")
async def agency(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.billing import PLAN_BY_ID

    ws_id = _agency_ws(auth)
    ws = await db.get(Workspace, ws_id)
    clients = (await db.execute(select(Workspace).where(Workspace.parent_id == ws_id).order_by(Workspace.created_at))).scalars().all()
    rebill = (ws.settings or {}).get("rebilling") or {}
    items = []
    for c in clients:
        u = await _usage(db, c.id)
        price = (c.settings or {}).get("client_price") or {}
        markup = float(price.get("markup_pct", rebill.get("default_markup_pct", 30)))
        agents = (await db.execute(select(func.count()).select_from(Agent).where(Agent.workspace_id == c.id))).scalar()
        items.append({"id": c.id, "name": c.name, "plan": c.plan, "created_at": c.created_at.isoformat(), "agents": agents, "usage": u,
                      "branding": c.branding or {}, "pricing": price,
                      "rebill": {"base_fee": float(price.get("monthly_fee", rebill.get("default_monthly_fee", 0))),
                                 "voice_rate": float(price.get("voice_minute_rate", rebill.get("default_voice_minute_rate", 5))),
                                 "usage_charge": round(u["voice_minutes"] * float(price.get("voice_minute_rate", rebill.get("default_voice_minute_rate", 5))), 2),
                                 "ai_cost_with_markup_usd": round(u["provider_cost_usd"] * (1 + markup / 100), 4)}})
    plan = PLAN_BY_ID.get(ws.plan, PLAN_BY_ID["free"])
    return {"enabled": bool((ws.settings or {}).get("agency")), "is_client": bool(ws.parent_id), "limit": plan["sub_accounts"] if not settings.is_dev else 1000,
            "rebilling": {"currency": rebill.get("currency", ws.settings.get("currency", "INR")), "default_markup_pct": rebill.get("default_markup_pct", 30),
                          "default_monthly_fee": rebill.get("default_monthly_fee", 0), "default_voice_minute_rate": rebill.get("default_voice_minute_rate", 5)},
            "clients": items}


@router.post("/agency/enable")
async def agency_enable(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    ws = await db.get(Workspace, _agency_ws(auth))
    if ws.parent_id:
        raise HTTPException(400, "A client sub-account can't be an agency")
    ws.settings = {**ws.settings, "agency": True, "rebilling": {**(ws.settings.get("rebilling") or {}), **(body.get("rebilling") or {})}}
    await db.commit()
    return {"ok": True}


@router.post("/agency/clients")
async def agency_create_client(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.billing import PLAN_BY_ID

    auth.require("admin")
    ws = await db.get(Workspace, _agency_ws(auth))
    count = (await db.execute(select(func.count()).select_from(Workspace).where(Workspace.parent_id == ws.id))).scalar()
    limit = PLAN_BY_ID.get(ws.plan, PLAN_BY_ID["free"])["sub_accounts"]
    if count >= limit and not settings.is_dev:
        raise HTTPException(402, f"Your {ws.plan} plan includes {limit} client sub-account(s). Upgrade to Agency for unlimited.")
    cid = new_id("ws")
    name = (body.get("name") or "New client").strip()[:200]
    client = Workspace(id=cid, clerk_org_id=f"client_{cid}", name=name, slug="".join(ch if ch.isalnum() else "-" for ch in name.lower())[:60],
                       plan=body.get("plan") or ws.plan, parent_id=ws.id,
                       settings={"dek": new_wrapped_dek(cid), "timezone": body.get("timezone") or ws.settings.get("timezone", "Asia/Kolkata"),
                                 "currency": ws.settings.get("currency", "INR"), "client_price": body.get("pricing") or {}},
                       branding={**(ws.branding or {}), **(body.get("branding") or {})})
    db.add(client)
    await db.flush()
    db.add(Member(workspace_id=cid, user_id=auth.user_id, email=auth.email, name=auth.name, role="owner"))
    from ..services.bootstrap import seed_workspace

    await seed_workspace(db, client)
    if not (ws.settings or {}).get("agency"):
        ws.settings = {**ws.settings, "agency": True}
    await audit(db, auth, "agency.client_created", cid, {"name": name})
    await db.commit()
    if body.get("blueprint_agent_ids") or body.get("blueprint_automation_ids") or body.get("blueprint_form_ids"):
        await _apply_blueprint(db, ws.id, cid, body)
    return {"id": cid, "name": name}


@router.patch("/agency/clients/{client_id}")
async def agency_update_client(client_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    client = await db.get(Workspace, client_id)
    if not client or client.parent_id != _agency_ws(auth):
        raise HTTPException(404, "Client not found")
    if body.get("name"):
        client.name = body["name"][:200]
    if "pricing" in body:
        client.settings = {**client.settings, "client_price": body["pricing"]}
    if "branding" in body:
        client.branding = {**(client.branding or {}), **{k: v for k, v in body["branding"].items() if k in BRAND_FIELDS}}
    if body.get("plan"):
        client.plan = body["plan"]
    await db.commit()
    return {"ok": True}


@router.patch("/agency/rebilling")
async def agency_rebilling(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    ws = await db.get(Workspace, _agency_ws(auth))
    ws.settings = {**ws.settings, "rebilling": {**(ws.settings.get("rebilling") or {}), **body}}
    await db.commit()
    return {"ok": True}


async def _apply_blueprint(db: AsyncSession, from_ws: str, to_ws: str, body: dict) -> dict:
    """Blueprints (GoHighLevel 'snapshots'): copy proven agents, automations and forms into a client account."""
    copied = {"agents": 0, "automations": 0, "forms": 0}
    for aid in body.get("blueprint_agent_ids") or []:
        a = await db.get(Agent, aid)
        if a and a.workspace_id == from_ws:
            cfg = copy.deepcopy(a.config)
            cfg.setdefault("knowledge", {})["kb_ids"] = []  # knowledge is per client; they upload their own
            cfg["squad"] = {"members": []}
            db.add(Agent(workspace_id=to_ws, name=a.name, description=a.description, template_id=a.template_id, config=cfg, status="draft"))
            copied["agents"] += 1
    for aid in body.get("blueprint_automation_ids") or []:
        a = await db.get(Automation, aid)
        if a and a.workspace_id == from_ws:
            db.add(Automation(workspace_id=to_ws, name=a.name, trigger=copy.deepcopy(a.trigger), steps=copy.deepcopy(a.steps), enabled=False))
            copied["automations"] += 1
    for fid in body.get("blueprint_form_ids") or []:
        f = await db.get(Form, fid)
        if f and f.workspace_id == from_ws:
            db.add(Form(workspace_id=to_ws, name=f.name, kind=f.kind, fields=copy.deepcopy(f.fields), settings=copy.deepcopy(f.settings)))
            copied["forms"] += 1
    await db.commit()
    return copied


@router.post("/agency/clients/{client_id}/blueprint")
async def agency_blueprint(client_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    client = await db.get(Workspace, client_id)
    agency_id = _agency_ws(auth)
    if not client or client.parent_id != agency_id:
        raise HTTPException(404, "Client not found")
    return await _apply_blueprint(db, agency_id, client_id, body)


@router.get("/agency/report")
async def agency_report(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Monthly rebilling statement across all clients (CSV-friendly)."""
    data = await agency(auth, db)
    rows = [{"client": c["name"], "voice_minutes": c["usage"]["voice_minutes"], "base_fee": c["rebill"]["base_fee"],
             "usage_charge": c["rebill"]["usage_charge"], "total": round(c["rebill"]["base_fee"] + c["rebill"]["usage_charge"], 2)}
            for c in data["clients"]]
    return {"currency": data["rebilling"]["currency"], "rows": rows, "grand_total": round(sum(r["total"] for r in rows), 2),
            "period": utcnow().strftime("%B %Y"), "generated_at": utcnow().isoformat(), "expires": (utcnow() + timedelta(days=1)).isoformat()}


@router.get("/workspaces/accessible")
async def accessible(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Workspace switcher: the user's own workspace plus (for agency admins) every client sub-account."""
    home_id = auth.claims.get("agency_ws") or auth.ws
    home = await db.get(Workspace, home_id)
    clients = (await db.execute(select(Workspace).where(Workspace.parent_id == home_id).order_by(Workspace.name))).scalars().all()
    return {"home": {"id": home.id, "name": home.name, "agency": bool((home.settings or {}).get("agency"))},
            "clients": [{"id": c.id, "name": c.name, "logo_url": (c.branding or {}).get("logo_url")} for c in clients],
            "current": auth.ws}


@router.get("/integrations/google/connected")
async def google_connected_redirect():
    return RedirectResponse(f"{settings.app_url}/app/integrations?google=connected")
