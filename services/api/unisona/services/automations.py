"""Workflow automations: trigger → ordered steps (with waits and conditions).

Triggers are platform events (contact.created, conversation.ended, appointment.booked,
handoff.requested, deal.stage_changed, lead.captured, analysis.completed, call.ended ...)
plus optional match conditions on the event data. Steps run in the worker; `wait` steps
schedule a delayed continuation job so runs survive restarts.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import Activity, Agent, Automation, AutomationRun, Contact, Deal, Task, Workspace

log = get_logger("automations")

STEP_TYPES = {
    "send_message": "Send a message (WhatsApp / Telegram / email / SMS)",
    "ai_message": "Send an AI-written personalised message",
    "start_call": "Start an AI phone call",
    "add_tag": "Add a tag",
    "remove_tag": "Remove a tag",
    "update_field": "Update a contact field",
    "set_lifecycle": "Set lifecycle stage",
    "create_task": "Create a task",
    "move_deal": "Move open deal to stage",
    "notify": "Notify the team",
    "webhook": "Call a webhook",
    "review_request": "Ask for a review (happy → Google, unhappy → private feedback)",
    "send_payment_link": "Send a payment link (Razorpay / Stripe)",
    "add_to_campaign": "Add to a campaign",
    "wait": "Wait",
    "condition": "Continue only if…",
}
TRIGGERS = ["contact.created", "lead.captured", "conversation.started", "conversation.ended", "analysis.completed", "call.ended",
            "handoff.requested", "appointment.booked", "deal.stage_changed", "message.created", "form.submitted", "payment.received",
            "review.received", "contact.opted_out", "call.transferred", "agent.transferred", "webhook.received", "manual"]


def _get(data: dict, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _match(cond: dict, data: dict) -> bool:
    val = _get(data, cond.get("field", ""))
    op, target = cond.get("op", "equals"), cond.get("value")
    if op == "equals":
        return str(val).lower() == str(target).lower()
    if op == "not_equals":
        return str(val).lower() != str(target).lower()
    if op == "contains":
        return target is not None and str(target).lower() in str(val or "").lower()
    if op == "exists":
        return val not in (None, "", [])
    if op == "gt":
        try:
            return float(val) > float(target)
        except (TypeError, ValueError):
            return False
    if op == "lt":
        try:
            return float(val) < float(target)
        except (TypeError, ValueError):
            return False
    return False


async def on_event(ws_id: str, event: str, data: dict) -> int:
    async with SessionLocal() as db:
        autos = (await db.execute(select(Automation).where(Automation.workspace_id == ws_id, Automation.enabled.is_(True)))).scalars().all()
        matched = [a for a in autos if (a.trigger or {}).get("event") == event and all(_match(c, data) for c in (a.trigger or {}).get("conditions", []))]
    for a in matched:
        await start_run(ws_id, a.id, data)
    return len(matched)


async def start_run(ws_id: str, automation_id: str, data: dict) -> str:
    async with SessionLocal() as db:
        auto = await db.get(Automation, automation_id)
        contact_id = data.get("contact_id")
        if not contact_id and data.get("conversation_id"):
            from ..models import Conversation

            conv = await db.get(Conversation, data["conversation_id"])
            contact_id = conv.contact_id if conv else None
        run = AutomationRun(workspace_id=ws_id, automation_id=auto.id, contact_id=contact_id, log=[{"at": utcnow().isoformat(), "event": "started", "data": data}])
        db.add(run)
        auto.run_count += 1
        await db.commit()
        run_id = run.id
    await continue_run(run_id, 0)
    return run_id


async def continue_run(run_id: str, step_index: int) -> None:
    from ..worker.queue import enqueue

    async with SessionLocal() as db:
        run = await db.get(AutomationRun, run_id)
        auto = await db.get(Automation, run.automation_id)
        ws = await db.get(Workspace, run.workspace_id)
        contact = await db.get(Contact, run.contact_id) if run.contact_id else None
        steps = auto.steps or []
        logs = list(run.log or [])
        i = step_index
        while i < len(steps):
            step = steps[i]
            typ = step.get("type")
            try:
                if typ == "wait":
                    minutes = float(step.get("minutes", 0)) + 60 * float(step.get("hours", 0)) + 1440 * float(step.get("days", 0))
                    logs.append({"step": i, "type": typ, "status": "waiting", "minutes": minutes})
                    run.log, run.status = logs, "waiting"
                    await db.commit()
                    await enqueue("automation.resume", {"run_id": run_id, "step": i + 1}, workspace_id=ws.id, delay_s=minutes * 60)
                    return
                result = await _run_step(db, ws, contact, step, run)
                if result == "stop":
                    logs.append({"step": i, "type": typ, "status": "condition_false"})
                    break
                logs.append({"step": i, "type": typ, "status": "ok", "detail": result})
            except Exception as e:
                logs.append({"step": i, "type": typ, "status": "error", "detail": str(e)[:300]})
                log.warning(f"Automation {auto.name} step {i} ({typ}) failed: {e}")
            i += 1
        run.log, run.status = logs, "completed"
        await db.commit()


async def _run_step(db, ws: Workspace, contact: Contact | None, step: dict, run: AutomationRun) -> str:
    typ = step.get("type")
    if typ == "condition":
        data = {"contact": {"name": contact.name, "tags": contact.tags, "lifecycle": contact.lifecycle, "score": contact.score,
                            "fields": contact.fields} if contact else {}}
        field = step.get("field", "")
        if field.startswith("contact.tags") and contact:
            return "ok" if step.get("value") in (contact.tags or []) else "stop"
        return "ok" if _match(step, data) else "stop"
    if not contact:
        return "skipped (no contact)"
    if typ == "add_tag":
        contact.tags = sorted(set(contact.tags or []) | {step["tag"]})
        return f"tag {step['tag']}"
    if typ == "remove_tag":
        contact.tags = [t for t in (contact.tags or []) if t != step["tag"]]
        return f"untag {step['tag']}"
    if typ == "update_field":
        contact.fields = {**(contact.fields or {}), step["field"]: step.get("value")}
        return f"{step['field']}={step.get('value')}"
    if typ == "set_lifecycle":
        contact.lifecycle = step.get("value", contact.lifecycle)
        return contact.lifecycle
    if typ == "create_task":
        from datetime import timedelta

        db.add(Task(workspace_id=ws.id, title=_fill(step.get("title", "Follow up"), contact), contact_id=contact.id,
                    due_at=utcnow() + timedelta(hours=float(step.get("due_hours", 24))), created_by="automation"))
        return "task created"
    if typ == "move_deal":
        deal = (await db.execute(select(Deal).where(Deal.contact_id == contact.id, Deal.status == "open"))).scalars().first()
        if deal:
            deal.stage = step.get("stage", deal.stage)
            return f"deal → {deal.stage}"
        return "no open deal"
    if typ == "notify":
        from .notify import notify

        await notify(ws.id, "automation", _fill(step.get("title", "Automation alert"), contact), _fill(step.get("body", ""), contact),
                     f"/app/crm/contacts/{contact.id}", urgent=bool(step.get("urgent")))
        return "notified"
    if typ in {"send_message", "ai_message"}:
        from ..channels.outbound import send_to_contact

        agent = await db.get(Agent, step.get("agent_id")) if step.get("agent_id") else None
        text = _fill(step.get("text", ""), contact)
        if typ == "ai_message":
            from ..providers.llm import get_llm

            llm = await get_llm(db, ws, feature="AI automation messages")
            if llm.available:
                r = await llm.chat([{"role": "system", "content": "Write one short, friendly, personalised message to a customer for a business. Plain text, no placeholders."},
                                    {"role": "user", "content": f"Business: {ws.name}\nCustomer: {contact.name or 'customer'}; facts: {contact.summary or ''}\nGoal: {step.get('instruction', '')}"}],
                                   max_tokens=300, purpose="automation")
                text = r.content
        ok, detail = await send_to_contact(db, ws, agent, contact, step.get("channel", "whatsapp"), text)
        db.add(Activity(workspace_id=ws.id, contact_id=contact.id, type="automation.message", title=f"Automation message via {step.get('channel')}",
                        data={"text": text[:500], "ok": ok, "detail": detail}, actor="automation"))
        return f"{'sent' if ok else 'not sent'}: {detail}"
    if typ == "start_call":
        from ..channels.telephony import dial
        from ..models import Channel

        ch = (await db.execute(select(Channel).where(Channel.workspace_id == ws.id, Channel.type == "phone", Channel.enabled.is_(True)))).scalars().first()
        if not ch or not contact.phone:
            return "skipped (no phone channel or number)"
        await dial(ws, ch, contact.phone)
        return "call started"
    if typ == "review_request":
        from .reputation import send_request

        r = await send_request(ws.id, contact.id, step.get("channel"))
        return f"review request: {r}"
    if typ == "send_payment_link":
        from .payments import create_and_send

        ok, detail, link = await create_and_send(db, ws, None, contact, float(step.get("amount") or 0), _fill(step.get("description", "Payment"), contact),
                                                 channel=step.get("channel", "whatsapp"), currency=step.get("currency"))
        return f"payment link {'sent' if ok else 'not sent'}: {detail}"
    if typ == "add_to_campaign":
        from ..models import Campaign, CampaignTarget

        camp = await db.get(Campaign, step.get("campaign_id", ""))
        if not camp or camp.workspace_id != ws.id:
            return "campaign not found"
        address = contact.phone if camp.type in {"voice", "sms", "whatsapp", "whatsapp_template"} else contact.email if camp.type == "email" else None
        if not address:
            return "contact has no address for this campaign"
        db.add(CampaignTarget(workspace_id=ws.id, campaign_id=camp.id, contact_id=contact.id, address=address,
                              variables={"name": contact.name or ""}))
        return f"added to {camp.name}"
    if typ == "webhook":
        import httpx

        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(step["url"], json={"contact": {"id": contact.id, "name": contact.name, "phone": contact.phone,
                                                             "email": contact.email, "tags": contact.tags, "fields": contact.fields}})
        return f"HTTP {r.status_code}"
    return f"unknown step {typ}"


def _fill(text: str, contact: Contact | None) -> str:
    if not contact:
        return text
    first = (contact.name or "there").split()[0]
    return (text or "").replace("{{first_name}}", first).replace("{{name}}", contact.name or "there")
