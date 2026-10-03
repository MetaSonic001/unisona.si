"""Forms and surveys: hosted/embeddable, every submission becomes (or updates) a CRM contact,
fires `form.submitted` for automations, and can trigger an instant AI follow-up (speed-to-lead):
an AI call or WhatsApp message within seconds of the form being filled.
"""
from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from ..log import get_logger
from ..models import Activity, Form, FormSubmission, Workspace

log = get_logger("forms")

FIELD_TYPES = ["text", "email", "phone", "textarea", "select", "radio", "checkbox", "number", "date", "rating", "nps"]
TEMPLATES = {
    "contact": {"name": "Contact us", "kind": "form", "fields": [
        {"id": "name", "label": "Your name", "type": "text", "required": True, "map_to": "name"},
        {"id": "phone", "label": "Phone / WhatsApp", "type": "phone", "required": True, "map_to": "phone"},
        {"id": "email", "label": "Email", "type": "email", "required": False, "map_to": "email"},
        {"id": "message", "label": "How can we help?", "type": "textarea", "required": False}]},
    "nps": {"name": "Customer satisfaction survey", "kind": "survey", "fields": [
        {"id": "nps", "label": "How likely are you to recommend us to a friend?", "type": "nps", "required": True},
        {"id": "liked", "label": "What did you like most?", "type": "textarea"},
        {"id": "improve", "label": "What could we do better?", "type": "textarea"}]},
    "lead": {"name": "Get a quote", "kind": "form", "fields": [
        {"id": "name", "label": "Full name", "type": "text", "required": True, "map_to": "name"},
        {"id": "phone", "label": "Phone", "type": "phone", "required": True, "map_to": "phone"},
        {"id": "service", "label": "Service needed", "type": "select", "options": ["Consultation", "Installation", "Repair", "Other"]},
        {"id": "budget", "label": "Budget", "type": "radio", "options": ["< ₹10k", "₹10k–50k", "₹50k+"]},
        {"id": "consent", "label": "I agree to be contacted by call/WhatsApp", "type": "checkbox", "required": True, "map_to": "consent"}]},
}


def validate(form: Form, data: dict) -> list[str]:
    errors = []
    for f in form.fields or []:
        v = data.get(f["id"])
        if f.get("required") and (v is None or str(v).strip() == "" or v is False):
            errors.append(f"{f['label']} is required")
            continue
        if v and f.get("type") == "email" and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(v)):
            errors.append(f"{f['label']} must be a valid email")
        if v and f.get("type") == "phone" and len(re.sub(r"\D", "", str(v))) < 7:
            errors.append(f"{f['label']} must be a valid phone number")
    return errors


async def submit(db: AsyncSession, form: Form, data: dict, meta: dict) -> FormSubmission:
    from ..brain.identity import resolve_contact
    from .compliance import record_consent

    ws = await db.get(Workspace, form.workspace_id)
    mapped = {f.get("map_to"): data.get(f["id"]) for f in form.fields or [] if f.get("map_to") and data.get(f["id"]) not in (None, "")}
    identifiers = {k: str(v) for k, v in {"phone": mapped.get("phone"), "email": mapped.get("email")}.items() if v}
    contact = await resolve_contact(db, ws.id, identifiers, name=mapped.get("name"), channel="form") if identifiers else None
    if contact:
        extra = {f["id"]: data.get(f["id"]) for f in form.fields or [] if not f.get("map_to") and data.get(f["id"]) not in (None, "")}
        contact.fields = {**(contact.fields or {}), **extra}
        contact.tags = sorted(set(contact.tags or []) | set((form.settings or {}).get("tags") or []) | {f"form:{form.slug}"})
        if mapped.get("consent"):
            record_consent(contact, "marketing", "opted_in", f"form {form.name}")
        db.add(Activity(workspace_id=ws.id, contact_id=contact.id, type="form.submitted", title=f"Submitted {form.name}", data=data))
    sub = FormSubmission(workspace_id=ws.id, form_id=form.id, contact_id=contact.id if contact else None, data=data, meta=meta)
    db.add(sub)
    form.submissions = (form.submissions or 0) + 1
    await db.commit()
    from ..brain.respond import background
    from .webhooks import emit

    background(emit(ws.id, "form.submitted", {"form_id": form.id, "form": form.name, "submission_id": sub.id,
                                               "contact_id": contact.id if contact else None, "data": data}))
    follow = (form.settings or {}).get("follow_up") or {}
    if contact and follow.get("type") in {"call", "whatsapp", "sms", "email"}:
        background(_follow_up(ws, contact.id, follow, form))
    return sub


async def _follow_up(ws: Workspace, contact_id: str, follow: dict, form: Form) -> None:
    """Speed-to-lead: reach out within seconds while the lead is still warm."""
    from ..db import SessionLocal
    from ..models import Agent, Channel, Contact

    async with SessionLocal() as db:
        contact = await db.get(Contact, contact_id)
        agent = await db.get(Agent, follow.get("agent_id")) if follow.get("agent_id") else None
        try:
            if follow["type"] == "call":
                from sqlalchemy import select

                from ..channels.telephony import dial

                ch = (await db.execute(select(Channel).where(Channel.workspace_id == ws.id, Channel.type == "phone", Channel.enabled.is_(True)))).scalars().first()
                if ch and contact.phone:
                    await dial(ws, ch, contact.phone)
            else:
                from ..channels.outbound import send_to_contact

                text = (follow.get("message") or "Hi {{first_name}}, thanks for reaching out to {{business}}! How can we help you today?")
                text = text.replace("{{first_name}}", (contact.name or "there").split()[0]).replace("{{business}}", ws.name)
                await send_to_contact(db, ws, agent, contact, follow["type"], text)
        except Exception as e:
            log.warning(f"Form {form.name} follow-up failed: {e}")
