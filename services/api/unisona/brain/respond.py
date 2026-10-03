"""The brain: one response pipeline for every text channel (web, widget, WhatsApp, Telegram,
email, playground). Voice reuses the same building blocks in voice/session.py.

respond_events() is an async generator of events so callers can stream:
  {"type": "meta", conversation_id, contact_id}
  {"type": "token", "text": ...}       (web/widget/playground only)
  {"type": "tool", "name": ...}
  {"type": "final", reply: {...}}

Latency design: the hot path does as few database round-trips as possible (agent setup and
contact briefs are cached briefly, IDs are generated client-side, and webhooks/jobs/analytics
run after the reply in background tasks).
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, AsyncIterator

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal, new_id, utcnow
from ..knowledge import store
from ..knowledge.embed import embed
from ..knowledge.retrieve import retrieve
from ..log import get_logger
from ..models import (Agent, AgentKnowledge, Calendar, Contact, Conversation, Dataset, GoldenAnswer, Message, Trace, Workspace)
from ..providers.llm import LLMUnavailable, get_llm
from ..realtime import hub
from ..security.guard import SAFE_REFUSAL, check_input, leaked_canary, new_canary
from ..security.redact import redact
from . import cache
from . import handoff as handoff_mod
from .agent_config import fill_vars, normalize
from .identity import resolve_contact
from .lang import detect
from .memory import contact_brief
from .prompts import build_sections, join_sections
from .render import render
from .tools import ToolContext, execute, tool_schemas

log = get_logger("brain")
_SMALLTALK = re.compile(r"^\s*(hi+|hello+|hey+|hii+|namaste|namaskar|thanks?|thank you|thx|ok(ay)?|cool|great|bye|good (morning|evening|night)|yes|no|haan|nahi|ji|dhanyavad|shukriya)[\s!.?]*$", re.I)
MAX_TOOL_ROUNDS = 4
GOLDEN_KB = "golden_{agent_id}"
_bg: set[asyncio.Task] = set()


def background(coro) -> None:
    """Run side effects after the reply without blocking it; errors are logged, never raised."""
    task = asyncio.create_task(coro)
    _bg.add(task)

    def done(t: asyncio.Task):
        _bg.discard(t)
        if not t.cancelled() and t.exception():
            log.warning(f"background task failed: {t.exception()}")
    task.add_done_callback(done)


@dataclass
class Turn:
    ws: Workspace
    agent: Agent
    channel: str
    text: str
    identifiers: dict[str, str] = field(default_factory=dict)
    name: str | None = None
    channel_ref: str | None = None
    conversation_id: str | None = None
    use_draft: bool = False
    variables: dict[str, Any] = field(default_factory=dict)
    channel_msg_id: str | None = None


def agent_cfg(agent: Agent, use_draft: bool) -> dict:
    src = agent.config if (use_draft or not agent.published_config) else agent.published_config
    return normalize(src)


async def agent_kb_ids(db: AsyncSession, agent: Agent, cfg: dict) -> list[str]:
    linked = (await db.execute(select(AgentKnowledge.kb_id).where(AgentKnowledge.agent_id == agent.id))).scalars().all()
    return sorted(set(linked) | set(cfg["knowledge"].get("kb_ids") or []))


async def agent_setup(db: AsyncSession, ws: Workspace, agent: Agent, cfg: dict, channel: str) -> dict:
    """kb_ids, table schema cards, calendar presence and tool schemas — cached for 20s."""
    key = f"setup:{agent.id}:{channel}:{hash(str(cfg.get('tools')) + str(cfg['knowledge'].get('kb_ids')) + str(cfg.get('handoff', {}).get('enabled')))}"
    hit = cache.get(key)
    if hit:
        return hit
    kb_ids = await agent_kb_ids(db, agent, cfg)
    tables = [d.schema_card for d in (await db.execute(select(Dataset).where(Dataset.workspace_id == ws.id, Dataset.kb_id.in_(kb_ids or [""])))).scalars()]
    has_calendar = (await db.execute(select(func.count()).select_from(Calendar).where(Calendar.workspace_id == ws.id))).scalar() > 0
    tools = await tool_schemas(db, ws, cfg, has_tables=bool(tables), has_calendar=has_calendar, channel=channel)
    return cache.put(key, {"kb_ids": kb_ids, "tables": tables, "has_calendar": has_calendar, "tools": tools}, 20)


async def cached_brief(contact: Contact | None, conv_id: str) -> tuple[str, dict]:
    if not contact:
        return "", {}
    key = f"brief:{contact.id}:{conv_id}"
    hit = cache.get(key)
    if hit:
        return hit
    async with SessionLocal() as db2:
        c = await db2.get(Contact, contact.id)
        return cache.put(key, await contact_brief(db2, c, conv_id), 45)


async def get_or_create_conversation(db: AsyncSession, turn: Turn) -> tuple[Conversation | None, bool]:
    ws_id = turn.ws.id
    if turn.conversation_id:
        conv = await db.get(Conversation, turn.conversation_id)
        if conv and conv.workspace_id == ws_id and conv.status != "closed" and (
                conv.agent_id == turn.agent.id or (conv.meta or {}).get("squad_root") == turn.agent.id):
            return conv, False
    if turn.channel_ref:
        conv = (await db.execute(select(Conversation).where(
            Conversation.workspace_id == ws_id, Conversation.channel == turn.channel,
            (Conversation.agent_id == turn.agent.id) | (Conversation.meta["squad_root"].astext == turn.agent.id),
            Conversation.channel_ref == turn.channel_ref, Conversation.status != "closed",
            Conversation.last_message_at > utcnow() - timedelta(hours=24)).order_by(Conversation.last_message_at.desc()))).scalars().first()
        if conv:
            return conv, False
    return None, True


async def store_message(db: AsyncSession, conv: Conversation, role: str, content: str, *, ir: dict | None = None,
                        channel_msg_id: str | None = None, author_id: str | None = None, latency_ms: int | None = None,
                        trace_id: str | None = None, flagged: bool = False, flag_reason: str | None = None,
                        redact_pii: bool = False) -> Message:
    m = Message(id=new_id("msg"), workspace_id=conv.workspace_id, conversation_id=conv.id, role=role,
                content=redact(content) if redact_pii else content, ir=ir or {}, channel_msg_id=channel_msg_id, author_id=author_id,
                latency_ms=latency_ms, trace_id=trace_id, flagged=flagged, flag_reason=flag_reason, created_at=utcnow())
    db.add(m)
    conv.message_count = (conv.message_count or 0) + 1
    conv.last_message_at = utcnow()
    if role == "user" and not conv.subject:
        conv.subject = content[:120]
    event = {"type": "message.created", "conversation_id": conv.id, "message": {
        "id": m.id, "role": role, "content": m.content, "ir": m.ir, "created_at": m.created_at.isoformat(), "flagged": flagged}}
    await hub.publish(conv.workspace_id, {**event, "channel": conv.channel, "agent_id": conv.agent_id, "status": conv.status})
    await hub.publish(f"conv:{conv.id}", event)
    return m


async def golden_matches(agent: Agent, ws_id: str, qvec: list[float] | None, text: str) -> list[dict]:
    if qvec is None:
        [qvec] = await embed([text])
    hits = await store.dense_query(ws_id, qvec, [GOLDEN_KB.format(agent_id=agent.id)], k=3)
    return [{"question": h["meta"].get("question", ""), "answer": h["text"], "similarity": round(h["similarity"], 3), "id": h["id"]}
            for h in hits if h["similarity"] >= 0.72]


async def index_golden(db: AsyncSession, ga: GoldenAnswer) -> None:
    if not ga.agent_id:
        return
    [vec] = await embed([ga.question])
    if ga.status == "approved":
        await store.upsert(ga.workspace_id, [ga.id], [vec], [ga.answer],
                           [{"kb_id": GOLDEN_KB.format(agent_id=ga.agent_id), "question": ga.question[:500], "source_id": ga.id, "title": "Approved answer"}])
    else:
        await store.delete_where(ga.workspace_id, {"source_id": ga.id})


def _citations(chunks: list[dict], min_score: float) -> list[dict]:
    seen, out = set(), []
    for c in chunks:
        key = c["source_id"]
        if key in seen or ((c.get("dense") or 0) < min_score and not c.get("bm25")):
            continue
        seen.add(key)
        out.append({"title": c["title"], "url": c.get("url"), "source_id": c["source_id"], "snippet": c["text"][:240]})
    return out[:4]


async def _after_reply(ws_id: str, conv_id: str, *, created: bool, channel: str, agent_id: str, ended: bool, extract_memory: bool,
                       handoff_reason: str | None, brief: str) -> None:
    """Side effects that must not delay the customer: webhooks, jobs, handoff alerts."""
    from ..services.webhooks import emit
    from ..worker.queue import enqueue

    if created:
        await emit(ws_id, "conversation.started", {"conversation_id": conv_id, "channel": channel, "agent_id": agent_id})
    if handoff_reason:
        async with SessionLocal() as db:
            conv = await db.get(Conversation, conv_id)
            ws = await db.get(Workspace, ws_id)
            llm = await get_llm(db, ws, feature="handoff brief")
            await handoff_mod.create_handoff(db, conv, handoff_reason, llm, brief)
    if ended:
        await enqueue("conversation.analyze", {"conversation_id": conv_id}, workspace_id=ws_id)
    elif extract_memory:
        await enqueue("memory.extract", {"conversation_id": conv_id}, workspace_id=ws_id, max_attempts=1)


async def respond_events(db: AsyncSession, turn: Turn) -> AsyncIterator[dict[str, Any]]:
    t_start = time.perf_counter()
    timings: dict[str, int] = {}
    ws = turn.ws
    squad = (agent_cfg(turn.agent, turn.use_draft).get("squad") or {}).get("members")
    if squad and (turn.conversation_id or turn.channel_ref):  # a specialist agent may have taken over this conversation
        prior, _ = await get_or_create_conversation(db, turn)
        if prior and prior.agent_id != turn.agent.id:
            other = await db.get(Agent, prior.agent_id)
            if other and other.workspace_id == ws.id:
                turn.agent = other
                turn.conversation_id = prior.id
    cfg = agent_cfg(turn.agent, turn.use_draft)
    redact_pii = bool(cfg["guardrails"].get("pii_redaction"))

    # 1. Conversation (+ identity only when needed) and the guard check in parallel
    llm = await get_llm(db, ws, provider=cfg["llm"].get("provider"), model=cfg["llm"].get("model"), feature="AI replies")
    guard_task = asyncio.create_task(check_input(turn.text, llm.key.api_key if llm.provider == "groq" else None,
                                                 threshold=float(cfg["guardrails"].get("injection_threshold", 0.85))))
    t0 = time.perf_counter()
    conv, created = await get_or_create_conversation(db, turn)
    contact: Contact | None = None
    if conv and conv.contact_id:
        contact = await db.get(Contact, conv.contact_id)
    if (created or not contact) and turn.identifiers:
        contact = await resolve_contact(db, ws.id, turn.identifiers, name=turn.name, channel=turn.channel)
    if created:
        conv = Conversation(id=new_id("cv"), workspace_id=ws.id, agent_id=turn.agent.id, contact_id=contact.id if contact else None,
                            channel=turn.channel, channel_ref=turn.channel_ref, meta={"variables": turn.variables} if turn.variables else {},
                            message_count=0, started_at=utcnow(), last_message_at=utcnow(), status="ai", ai_enabled=True, subject="")
        db.add(conv)
    elif contact and conv.contact_id != contact.id:
        conv.contact_id = contact.id
    timings["conversation"] = int((time.perf_counter() - t0) * 1000)
    yield {"type": "meta", "conversation_id": conv.id, "contact_id": contact.id if contact else None, "created": created}

    language = detect(turn.text)
    conv.language = language
    guard = await guard_task
    timings["guard"] = int((time.perf_counter() - t_start) * 1000) - timings["conversation"]
    user_msg = await store_message(db, conv, "user", turn.text, channel_msg_id=turn.channel_msg_id, flagged=guard.blocked,
                                   flag_reason="prompt_injection" if guard.blocked else None, redact_pii=redact_pii)

    async def finish(text: str, *, extra_ir: dict | None = None, trace: dict | None = None, handoff_reason: str | None = None,
                     ended: str | None = None, brief: str = "") -> dict:
        rendered = render(turn.channel, text)
        ir = {"options": rendered["options"], **(extra_ir or {})}
        tr_id = None
        if trace is not None:
            tr_id = new_id("tr")
            db.add(Trace(id=tr_id, workspace_id=ws.id, conversation_id=conv.id, data={**trace, "timings_ms": {**timings, **trace.get("timings_ms", {})}},
                         created_at=utcnow()))
        latency = int((time.perf_counter() - t_start) * 1000)
        msg = await store_message(db, conv, "assistant", rendered["text"], ir=ir, latency_ms=latency, trace_id=tr_id, redact_pii=redact_pii)
        if ended:
            conv.status, conv.ended_at, conv.outcome = "closed", utcnow(), ended
        if handoff_reason:
            conv.status = "handoff_pending"
        await db.commit()
        background(_after_reply(ws.id, conv.id, created=created, channel=turn.channel, agent_id=turn.agent.id, ended=bool(ended),
                                extract_memory=bool(contact and cfg["memory"].get("remember_facts", True) and conv.message_count % 6 == 0),
                                handoff_reason=handoff_reason, brief=brief))
        return {"conversation_id": conv.id, "message_id": msg.id, "text": rendered["text"], "options": rendered["options"],
                "citations": ir.get("citations", []), "handoff": bool(handoff_reason) or conv.status == "handoff_pending",
                "ended": bool(ended), "trace_id": tr_id, "latency_ms": latency, "language": language,
                "contact_id": contact.id if contact else None, "status": conv.status}

    if guard.blocked:
        text = SAFE_REFUSAL["hi" if language in {"hi", "hinglish"} else "en"]
        yield {"type": "final", "reply": await finish(text, trace={"guard": guard.__dict__, "blocked": True})}
        return

    # Opt-out ("stop", "don't message me", "call mat karo"): honour immediately, before anything else.
    from ..services import compliance

    if compliance.settings_for(ws)["auto_opt_out"] and compliance.is_opt_out(turn.text) and turn.channel not in {"playground"}:
        await compliance.opt_out(db, ws, contact, turn.channel, (turn.identifiers or {}).get("phone") or (turn.identifiers or {}).get("email"))
        text = compliance.OPT_OUT_REPLY.get(language, compliance.OPT_OUT_REPLY["en"])
        yield {"type": "final", "reply": await finish(text, trace={"opt_out": True}, ended="opted_out")}
        return

    # Live emotion: shown in the inbox/live monitor; sustained anger escalates to a human.
    from . import emotion

    emo = emotion.score(turn.text)
    emo_hist, emo_escalate = emotion.trend((conv.meta or {}).get("emotion") or [], emo)
    conv.meta = {**(conv.meta or {}), "emotion": emo_hist}
    if emo["label"] != "neutral":
        await hub.publish(ws.id, {"type": "conversation.emotion", "conversation_id": conv.id, **emo})

    # 2. Human in control → don't let the AI talk over them
    if conv.status in {"human", "handoff_pending"} and not conv.ai_enabled:
        await db.commit()
        await hub.publish(ws.id, {"type": "conversation.awaiting_human", "conversation_id": conv.id})
        yield {"type": "final", "reply": {"conversation_id": conv.id, "message_id": user_msg.id, "text": "", "options": [], "citations": [],
                                          "handoff": True, "ended": False, "awaiting_human": True, "status": conv.status,
                                          "contact_id": contact.id if contact else None}}
        return

    if not llm.available:
        text = "Our assistant isn't configured yet. A team member will get back to you shortly."
        yield {"type": "final", "reply": await finish(text, trace={"error": "no_llm_key"}, handoff_reason="ai_unavailable")}
        return

    # 3. History, setup, memory and knowledge (in parallel where safe)
    t0 = time.perf_counter()
    history_rows: list[Message] = []
    if not created:
        history_rows = list(reversed((await db.execute(select(Message).where(
            Message.conversation_id == conv.id, Message.id != user_msg.id, Message.role.in_(["user", "assistant", "human"]))
            .order_by(Message.created_at.desc()).limit(14))).scalars().all()))
    prior_user = [m.content for m in history_rows if m.role == "user"]
    low_conf_streak = int((conv.meta or {}).get("low_conf_streak", 0))
    trigger = handoff_mod.detect_trigger(turn.text, prior_user, cfg, low_conf_streak)
    if trigger == "customer_requested" or (trigger and trigger.startswith("policy_topic")):
        msg = fill_vars(cfg["handoff"]["message"], cfg)
        yield {"type": "final", "reply": await finish(msg, trace={"handoff_trigger": trigger}, handoff_reason=trigger)}
        return

    setup = await agent_setup(db, ws, turn.agent, cfg, turn.channel)
    kb_ids = setup["kb_ids"]
    smalltalk = bool(_SMALLTALK.match(turn.text)) and len(turn.text) < 40
    mode = cfg["knowledge"].get("mode", "auto")
    if mode == "auto":
        mode = "deep" if (turn.channel not in {"voice", "phone"} and len(turn.text) > 80) else "fast"
    query = turn.text if len(turn.text) >= 25 or not prior_user else f"{prior_user[-1]} {turn.text}"

    async def _retrieval():
        if smalltalk or not kb_ids:
            return None
        async with SessionLocal() as db2:
            return await retrieve(db2, ws.id, kb_ids, query, k=int(cfg["knowledge"].get("k", 5)), mode=mode,
                                  policies=cfg["knowledge"].get("policies"))

    async def _golden():
        return [] if smalltalk else await golden_matches(turn.agent, ws.id, None, turn.text)

    want_brief = bool(cfg["memory"].get("cross_channel", True))
    retrieval, golden, (brief, brief_meta) = await asyncio.gather(
        _retrieval(), _golden(), cached_brief(contact, conv.id) if want_brief else asyncio.sleep(0, result=("", {})))
    timings["context"] = int((time.perf_counter() - t0) * 1000)

    min_conf = float(cfg["knowledge"].get("min_confidence", 0.32))
    knowledge = [c.__dict__ for c in retrieval.chunks] if retrieval else []
    confident = bool(knowledge) and (retrieval.confidence >= min_conf)
    usable_knowledge = [c for c in knowledge if (c.get("dense") or 0) >= min_conf * 0.8 or (c.get("bm25") or 0) > 0]
    streak = 0 if (smalltalk or confident or golden or not kb_ids) else low_conf_streak + 1
    conv.meta = {**(conv.meta or {}), "low_conf_streak": streak}

    canary = new_canary()
    sections = build_sections(cfg, channel=turn.channel, contact_brief=brief, knowledge=usable_knowledge, golden=golden,
                              tables=setup["tables"], canary=canary, language_hint=language, timezone=ws.settings.get("timezone", "Asia/Kolkata"),
                              extra_vars={**((conv.meta or {}).get("variables") or {}), **turn.variables})
    from . import flows

    flow_state = None
    if flows.enabled(cfg):
        flow_state = (conv.meta or {}).get("flow") or flows.initial_state(cfg)
        conv.meta = {**(conv.meta or {}), "flow": flow_state}
        sections.append(("flow", flows.prompt_section(cfg, flow_state)))
    messages: list[dict[str, Any]] = [{"role": "system", "content": join_sections(sections)}]
    for m in history_rows:
        messages.append({"role": "user" if m.role == "user" else "assistant", "content": m.content})
    messages.append({"role": "user", "content": turn.text})

    ctx = ToolContext(db=db, ws=ws, agent=turn.agent, cfg=cfg, conversation=conv, contact=contact, channel=turn.channel, llm=llm, kb_ids=kb_ids)
    tools = list(setup["tools"]) + (flows.tool_schemas(cfg, flow_state) if flow_state else [])

    # 4. LLM with tool loop (streams final text)
    t0 = time.perf_counter()
    final_text, rounds = "", []
    tokens_in = tokens_out = 0
    cost = 0.0
    stream_ok = turn.channel not in {"voice", "phone", "whatsapp", "telegram", "email"}
    try:
        for rnd in range(MAX_TOOL_ROUNDS + 1):
            result, streamed = None, []
            async for kind, payload in llm.stream_chat(messages, tools=tools if rnd < MAX_TOOL_ROUNDS else None,
                                                       temperature=float(cfg["llm"].get("temperature", 0.3)), max_tokens=900, agent_id=turn.agent.id):
                if kind == "text":
                    streamed.append(payload)
                    if stream_ok:
                        yield {"type": "token", "text": payload}
                else:
                    result = payload
            tokens_in += result.input_tokens
            tokens_out += result.output_tokens
            cost += result.cost_usd
            rounds.append({"round": rnd, "tool_calls": [{"name": c["name"], "arguments": c["arguments"]} for c in result.tool_calls],
                           "latency_ms": result.latency_ms})
            if not result.tool_calls:
                final_text = result.content
                break
            messages.append(result.raw_message)
            if streamed and stream_ok:
                yield {"type": "reset"}
            for call in result.tool_calls:
                yield {"type": "tool", "name": call["name"]}
                out = await execute(ctx, call["name"], call["arguments"])
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": out[:6000]})
    except LLMUnavailable:
        final_text = "I'm having trouble right now. A team member will follow up shortly."
        ctx.state["handoff_reason"] = "ai_unavailable"
    except Exception as e:
        log.error(f"LLM error for {conv.id}: {e}")
        final_text = "Sorry, I ran into a problem answering that. Could you rephrase, or would you like me to connect you with our team?"
    timings["llm"] = int((time.perf_counter() - t0) * 1000)
    if ctx.contact and not contact:
        contact = ctx.contact

    if leaked_canary(final_text, canary):
        log.warning(f"Canary leaked in {conv.id}; reply blocked")
        final_text = SAFE_REFUSAL["en"]
        user_msg.flagged, user_msg.flag_reason = True, "prompt_leak_attempt"
    if not final_text.strip():
        final_text = fill_vars(cfg["handoff"]["message"], cfg) if ctx.state.get("handoff_reason") else "Could you tell me a little more?"

    citations = _citations(usable_knowledge, min_conf) if cfg["knowledge"].get("cite_sources", True) else []
    trace = {
        "channel": turn.channel, "language": language, "router": "smalltalk" if smalltalk else (retrieval.mode if retrieval else "no_kb"),
        "guard": {"score": guard.score, "model_used": guard.model_used, "reasons": guard.reasons},
        "retrieval": retrieval.to_dict() if retrieval else None, "extra_retrievals": ctx.state.get("extra_retrievals", []),
        "golden": golden, "confidence": round(retrieval.confidence, 3) if retrieval else None, "confident": confident,
        "memory": brief_meta, "memory_brief": brief[:1500],
        "prompt_sections": [{"name": n, "chars": len(t), "text": t if n != "safety" else t.replace(canary, "[canary]")} for n, t in sections],
        "tools": ctx.state.get("tool_log", []), "rounds": rounds, "sql": ctx.state.get("sql", []),
        "llm": {"provider": llm.provider, "model": llm.model, "key_source": llm.key.source, "tokens_in": tokens_in,
                "tokens_out": tokens_out, "cost_usd": round(cost, 6)},
        "handoff_trigger": trigger,
    }
    handoff_reason = ctx.state.get("handoff_reason") or (trigger if trigger in {"frustration", "repeated_question", "low_confidence"} else None)
    if not handoff_reason and emo_escalate and cfg["handoff"].get("enabled", True) and cfg["handoff"].get("on_frustration", True):
        handoff_reason = "frustration"
    trace["emotion"] = emo
    if ctx.state.get("flow_state"):
        trace["flow"] = ctx.state["flow_state"]
    switch = ctx.state.get("switch_agent")
    if switch:  # squads: the specialist owns the conversation from the next message on; memory and history carry over
        root = (conv.meta or {}).get("squad_root") or turn.agent.id
        conv.meta = {**(conv.meta or {}), "squad_root": root,
                     "squad_history": [*((conv.meta or {}).get("squad_history") or []), {"from": turn.agent.id, "to": switch["agent_id"], "reason": switch.get("reason")}]}
        conv.agent_id = switch["agent_id"]
        trace["agent_transfer"] = switch
        from ..services.webhooks import emit

        background(emit(ws.id, "agent.transferred", {"conversation_id": conv.id, "from_agent": turn.agent.id, "to_agent": switch["agent_id"],
                                                      "reason": switch.get("reason")}))
    if ctx.state.get("lead_captured") or ctx.state.get("appointment_booked"):
        cache.invalidate_prefix(f"brief:{contact.id}" if contact else "brief:")
    reply = await finish(final_text, extra_ir={"citations": citations, "confidence": trace["confidence"]}, trace=trace,
                         handoff_reason=handoff_reason, ended=ctx.state.get("end") or (f"flow:{ctx.state['flow_end']}" if ctx.state.get("flow_end") else None),
                         brief=brief)
    reply["tools_used"] = [t["tool"] for t in ctx.state.get("tool_log", [])]
    yield {"type": "final", "reply": reply}


async def respond(db: AsyncSession, turn: Turn) -> dict[str, Any]:
    reply: dict[str, Any] = {}
    async for ev in respond_events(db, turn):
        if ev["type"] == "final":
            reply = ev["reply"]
    return reply


async def greeting(db: AsyncSession, agent: Agent, *, use_draft: bool = False, contact: Contact | None = None) -> str:
    cfg = agent_cfg(agent, use_draft)
    text = fill_vars(cfg["persona"].get("greeting") or "Hi! How can I help you today?", cfg)
    if contact and contact.name:
        first = contact.name.split()[0]
        if first.lower() not in text.lower():
            text = text.replace("Hi!", f"Hi {first}!").replace("Hello!", f"Hello {first}!")
    return text
