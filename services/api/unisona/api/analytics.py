"""Analytics: workspace overview, per-channel/agent breakdowns, trends, quality and cost."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db, utcnow
from ..models import Agent, Appointment, Call, Contact, Conversation, Deal, Handoff, Message, Task, UsageEvent
from ..security.auth import AuthContext, require_auth

router = APIRouter(prefix="/analytics")


async def _kpis(db: AsyncSession, ws_id: str, since, agent_id: str | None = None) -> dict:
    cv = select(Conversation).where(Conversation.workspace_id == ws_id, Conversation.started_at >= since, Conversation.channel != "playground")
    if agent_id:
        cv = cv.where(Conversation.agent_id == agent_id)
    sub = cv.subquery()
    total = (await db.execute(select(func.count()).select_from(sub))).scalar() or 0
    handed = (await db.execute(select(func.count(func.distinct(Handoff.conversation_id))).where(Handoff.conversation_id.in_(select(sub.c.id))))).scalar() or 0
    csat = (await db.execute(select(func.avg(sub.c.csat)).where(sub.c.csat.isnot(None)))).scalar()
    sentiments = dict((await db.execute(select(sub.c.sentiment, func.count()).group_by(sub.c.sentiment))).all())
    channels = dict((await db.execute(select(sub.c.channel, func.count()).group_by(sub.c.channel))).all())
    outcomes = dict((await db.execute(select(sub.c.outcome, func.count()).where(sub.c.outcome.isnot(None)).group_by(sub.c.outcome))).all())
    msgs = (await db.execute(select(func.count()).select_from(Message).where(Message.conversation_id.in_(select(sub.c.id)), Message.role == "assistant"))).scalar() or 0
    lat = (await db.execute(select(func.avg(Message.latency_ms)).where(Message.conversation_id.in_(select(sub.c.id)), Message.role == "assistant",
                                                                       Message.latency_ms.isnot(None)))).scalar()
    calls_q = select(func.count(), func.coalesce(func.sum(Call.duration_s), 0)).where(Call.workspace_id == ws_id, Call.started_at >= since)
    if agent_id:
        calls_q = calls_q.where(Call.agent_id == agent_id)
    n_calls, secs = (await db.execute(calls_q)).one()
    up = (await db.execute(select(func.count()).select_from(Message).where(Message.conversation_id.in_(select(sub.c.id)), Message.feedback == 1))).scalar() or 0
    down = (await db.execute(select(func.count()).select_from(Message).where(Message.conversation_id.in_(select(sub.c.id)), Message.feedback == -1))).scalar() or 0
    cost_q = select(func.coalesce(func.sum(UsageEvent.cost_usd), 0), func.coalesce(func.sum(UsageEvent.input_tokens + UsageEvent.output_tokens), 0)).where(
        UsageEvent.workspace_id == ws_id, UsageEvent.created_at >= since)
    if agent_id:
        cost_q = cost_q.where(UsageEvent.agent_id == agent_id)
    cost, tokens = (await db.execute(cost_q)).one()
    return {
        "conversations": total, "ai_messages": msgs, "calls": n_calls, "call_minutes": round(float(secs) / 60, 1),
        "handoffs": handed, "handoff_rate": round(handed / total, 3) if total else 0,
        "containment_rate": round(1 - handed / total, 3) if total else 0,
        "csat": round(float(csat), 2) if csat else None, "sentiment": {k or "unknown": v for k, v in sentiments.items()},
        "channels": channels, "outcomes": outcomes, "avg_response_ms": int(lat) if lat else None,
        "thumbs_up": up, "thumbs_down": down, "llm_cost_usd": round(float(cost), 4), "llm_tokens": int(tokens),
    }


@router.get("/overview")
async def overview(days: int = 30, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    since = utcnow() - timedelta(days=days)
    k = await _kpis(db, auth.ws, since)
    day = cast(Conversation.started_at, Date)
    series = (await db.execute(select(day, Conversation.channel, func.count()).where(
        Conversation.workspace_id == auth.ws, Conversation.started_at >= since, Conversation.channel != "playground")
        .group_by(day, Conversation.channel).order_by(day))).all()
    by_day: dict[str, dict] = {}
    for d, ch, n in series:
        key = d.isoformat()
        by_day.setdefault(key, {"date": key})[ch] = n
    agents = (await db.execute(select(Agent.id, Agent.name, func.count(Conversation.id)).outerjoin(
        Conversation, (Conversation.agent_id == Agent.id) & (Conversation.started_at >= since) & (Conversation.channel != "playground"))
        .where(Agent.workspace_id == auth.ws).group_by(Agent.id, Agent.name))).all()
    crm = {
        "new_contacts": (await db.execute(select(func.count()).select_from(Contact).where(Contact.workspace_id == auth.ws, Contact.created_at >= since))).scalar(),
        "open_deals": (await db.execute(select(func.count()).select_from(Deal).where(Deal.workspace_id == auth.ws, Deal.status == "open"))).scalar(),
        "pipeline_value": float((await db.execute(select(func.coalesce(func.sum(Deal.value), 0)).where(Deal.workspace_id == auth.ws, Deal.status == "open"))).scalar()),
        "appointments": (await db.execute(select(func.count()).select_from(Appointment).where(Appointment.workspace_id == auth.ws, Appointment.created_at >= since))).scalar(),
        "open_tasks": (await db.execute(select(func.count()).select_from(Task).where(Task.workspace_id == auth.ws, Task.status == "open"))).scalar(),
        "ai_tasks": (await db.execute(select(func.count()).select_from(Task).where(Task.workspace_id == auth.ws, Task.created_by == "ai", Task.created_at >= since))).scalar(),
    }
    intent_expr = Conversation.analysis["intent"].astext
    sub = select(intent_expr.label("intent")).where(Conversation.workspace_id == auth.ws, Conversation.started_at >= since,
                                                    intent_expr.isnot(None)).subquery()
    intents = (await db.execute(select(sub.c.intent, func.count()).group_by(sub.c.intent).order_by(func.count().desc()).limit(8))).all()
    return {"kpis": k, "series": list(by_day.values()), "agents": [{"id": a, "name": n, "conversations": c} for a, n, c in agents],
            "crm": crm, "top_intents": [{"intent": i, "count": c} for i, c in intents if i]}


async def agent_metrics(db: AsyncSession, ws_id: str, agent_id: str, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    k = await _kpis(db, ws_id, since, agent_id)
    lat = (await db.execute(select(Call.metrics["avg_latency_ms"].astext).where(Call.agent_id == agent_id, Call.started_at >= since))).scalars().all()
    vals = [int(x) for x in lat if x and x != "null"]
    k["voice_avg_latency_ms"] = int(sum(vals) / len(vals)) if vals else None
    return k
