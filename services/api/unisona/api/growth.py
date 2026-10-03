"""Campaigns, automations, outbound webhooks and evaluations."""
from __future__ import annotations

import csv
import io
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..brain.identity import normalize_phone
from ..db import get_db, utcnow
from ..models import (Agent, Automation, AutomationRun, Campaign, CampaignTarget, Contact, EvalRun, EvalSuite, WebhookDelivery, WebhookEndpoint)
from ..security.auth import AuthContext, require_auth
from ..services.automations import STEP_TYPES, TRIGGERS, start_run
from ..services.campaigns import DEFAULTS
from ..services.webhooks import EVENTS
from ..worker.queue import enqueue
from .common import audit, crud_router, get_scoped, to_dict

router = APIRouter()

# ── Campaigns ────────────────────────────────────────────────────────────────
router.include_router(crud_router(Campaign, "/campaigns", writable={"name", "type", "agent_id", "settings", "scheduled_at"},
                                  required={"name", "type", "agent_id"}, filters={"status", "type"}))


@router.get("/campaigns-defaults")
async def campaign_defaults():
    return {"settings": DEFAULTS}


@router.post("/campaigns/{campaign_id}/targets")
async def add_targets(campaign_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Campaign, campaign_id, auth)
    added = 0
    if body.get("contact_ids") or body.get("tag"):
        q = select(Contact).where(Contact.workspace_id == auth.ws)
        if body.get("contact_ids"):
            q = q.where(Contact.id.in_(body["contact_ids"]))
        if body.get("tag"):
            q = q.where(Contact.tags.contains([body["tag"]]))
        from ..models import ContactIdentity

        ident_type = {"email": "email", "instagram": "instagram_id", "messenger": "messenger_id", "telegram": "telegram_id"}.get(c.type)
        for ct in (await db.execute(q)).scalars():
            addr = ct.phone
            if c.type == "email":
                addr = ct.email
            elif ident_type and ident_type != "email":
                addr = (await db.execute(select(ContactIdentity.value).where(ContactIdentity.contact_id == ct.id,
                                                                             ContactIdentity.type == ident_type))).scalars().first()
            if addr:
                db.add(CampaignTarget(workspace_id=auth.ws, campaign_id=c.id, contact_id=ct.id, address=addr, variables={"name": ct.name or ""}))
                added += 1
    for row in body.get("rows") or []:
        addr = (str(row.get("email") or "") if c.type == "email" else normalize_phone(str(row.get("phone") or row.get("address") or ""))) or str(row.get("telegram_id") or "")
        if addr:
            db.add(CampaignTarget(workspace_id=auth.ws, campaign_id=c.id, address=addr, variables={k: v for k, v in row.items() if k not in {"phone", "address"}}))
            added += 1
    await db.commit()
    return {"added": added}


@router.post("/campaigns/{campaign_id}/targets/upload")
async def upload_targets(campaign_id: str, file: UploadFile = File(...), auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Campaign, campaign_id, auth)
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    added = 0
    for row in rows:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        addr = (r.get("email", "") if c.type == "email" else normalize_phone(r.get("phone") or r.get("mobile") or "")) or r.get("telegram_id", "")
        if addr:
            db.add(CampaignTarget(workspace_id=auth.ws, campaign_id=c.id, address=addr, variables=r))
            added += 1
    await db.commit()
    return {"added": added, "rows": len(rows)}


