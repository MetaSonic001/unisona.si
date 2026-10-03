"""Cross-channel memory.

Layers:
1. Working memory: the current conversation's recent turns.
2. Episodic: per-conversation summaries across *all* channels for this contact.
3. Semantic facts: durable facts with validity windows (a contradicted fact is closed
   with `valid_to`, never silently overwritten).
4. CRM state: open deals, tasks and upcoming appointments.

`contact_brief()` assembles these into a compact block injected into every prompt, so
a caller who chatted on the website at 2 PM is recognised when they call at 4 PM.
"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import utcnow
from ..log import get_logger
from ..models import Appointment, Contact, ContactFact, Conversation, Deal, Message, Task

log = get_logger("memory")
CHANNEL_LABEL = {"web": "website chat", "widget": "website widget", "voice": "voice call", "phone": "phone call",
                 "whatsapp": "WhatsApp", "telegram": "Telegram", "email": "email", "playground": "test playground"}


def _ago(dt) -> str:
    if not dt:
        return ""
    delta = utcnow() - dt
    s = int(delta.total_seconds())
    if s < 3600:
        return f"{max(1, s // 60)} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} days ago"


async def contact_brief(db: AsyncSession, contact: Contact | None, current_conversation_id: str | None) -> tuple[str, dict]:
    if not contact:
        return "", {}
    facts = (await db.execute(select(ContactFact).where(
        ContactFact.contact_id == contact.id, ContactFact.valid_to.is_(None)).order_by(ContactFact.valid_from.desc()).limit(12))).scalars().all()
    convs = (await db.execute(select(Conversation).where(
        Conversation.contact_id == contact.id, Conversation.id != (current_conversation_id or ""))
        .order_by(Conversation.last_message_at.desc()).limit(4))).scalars().all()

    recent_lines: list[str] = []
    for cv in convs:
        label = CHANNEL_LABEL.get(cv.channel, cv.channel)
        if cv.summary:
            recent_lines.append(f"- {label}, {_ago(cv.last_message_at)}: {cv.summary}")
        elif cv.last_message_at and utcnow() - cv.last_message_at < timedelta(days=3):
            msgs = (await db.execute(select(Message).where(Message.conversation_id == cv.id, Message.role.in_(["user", "assistant", "human"]))
                                     .order_by(Message.created_at.desc()).limit(6))).scalars().all()
            if msgs:
                snippet = " | ".join(f"{'Customer' if m.role == 'user' else 'Us'}: {m.content[:140]}" for m in reversed(msgs))
                recent_lines.append(f"- {label}, {_ago(cv.last_message_at)} (in progress): {snippet}")

    deals = (await db.execute(select(Deal).where(Deal.contact_id == contact.id, Deal.status == "open").limit(3))).scalars().all()
    tasks = (await db.execute(select(Task).where(Task.contact_id == contact.id, Task.status == "open").limit(3))).scalars().all()
    appts = (await db.execute(select(Appointment).where(Appointment.contact_id == contact.id, Appointment.status == "booked",
                                                        Appointment.start_at >= utcnow()).order_by(Appointment.start_at).limit(2))).scalars().all()

    lines = []
    who = contact.name or "Unknown name"
    known = [x for x in [contact.phone, contact.email] if x]
    lines.append(f"Customer: {who}" + (f" ({', '.join(known)})" if known else "") + (f". Lead stage: {contact.lifecycle}" if contact.lifecycle else ""))
    if contact.tags:
        lines.append(f"Tags: {', '.join(contact.tags[:8])}")
    if facts:
        lines.append("Known facts:\n" + "\n".join(f"- {f.fact}" for f in facts))
    if recent_lines:
        lines.append("Previous interactions (all channels):\n" + "\n".join(recent_lines))
    if deals:
        lines.append("Open deals: " + "; ".join(f"{d.title} at stage '{d.stage}'" for d in deals))
    if tasks:
        lines.append("Open follow-ups: " + "; ".join(t.title for t in tasks))
    if appts:
        lines.append("Upcoming appointments: " + "; ".join(f"{a.title} on {a.start_at:%a %d %b %H:%M} UTC" for a in appts))
    meta = {"contact_id": contact.id, "facts": len(facts), "previous_conversations": len(convs),
            "channels_seen": sorted({c.channel for c in convs})}
    returning = bool(convs or facts)
    if returning:
        lines.append("This is a returning customer. Greet them by name if known and use this context naturally. Do not recite it.")
    return "\n".join(lines), meta


FACT_SYSTEM = """You maintain long-term memory about a customer for a business's AI agent.
From the conversation, extract durable facts worth remembering for future conversations on ANY channel:
identity details (name, company, city), preferences, needs, products owned, order/booking references,
commitments (e.g. "promised to pay on 5 March"), and unresolved issues. Skip small talk and anything already known.
If a new fact contradicts a known fact, list the known fact's id in "supersedes".
Return JSON: {"facts": [{"fact": str, "category": "identity|preference|need|commitment|issue|purchase|other", "confidence": 0-1, "supersedes": [ids]}],
"name": str|null, "email": str|null, "phone": str|null}"""


async def extract_facts(db: AsyncSession, llm, contact: Contact, conversation: Conversation) -> int:
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conversation.id, Message.role.in_(["user", "assistant", "human"]))
                             .order_by(Message.created_at.desc()).limit(24))).scalars().all()
    if not msgs:
        return 0
    known = (await db.execute(select(ContactFact).where(ContactFact.contact_id == contact.id, ContactFact.valid_to.is_(None)))).scalars().all()
    transcript = "\n".join(f"{'Customer' if m.role == 'user' else 'Agent'}: {m.content}" for m in reversed(msgs))
    known_txt = json.dumps([{"id": f.id, "fact": f.fact} for f in known], ensure_ascii=False)
    data = await llm.json(FACT_SYSTEM, f"Known facts: {known_txt}\n\nConversation ({conversation.channel}):\n{transcript}", purpose="memory")
    added = 0
    known_ids = {f.id: f for f in known}
    for item in data.get("facts", [])[:10]:
        text = (item.get("fact") or "").strip()
        if not text or float(item.get("confidence", 0.7)) < 0.5:
            continue
        for sid in item.get("supersedes") or []:
            if sid in known_ids:
                known_ids[sid].valid_to = utcnow()
        db.add(ContactFact(workspace_id=contact.workspace_id, contact_id=contact.id, fact=text[:500],
                           category=item.get("category", "other"), confidence=float(item.get("confidence", 0.8)),
                           source_conversation_id=conversation.id, source_channel=conversation.channel))
        added += 1
    if data.get("name") and not contact.name:
        contact.name = data["name"][:200]
    from .identity import add_identity

    if data.get("email"):
        await add_identity(db, contact, "email", data["email"])
    if data.get("phone"):
        await add_identity(db, contact, "phone", data["phone"])
    await db.commit()
    if added:
        log.info(f"Memory: +{added} facts for contact {contact.id}")
    return added
