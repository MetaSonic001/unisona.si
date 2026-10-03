"""Post-conversation analysis and Auto-CRM, plus the nightly improve loop."""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import utcnow
from ..log import get_logger
from ..models import (Activity, Agent, Contact, Conversation, Deal, Message, Pipeline, ReviewItem, Task, Workspace)
from ..providers.llm import get_llm
from .agent_config import normalize

log = get_logger("analysis")


def _schema_text(cfg: dict) -> str:
    fields = cfg["analysis"].get("extraction") or []
    if not fields:
        return "{}"
    return json.dumps({f["name"]: f"{f.get('type', 'string')} — {f.get('description', '')}" for f in fields}, ensure_ascii=False)


ANALYSIS_SYSTEM = """You analyse a finished customer conversation for a business. Return strict JSON:
{
 "summary": "2-3 sentence summary (who, what they wanted, outcome)",
 "disposition": one of DISPOSITIONS,
 "sentiment": "positive|neutral|negative",
 "csat_estimate": 1-5,
 "intent": "short label of the main intent",
 "resolved": true|false,
 "lead_score": 0-100 (purchase/engagement intent; 0 if not a sales context),
 "tags": ["up to 4 short lowercase tags"],
 "follow_up": "a follow-up task the team should do, or empty string",
 "knowledge_gaps": ["questions the agent could not answer well"],
 "fields": EXTRACTION_SCHEMA (use null when unknown)
}"""


async def analyze_conversation(db: AsyncSession, conversation_id: str) -> dict:
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        return {"skipped": "missing"}
    ws = await db.get(Workspace, conv.workspace_id)
    agent = await db.get(Agent, conv.agent_id)
    cfg = normalize(agent.published_config or agent.config)
    msgs = (await db.execute(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at))).scalars().all()
    turns = [m for m in msgs if m.role in {"user", "assistant", "human"}]
    if len([m for m in turns if m.role == "user"]) == 0:
        return {"skipped": "no user messages"}
    llm = await get_llm(db, ws, feature="post-conversation analysis")
    if not llm.available:
        return {"skipped": "no llm"}
    transcript = "\n".join(f"{'Customer' if m.role == 'user' else ('Human agent' if m.role == 'human' else 'AI agent')}: {m.content}" for m in turns[-60:])
    system = ANALYSIS_SYSTEM.replace("DISPOSITIONS", json.dumps(cfg["analysis"].get("dispositions") or ["resolved", "unresolved"])) \
                            .replace("EXTRACTION_SCHEMA", _schema_text(cfg))
    data = await llm.json(system, f"Channel: {conv.channel}\n\nTranscript:\n{transcript}", purpose="analysis", max_tokens=1500)
    conv.summary = (data.get("summary") or "")[:2000]
    conv.outcome = data.get("disposition") or conv.outcome
    conv.sentiment = data.get("sentiment")
    try:
        conv.csat = int(data.get("csat_estimate")) if data.get("csat_estimate") is not None else None
    except (TypeError, ValueError):
        pass
    conv.analysis = data
    if conv.status != "closed" and conv.status == "ai":
        conv.status = "closed"
        conv.ended_at = conv.ended_at or utcnow()

    contact = await db.get(Contact, conv.contact_id) if conv.contact_id else None
    if contact and cfg["analysis"].get("auto_crm", True):
        changes = {}
        fields = {k: v for k, v in (data.get("fields") or {}).items() if v not in (None, "", [])}
        if fields:
            contact.fields = {**(contact.fields or {}), **fields}
            changes["fields"] = fields
        new_tags = [t for t in (data.get("tags") or []) if isinstance(t, str)][:4]
        if new_tags:
            contact.tags = sorted(set(contact.tags or []) | set(new_tags))
            changes["tags"] = new_tags
        try:
            score = int(data.get("lead_score") or 0)
            if score:
                contact.score = max(contact.score or 0, score)
                changes["score"] = score
                if score >= 70 and contact.lifecycle == "lead":
                    contact.lifecycle = "qualified"
        except (TypeError, ValueError):
            pass
        contact.summary = conv.summary
        if data.get("follow_up"):
            db.add(Task(workspace_id=ws.id, title=data["follow_up"][:300], contact_id=contact.id, conversation_id=conv.id,
                        created_by="ai", due_at=utcnow() + timedelta(days=1)))
            changes["task"] = data["follow_up"]
        if (data.get("lead_score") or 0) >= 60:
            pl = (await db.execute(select(Pipeline).where(Pipeline.workspace_id == ws.id).limit(1))).scalar_one_or_none()
            has_deal = (await db.execute(select(Deal).where(Deal.contact_id == contact.id, Deal.status == "open"))).scalars().first()
            if pl and not has_deal:
                db.add(Deal(workspace_id=ws.id, pipeline_id=pl.id, stage=pl.stages[0]["id"] if pl.stages else "new",
                            title=f"{contact.name or 'Lead'} · {data.get('intent') or conv.channel}"[:200], contact_id=contact.id))
                changes["deal"] = "created"
        db.add(Activity(workspace_id=ws.id, contact_id=contact.id, type="conversation.analyzed",
                        title=f"{conv.channel.title()} conversation: {conv.outcome or 'completed'}",
                        data={"conversation_id": conv.id, "summary": conv.summary, "changes": changes}, actor="ai"))

    for gap in (data.get("knowledge_gaps") or [])[:3]:
        if isinstance(gap, str) and gap.strip():
            db.add(ReviewItem(workspace_id=ws.id, agent_id=agent.id, conversation_id=conv.id, question=gap[:1000], reason="knowledge_gap"))
    await db.commit()
    if contact and cfg["memory"].get("remember_facts", True):
        from .cache import invalidate_prefix
        from .memory import extract_facts

        try:
            await extract_facts(db, llm, contact, conv)
        except Exception as e:
            log.warning(f"Fact extraction failed for {conv.id}: {e}")
        invalidate_prefix(f"brief:{contact.id}")
    from ..services.webhooks import emit

    await emit(ws.id, "analysis.completed", {"conversation_id": conv.id, "summary": conv.summary, "disposition": conv.outcome,
                                             "sentiment": conv.sentiment, "fields": data.get("fields")})
    await emit(ws.id, "conversation.ended", {"conversation_id": conv.id, "channel": conv.channel, "disposition": conv.outcome,
                                             "contact_id": conv.contact_id})
    log.info(f"Analyzed {conv.id}: {conv.outcome} / {conv.sentiment}")
    return {"disposition": conv.outcome, "sentiment": conv.sentiment}


