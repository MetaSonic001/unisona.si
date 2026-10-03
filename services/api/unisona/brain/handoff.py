"""Human handoff: detection, the AI-written brief, routing and alerts."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import utcnow
from ..log import get_logger
from ..models import Conversation, Handoff, Message
from ..realtime import hub

log = get_logger("handoff")

_EXPLICIT = re.compile(
    r"\b(talk|speak|connect|transfer)\b.{0,25}\b(human|person|agent|representative|someone|manager|real)\b"
    r"|\b(human|real person|live agent|customer care|manager)\b\s*(please|pls)?\s*$"
    r"|\b(insaan|aadmi|kisi se baat|manager se baat|agent se baat)\b"
    r"|(इंसान|किसी व्यक्ति|मैनेजर|एजेंट) से बात",
    re.I,
)
_FRUSTRATION = re.compile(
    r"\b(useless|stupid|worst|terrible|ridiculous|not helpful|waste of time|frustrat|angry|pathetic|scam|fraud|bakwas|bekaar|faltu)\b"
    r"|!!!|\?\?\?", re.I)


def detect_trigger(text: str, history_user_msgs: list[str], cfg: dict, low_conf_streak: int) -> str | None:
    ho = cfg.get("handoff", {})
    if not ho.get("enabled", True):
        return None
    t = text or ""
    if ho.get("explicit_request", True) and _EXPLICIT.search(t):
        return "customer_requested"
    for topic in ho.get("topics") or []:
        if topic and topic.lower() in t.lower():
            return f"policy_topic:{topic}"
    if ho.get("frustration", True):
        caps = sum(1 for ch in t if ch.isupper()) / max(1, sum(1 for ch in t if ch.isalpha()))
        if _FRUSTRATION.search(t) or (len(t) > 15 and caps > 0.7):
            recent_frustrated = sum(1 for m in history_user_msgs[-3:] if _FRUSTRATION.search(m))
            if recent_frustrated >= 1:
                return "frustration"
    n = int(ho.get("repeat_question", 3) or 0)
    if n and len(history_user_msgs) >= n - 1:
        norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()  # noqa: E731
        same = sum(1 for m in history_user_msgs[-(n - 1):] if norm(m) == norm(t) or (len(norm(t)) > 8 and norm(t) in norm(m)))
        if same >= n - 1:
            return "repeated_question"
    lc = int(ho.get("low_confidence_turns", 2) or 0)
    if lc and low_conf_streak >= lc:
        return "low_confidence"
    return None


BRIEF_SYSTEM = """Write a handoff brief for a human support agent taking over this conversation.
Return JSON: {"brief": "3-5 short lines: who the customer is, what they want, what the AI already tried, suggested next step",
"urgency": "low|normal|high", "subject": "max 8 words"}"""


async def create_handoff(db: AsyncSession, conv: Conversation, reason: str, llm=None, contact_brief: str = "") -> Handoff:
    if len(reason or "") > 64:  # the AI may give a free-text reason; keep the full text in the brief context
        contact_brief = f"Reason given by the AI: {reason}\n{contact_brief}"
        reason = "agent_requested"
    existing = (await db.execute(select(Handoff).where(Handoff.conversation_id == conv.id, Handoff.status.in_(["pending", "accepted"])))).scalar_one_or_none()
    if existing:
        return existing
    brief, urgency, subject = "", "high" if reason in {"frustration", "customer_requested"} else "normal", conv.subject
    if llm is not None and llm.available:
        msgs = (await db.execute(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.desc()).limit(14))).scalars().all()
        transcript = "\n".join(f"{m.role}: {m.content[:300]}" for m in reversed(msgs))
        try:
            data = await llm.json(BRIEF_SYSTEM, f"Reason: {reason}\nCustomer context: {contact_brief[:800]}\n\nTranscript:\n{transcript}", purpose="handoff")
            brief, urgency, subject = data.get("brief", ""), data.get("urgency", urgency), data.get("subject") or subject
        except Exception as e:
            log.warning(f"Brief generation failed: {e}")
    ho = Handoff(workspace_id=conv.workspace_id, conversation_id=conv.id, reason=reason, urgency=urgency, brief=brief or f"Reason: {reason}")
    db.add(ho)
    conv.status = "handoff_pending"
    conv.subject = subject or conv.subject
    await db.commit()
    log.info(f"Handoff requested for {conv.id} ({reason}, {urgency})")
    from ..services.notify import notify
    from ..services.webhooks import emit

    await notify(conv.workspace_id, "handoff", f"Human needed: {subject or 'conversation'}",
                 f"{reason.replace('_', ' ')} on {conv.channel}. {brief[:200]}", f"/app/inbox?c={conv.id}", urgent=True)
    await hub.publish(conv.workspace_id, {"type": "handoff.requested", "conversation_id": conv.id, "handoff_id": ho.id,
                                          "reason": reason, "urgency": urgency, "brief": brief, "channel": conv.channel})
    await emit(conv.workspace_id, "handoff.requested", {"conversation_id": conv.id, "reason": reason, "urgency": urgency, "brief": brief})
    return ho


async def accept(db: AsyncSession, conv: Conversation, user_id: str) -> None:
    ho = (await db.execute(select(Handoff).where(Handoff.conversation_id == conv.id, Handoff.status == "pending"))).scalar_one_or_none()
    if ho:
        ho.status, ho.assignee_id, ho.accepted_at = "accepted", user_id, utcnow()
    conv.status, conv.assignee_id, conv.ai_enabled = "human", user_id, False
    await db.commit()
    await hub.publish(conv.workspace_id, {"type": "conversation.updated", "conversation_id": conv.id, "status": "human", "assignee_id": user_id})
    await hub.publish(f"conv:{conv.id}", {"type": "agent.joined", "text": "A team member has joined the conversation."})


async def release_to_ai(db: AsyncSession, conv: Conversation) -> None:
    for ho in (await db.execute(select(Handoff).where(Handoff.conversation_id == conv.id, Handoff.status.in_(["pending", "accepted"])))).scalars():
        ho.status, ho.resolved_at = "resolved", utcnow()
    conv.status, conv.ai_enabled = "ai", True
    await db.commit()
    await hub.publish(conv.workspace_id, {"type": "conversation.updated", "conversation_id": conv.id, "status": "ai"})