@router.get("/campaigns/{campaign_id}/targets")
async def list_targets(campaign_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    await get_scoped(db, Campaign, campaign_id, auth)
    rows = (await db.execute(select(CampaignTarget).where(CampaignTarget.campaign_id == campaign_id).order_by(CampaignTarget.updated_at.desc()).limit(1000))).scalars().all()
    return {"items": [to_dict(r) for r in rows]}


@router.post("/campaigns/{campaign_id}/{action}")
async def campaign_action(campaign_id: str, action: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Campaign, campaign_id, auth)
    n = (await db.execute(select(func.count()).select_from(CampaignTarget).where(CampaignTarget.campaign_id == c.id))).scalar()
    if action == "start":
        if not n:
            raise HTTPException(422, "Add recipients first")
        c.status = "scheduled" if c.scheduled_at and c.scheduled_at > utcnow() else "running"
    elif action == "pause":
        c.status = "paused"
    elif action == "resume":
        c.status = "running"
    else:
        raise HTTPException(422, "Unknown action")
    await audit(db, auth, f"campaign.{action}", c.id)
    await db.commit()
    return to_dict(c)


# ── Automations ──────────────────────────────────────────────────────────────
router.include_router(crud_router(Automation, "/automations", writable={"name", "trigger", "steps", "enabled"}, required={"name"}))


@router.get("/automations-meta")
async def automations_meta():
    return {"triggers": TRIGGERS, "steps": STEP_TYPES}


@router.post("/automations/{automation_id}/run")
async def run_automation(automation_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    await get_scoped(db, Automation, automation_id, auth)
    run_id = await start_run(auth.ws, automation_id, {"contact_id": body.get("contact_id"), "manual": True})
    run = await db.get(AutomationRun, run_id)
    await db.refresh(run)
    return to_dict(run)


@router.get("/automations/{automation_id}/runs")
async def automation_runs(automation_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AutomationRun).where(AutomationRun.workspace_id == auth.ws, AutomationRun.automation_id == automation_id)
                             .order_by(AutomationRun.created_at.desc()).limit(100))).scalars().all()
    return {"items": [to_dict(r) for r in rows]}


# ── Webhooks ─────────────────────────────────────────────────────────────────
@router.get("/webhook-endpoints")
async def list_endpoints(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.workspace_id == auth.ws))).scalars().all()
    return {"items": [{**to_dict(r), "secret": r.secret[:6] + "…"} for r in rows], "events": EVENTS}


@router.post("/webhook-endpoints")
async def create_endpoint(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    url = body.get("url", "")
    if not url.startswith("https://") and not url.startswith("http://localhost"):
        raise HTTPException(422, "Webhook URL must be https")
    ep = WebhookEndpoint(workspace_id=auth.ws, url=url, events=body.get("events") or [], secret="whsec_" + secrets.token_urlsafe(24))
    db.add(ep)
    await db.commit()
    return to_dict(ep)


@router.delete("/webhook-endpoints/{ep_id}")
async def delete_endpoint(ep_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    ep = await get_scoped(db, WebhookEndpoint, ep_id, auth)
    await db.delete(ep)
    await db.commit()
    return {"ok": True}


@router.post("/webhook-endpoints/{ep_id}/test")
async def test_endpoint(ep_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from ..services.webhooks import emit

    await get_scoped(db, WebhookEndpoint, ep_id, auth)
    await emit(auth.ws, "conversation.ended", {"test": True, "message": "Hello from Unisona"})
    return {"ok": True}


@router.get("/webhook-deliveries")
async def deliveries(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WebhookDelivery).where(WebhookDelivery.workspace_id == auth.ws).order_by(WebhookDelivery.created_at.desc()).limit(100))).scalars().all()
    return {"items": [to_dict(r) for r in rows]}


# ── Evaluations ──────────────────────────────────────────────────────────────
router.include_router(crud_router(EvalSuite, "/eval-suites", writable={"agent_id", "name", "kind", "cases"}, required={"agent_id", "name"}, filters={"agent_id", "kind"}))


@router.post("/evals/run")
async def run_eval(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    agent = await get_scoped(db, Agent, body["agent_id"], auth)
    kind = body.get("kind", "qa")
    suite_id = body.get("suite_id")
    if kind == "qa" and not suite_id:
        raise HTTPException(422, "QA evaluations need a suite with test cases")
    run = EvalRun(workspace_id=auth.ws, agent_id=agent.id, suite_id=suite_id, kind=kind)
    db.add(run)
    await db.commit()
    await enqueue("eval.voice" if kind == "voice" else "eval.run", {"run_id": run.id}, workspace_id=auth.ws, max_attempts=1)
    return to_dict(run)


@router.get("/evals/voice-presets")
async def voice_presets():
    from ..evals.voice_sim import ACCENTS, DEFAULT_SCENARIOS

    return {"accents": list(ACCENTS), "scenarios": DEFAULT_SCENARIOS}


@router.get("/evals/runs")
async def eval_runs(agent_id: str | None = None, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    q = select(EvalRun).where(EvalRun.workspace_id == auth.ws)
    if agent_id:
        q = q.where(EvalRun.agent_id == agent_id)
    rows = (await db.execute(q.order_by(EvalRun.created_at.desc()).limit(50))).scalars().all()
    return {"items": [to_dict(r) for r in rows]}


@router.get("/evals/runs/{run_id}")
async def eval_run(run_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    return to_dict(await get_scoped(db, EvalRun, run_id, auth))