IMPROVE_SYSTEM = """A customer-facing AI agent gave a poor answer. Using ONLY the knowledge excerpts provided, write the ideal
short answer. If the knowledge does not contain the answer, say so and suggest what document the business should add.
Return JSON: {"ideal_answer": str, "answerable_from_knowledge": true|false, "suggested_source": str}"""


async def improve_flagged(db: AsyncSession, ws: Workspace, since_hours: int = 30) -> int:
    """Nightly: turn flagged/low-rated answers into review items with a proposed correction."""
    from ..knowledge.retrieve import retrieve
    from .respond import agent_cfg, agent_kb_ids

    flagged = (await db.execute(select(Message).where(
        Message.workspace_id == ws.id, Message.role == "assistant", Message.created_at > utcnow() - timedelta(hours=since_hours),
        (Message.feedback == -1) | (Message.flagged.is_(True))))).scalars().all()
    llm = await get_llm(db, ws, feature="nightly improve loop")
    if not llm.available or not flagged:
        return 0
    made = 0
    for m in flagged[:40]:
        exists = (await db.execute(select(ReviewItem).where(ReviewItem.message_id == m.id))).scalar_one_or_none()
        if exists:
            continue
        conv = await db.get(Conversation, m.conversation_id)
        q = (await db.execute(select(Message).where(Message.conversation_id == m.conversation_id, Message.role == "user",
                                                    Message.created_at <= m.created_at).order_by(Message.created_at.desc()).limit(1))).scalar_one_or_none()
        if not q or not conv:
            continue
        agent = await db.get(Agent, conv.agent_id)
        cfg = agent_cfg(agent, False)
        kb_ids = await agent_kb_ids(db, agent, cfg)
        res = await retrieve(db, ws.id, kb_ids, q.content, k=5, mode="deep") if kb_ids else None
        knowledge = "\n\n".join(c.text for c in res.chunks) if res else ""
        data = await llm.json(IMPROVE_SYSTEM, f"Question: {q.content}\nBad answer: {m.content}\n\nKnowledge:\n{knowledge[:6000]}", purpose="improve")
        db.add(ReviewItem(workspace_id=ws.id, agent_id=agent.id, message_id=m.id, conversation_id=conv.id, question=q.content,
                          bad_answer=m.content, proposed_answer=data.get("ideal_answer", ""),
                          reason="thumbs_down" if m.feedback == -1 else (m.flag_reason or "flagged")))
        made += 1
    await db.commit()
    log.info(f"Improve loop for {ws.id}: {made} review items")
    return made
