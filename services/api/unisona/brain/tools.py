"""Agent tools, shared by text and voice channels.

Each tool has an OpenAI function schema and an async executor that receives a
ToolContext (workspace, agent, conversation, contact, channel). Tools only ever touch
the current workspace and the current contact.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import utcnow
from ..log import get_logger
from ..models import (Activity, Agent, Appointment, Calendar, Contact, Conversation, Dataset, Deal, Pipeline, Task, Tool, Workspace)
from ..security.guard import fence_untrusted

log = get_logger("tools")


@dataclass
class ToolContext:
    db: AsyncSession
    ws: Workspace
    agent: Agent
    cfg: dict
    conversation: Conversation
    contact: Contact | None
    channel: str
    llm: Any = None
    state: dict = field(default_factory=dict)
    kb_ids: list[str] = field(default_factory=list)


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties, "required": required or []}}}


BUILTIN_SCHEMAS: dict[str, dict] = {
    "search_knowledge": _fn("search_knowledge", "Search the business's knowledge base for more information. Use when the provided KNOWLEDGE does not answer the question.",
                            {"query": {"type": "string", "description": "What to search for"}}, ["query"]),
    "query_table": _fn("query_table", "Run a read-only SQL SELECT (DuckDB syntax) against the business's structured data tables listed in STRUCTURED DATA. Use ILIKE for fuzzy text matches.",
                       {"sql": {"type": "string", "description": "A single SELECT statement"}}, ["sql"]),
    "handoff_to_human": _fn("handoff_to_human", "Transfer the conversation to a human team member.",
                            {"reason": {"type": "string", "description": "Why a human is needed"}}, ["reason"]),
    "capture_lead": _fn("capture_lead", "Save or update the customer's details in the CRM when they share them, e.g. name, phone, email, company, interest.",
                        {"name": {"type": "string"}, "phone": {"type": "string"}, "email": {"type": "string"},
                         "company": {"type": "string"}, "interest": {"type": "string", "description": "What they're interested in"},
                         "notes": {"type": "string"}}),
    "create_task": _fn("create_task", "Create a follow-up task for the team (e.g. call back, send quote).",
                       {"title": {"type": "string"}, "due_in_hours": {"type": "number"}, "notes": {"type": "string"}}, ["title"]),
    "check_availability": _fn("check_availability", "List free appointment slots on a date.",
                              {"date": {"type": "string", "description": "YYYY-MM-DD"}}, ["date"]),
    "book_appointment": _fn("book_appointment", "Book an appointment slot after the customer confirms the time.",
                            {"start": {"type": "string", "description": "Start time, ISO format YYYY-MM-DDTHH:MM (business local time)"},
                             "name": {"type": "string"}, "phone": {"type": "string"}, "email": {"type": "string"},
                             "purpose": {"type": "string"}}, ["start"]),
    "send_message": _fn("send_message", "Send the customer a message on another channel (e.g. a link or details on WhatsApp/Telegram/email). Use during calls instead of reading links aloud.",
                        {"channel": {"type": "string", "enum": ["whatsapp", "telegram", "email", "sms"]}, "text": {"type": "string"}}, ["channel", "text"]),
    "end_conversation": _fn("end_conversation", "End the conversation/call politely once the customer is done or says goodbye.",
                            {"disposition": {"type": "string", "description": "Outcome label"}}),
    "get_datetime": _fn("get_datetime", "Get the current date and time in the business's timezone.", {}),
    "send_payment_link": _fn("send_payment_link", "Create a secure payment link for an amount the customer agreed to pay and send it to them (WhatsApp/SMS/email). Never collect card details yourself.",
                             {"amount": {"type": "number", "description": "Amount in the currency's main unit, e.g. 1499 for Rs 1499"},
                              "description": {"type": "string", "description": "What the payment is for"},
                              "channel": {"type": "string", "enum": ["whatsapp", "sms", "email", "telegram"]},
                              "currency": {"type": "string", "description": "INR, USD, ... (default from business settings)"}}, ["amount", "description"]),
}

# Tools whose parameters depend on the agent's configuration (built per agent in tool_schemas).
DYNAMIC_TOOLS = {"transfer_call", "transfer_to_agent", "press_keys"}


async def _tz(ctx: ToolContext) -> str:
    if ctx.cfg.get("calendar_id"):
        cal = await ctx.db.get(Calendar, ctx.cfg["calendar_id"])
        if cal:
            return cal.timezone
    return ctx.ws.settings.get("timezone", "Asia/Kolkata")


async def _calendar(ctx: ToolContext) -> Calendar | None:
    if ctx.cfg.get("calendar_id"):
        cal = await ctx.db.get(Calendar, ctx.cfg["calendar_id"])
        if cal and cal.workspace_id == ctx.ws.id:
            return cal
    return (await ctx.db.execute(select(Calendar).where(Calendar.workspace_id == ctx.ws.id).limit(1))).scalar_one_or_none()


async def free_slots(db: AsyncSession, cal: Calendar, day: datetime, ws: Workspace | None = None) -> list[datetime]:
    tz = ZoneInfo(cal.timezone)
    wd = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][day.weekday()]
    windows = (cal.availability or {}).get(wd, [])
    start_day = datetime(day.year, day.month, day.day, tzinfo=tz)
    booked = (await db.execute(select(Appointment).where(Appointment.calendar_id == cal.id, Appointment.status == "booked",
                                                         Appointment.start_at >= start_day, Appointment.start_at < start_day + timedelta(days=1)))).scalars().all()
    slots = []
    now = utcnow()
    busy: list[tuple[datetime, datetime]] = []
    if ws is not None:  # Google Calendar busy times block slots too (two-way sync)
        from ..services.integrations import google_busy

        busy = await google_busy(db, ws, start_day, start_day + timedelta(days=1))
    for a, b in windows:
        h1, m1 = map(int, a.split(":"))
        h2, m2 = map(int, b.split(":"))
        t = start_day.replace(hour=h1, minute=m1)
        end = start_day.replace(hour=h2, minute=m2)
        while t + timedelta(minutes=cal.slot_minutes) <= end:
            clash = any(ap.start_at < t + timedelta(minutes=cal.slot_minutes) and ap.end_at > t for ap in booked) or \
                any(b0 < t + timedelta(minutes=cal.slot_minutes) and b1 > t for b0, b1 in busy)
            if not clash and t > now:
                slots.append(t)
            t += timedelta(minutes=cal.slot_minutes + cal.buffer_minutes)
    return slots


async def _ensure_contact(ctx: ToolContext) -> Contact:
    if ctx.contact:
        return ctx.contact
    c = Contact(workspace_id=ctx.ws.id, source_channel=ctx.channel)
    ctx.db.add(c)
    await ctx.db.flush()
    ctx.contact = c
    ctx.conversation.contact_id = c.id
    return c


async def execute(ctx: ToolContext, name: str, args: dict[str, Any]) -> str:
    """Run a tool; always returns a string for the model (errors included, never raises)."""
    try:
        if name in _BUILTIN:
            result = await _BUILTIN[name](ctx, **{k: v for k, v in (args or {}).items() if v not in (None, "")})
        else:
            result = await _custom(ctx, name, args or {})
        ctx.state.setdefault("tool_log", []).append({"tool": name, "args": args, "ok": True, "result": str(result)[:600]})
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    except TypeError as e:
        msg = f"Invalid arguments for {name}: {e}"
    except Exception as e:
        msg = f"Tool {name} failed: {e}"
        log.warning(msg)
    ctx.state.setdefault("tool_log", []).append({"tool": name, "args": args, "ok": False, "result": msg})
    return msg


async def t_search_knowledge(ctx: ToolContext, query: str) -> str:
    from ..knowledge.retrieve import retrieve

    res = await retrieve(ctx.db, ctx.ws.id, ctx.kb_ids, query, k=5, mode="deep" if ctx.channel not in {"voice", "phone"} else "fast",
                         policies=ctx.cfg["knowledge"].get("policies"))
    ctx.state.setdefault("extra_retrievals", []).append(res.to_dict())
    if not res.chunks:
        return "No relevant information found in the knowledge base."
    return "\n\n".join(fence_untrusted(c.title, c.text[:1200]) for c in res.chunks)


async def t_query_table(ctx: ToolContext, sql: str) -> str:
    from ..knowledge.tables import run_query

    datasets = (await ctx.db.execute(select(Dataset).where(Dataset.workspace_id == ctx.ws.id, Dataset.kb_id.in_(ctx.kb_ids or [""])))).scalars().all()
    if not datasets:
        return "No structured tables are available."
    referenced = {t.lower() for t in re.findall(r'\b(?:from|join)\s+"?([A-Za-z_]\w*)', sql, re.I)}
    ds = next((d for d in datasets if d.table_name.lower() in referenced), datasets[0])
    allowed = {d.table_name for d in datasets if d.kb_id == ds.kb_id}
    result = await run_query(ds.kb_id, sql, allowed)
    ctx.state.setdefault("sql", []).append(result.get("sql"))
    if not result["rows"]:
        return "The query returned no rows."
    return fence_untrusted(f"table {ds.table_name}", json.dumps(result["rows"][:25], ensure_ascii=False, default=str))


async def t_handoff(ctx: ToolContext, reason: str = "customer needs a human") -> str:
    ctx.state["handoff_reason"] = reason
    return "Handoff initiated. Tell the customer a team member will join shortly. Do not promise exact timings."


async def t_capture_lead(ctx: ToolContext, name: str | None = None, phone: str | None = None, email: str | None = None,
                         company: str | None = None, interest: str | None = None, notes: str | None = None) -> str:
    from .identity import add_identity

    c = await _ensure_contact(ctx)
    if name:
        c.name = name[:200]
    if phone:
        await add_identity(ctx.db, c, "phone", phone)
    if email:
        await add_identity(ctx.db, c, "email", email)
    fields = dict(c.fields or {})
    if company:
        fields["company"] = company
    if interest:
        fields["interest"] = interest
    if notes:
        fields["notes"] = notes
    c.fields = fields
    if interest:
        pl = (await ctx.db.execute(select(Pipeline).where(Pipeline.workspace_id == ctx.ws.id).limit(1))).scalar_one_or_none()
        if pl:
            open_deal = (await ctx.db.execute(select(Deal).where(Deal.contact_id == c.id, Deal.status == "open"))).scalars().first()
            if not open_deal:
                ctx.db.add(Deal(workspace_id=ctx.ws.id, pipeline_id=pl.id, stage=pl.stages[0]["id"] if pl.stages else "new",
                                title=f"{name or c.name or 'Lead'}: {interest}"[:200], contact_id=c.id))
    ctx.db.add(Activity(workspace_id=ctx.ws.id, contact_id=c.id, type="lead.captured", title="Details captured by AI agent",
                        data={"name": name, "phone": phone, "email": email, "interest": interest}, actor=f"agent:{ctx.agent.id}"))
    await ctx.db.commit()
    ctx.state["lead_captured"] = True
    return "Saved to CRM."


async def t_create_task(ctx: ToolContext, title: str, due_in_hours: float = 24, notes: str = "") -> str:
    c = await _ensure_contact(ctx)
    ctx.db.add(Task(workspace_id=ctx.ws.id, title=title[:300], notes=notes, due_at=utcnow() + timedelta(hours=float(due_in_hours or 24)),
                    contact_id=c.id, conversation_id=ctx.conversation.id, created_by="ai"))
    await ctx.db.commit()
    return f"Task created: {title}"


async def _calcom(ctx: ToolContext):
    if ctx.cfg.get("calendar_source") != "calcom":
        return None
    from ..services.integrations import client_for

    return await client_for(ctx.db, ctx.ws, "calcom")


async def t_check_availability(ctx: ToolContext, date: str) -> str:
    cc = await _calcom(ctx)
    if cc:
        tz = ctx.ws.settings.get("timezone", "Asia/Kolkata")
        slots = await cc.slots(datetime.fromisoformat(date[:10]), tz)
        if not slots:
            return f"No free slots on {date}. Suggest another day."
        return f"Free slots on {date} ({tz}): " + ", ".join(s[11:16] for s in slots[:12]) + ". Book with the full date and time."
    cal = await _calendar(ctx)
    if not cal:
        return "No booking calendar is configured. Offer to take their details so the team can call back."
    try:
        day = datetime.fromisoformat(date[:10])
    except ValueError:
        return "Please provide the date as YYYY-MM-DD."
    slots = await free_slots(ctx.db, cal, day, ctx.ws)
    if not slots:
        return f"No free slots on {day:%A %d %B}. Suggest another day."
    return f"Free slots on {day:%A %d %B} ({cal.timezone}): " + ", ".join(s.strftime("%H:%M") for s in slots[:12])


async def t_book_appointment(ctx: ToolContext, start: str, name: str | None = None, phone: str | None = None,
                             email: str | None = None, purpose: str | None = None) -> str:
    cc = await _calcom(ctx)
    if cc:
        if name or phone or email:
            await t_capture_lead(ctx, name=name, phone=phone, email=email)
        c = await _ensure_contact(ctx)
        tz = ctx.ws.settings.get("timezone", "Asia/Kolkata")
        st = datetime.fromisoformat(start.replace("Z", "")).replace(tzinfo=ZoneInfo(tz))
        booking = await cc.book(st.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"), c.name or name or "", c.email or email or "", tz, c.phone)
        ctx.db.add(Activity(workspace_id=ctx.ws.id, contact_id=c.id, type="appointment.booked", title=f"Booked via Cal.com {st:%d %b %H:%M}",
                            data={"calcom": booking.get("uid")}, actor=f"agent:{ctx.agent.id}"))
        await ctx.db.commit()
        ctx.state["appointment_booked"] = booking.get("uid") or "calcom"
        return f"Booked for {st:%A %d %B at %H:%M} ({tz}). Confirm this to the customer."
    cal = await _calendar(ctx)
    if not cal:
        return "No booking calendar is configured."
    tz = ZoneInfo(cal.timezone)
    try:
        st = datetime.fromisoformat(start.replace("Z", ""))
        st = st.replace(tzinfo=tz) if st.tzinfo is None else st
    except ValueError:
        return "Invalid time format. Use YYYY-MM-DDTHH:MM."
    free = await free_slots(ctx.db, cal, st.astimezone(tz), ctx.ws)
    if not any(abs((s - st).total_seconds()) < 60 for s in free):
        return "That slot is not available. Call check_availability and offer free slots."
    if name or phone or email:
        await t_capture_lead(ctx, name=name, phone=phone, email=email)
    c = await _ensure_contact(ctx)
    appt = Appointment(workspace_id=ctx.ws.id, calendar_id=cal.id, contact_id=c.id,
                       title=(purpose or f"Appointment with {c.name or 'customer'}")[:200], start_at=st,
                       end_at=st + timedelta(minutes=cal.slot_minutes), source=f"agent:{ctx.channel}")
    ctx.db.add(appt)
    ctx.db.add(Activity(workspace_id=ctx.ws.id, contact_id=c.id, type="appointment.booked", title=f"Booked {st:%d %b %H:%M}",
                        actor=f"agent:{ctx.agent.id}"))
    await ctx.db.commit()
    ctx.state["appointment_booked"] = appt.id
    from ..services.webhooks import emit

    await emit(ctx.ws.id, "appointment.booked", {"appointment_id": appt.id, "contact_id": c.id, "start": st.isoformat()})
    return f"Booked for {st:%A %d %B at %H:%M} ({cal.timezone}). Confirm this to the customer."


async def t_send_message(ctx: ToolContext, channel: str, text: str) -> str:
    from ..channels.outbound import send_to_contact

    c = await _ensure_contact(ctx)
    ok, detail = await send_to_contact(ctx.db, ctx.ws, ctx.agent, c, channel, text)
    if ok:
        ctx.db.add(Activity(workspace_id=ctx.ws.id, contact_id=c.id, type="message.cross_channel",
                            title=f"Sent on {channel} during {ctx.channel} conversation", data={"text": text[:500]}))
        await ctx.db.commit()
        return f"Sent on {channel}."
    await t_create_task(ctx, f"Send to customer via {channel}: {text[:120]}", 2, detail)
    return f"Could not send on {channel} ({detail}). A task was created for the team; tell the customer they'll receive it shortly."


async def t_end(ctx: ToolContext, disposition: str = "resolved") -> str:
    ctx.state["end"] = disposition
    return "Conversation will end after your goodbye. Say a brief, warm goodbye."


async def t_send_payment_link(ctx: ToolContext, amount: float, description: str, channel: str | None = None, currency: str | None = None) -> str:
    from ..services.payments import create_and_send

    c = await _ensure_contact(ctx)
    channel = channel or ("whatsapp" if ctx.channel in {"whatsapp", "voice", "phone"} else ctx.channel if ctx.channel in {"sms", "email", "telegram"} else "email")
    ok, detail, link = await create_and_send(ctx.db, ctx.ws, ctx.agent, c, float(amount), description, channel=channel, currency=currency,
                                             conversation_id=ctx.conversation.id)
    if link and ctx.channel in {"web", "widget", "playground"}:
        return f"Payment link created: {link.url} (share it with the customer)."
    return f"Payment link sent on {channel}." if ok else f"Could not send the payment link: {detail}"


async def t_transfer_call(ctx: ToolContext, destination: str, reason: str = "") -> str:
    targets = {t.get("name"): t for t in (ctx.cfg.get("handoff") or {}).get("transfer_targets") or []}
    target = targets.get(destination) or next(iter(targets.values()), None)
    if not target:
        ctx.state["handoff_reason"] = reason or "transfer requested"
        return "No transfer destination is configured; a team member has been notified instead."
    ctx.state["transfer"] = {"name": target.get("name"), "number": target.get("number"), "mode": target.get("mode", "warm"), "reason": reason}
    if ctx.channel not in {"voice", "phone"}:
        ctx.state["handoff_reason"] = f"transfer:{target.get('name')}"
        return f"The {target.get('name')} team has been notified and will take over this chat."
    return f"Transferring to {target.get('name')}. Tell the customer you are connecting them now and to stay on the line."


async def t_transfer_to_agent(ctx: ToolContext, agent: str, reason: str = "") -> str:
    members = {m.get("name"): m for m in (ctx.cfg.get("squad") or {}).get("members") or []}
    m = members.get(agent)
    if not m:
        return f"Unknown specialist '{agent}'."
    target = await ctx.db.get(Agent, m.get("agent_id"))
    if not target or target.workspace_id != ctx.ws.id:
        return "That specialist is not available."
    ctx.state["switch_agent"] = {"agent_id": target.id, "name": target.name, "reason": reason}
    return f"Handing over to {target.name}. Briefly tell the customer you're passing them to our {agent} specialist who can help."


async def t_press_keys(ctx: ToolContext, digits: str) -> str:
    clean = "".join(ch for ch in str(digits) if ch in "0123456789*#w")
    if not clean:
        return "No valid keys."
    ctx.state["dtmf"] = clean
    return f"Pressed {clean}. Wait silently for the menu to respond."


async def t_flow_goto(ctx: ToolContext, step: str, reason: str = "") -> str:
    from . import flows

    state = (ctx.conversation.meta or {}).get("flow") or flows.initial_state(ctx.cfg)
    new, msg = flows.goto(ctx.cfg, state, step)
    ctx.conversation.meta = {**(ctx.conversation.meta or {}), "flow": new}
    ctx.state["flow_state"] = new
    node = flows.current(ctx.cfg, new) or {}
    if node.get("action") == "handoff":
        ctx.state["handoff_reason"] = f"flow:{node.get('id')}"
    elif node.get("action") == "end":
        ctx.state["flow_end"] = node.get("id")
    return msg


async def t_flow_save(ctx: ToolContext, field: str, value: str) -> str:
    from . import flows

    state = (ctx.conversation.meta or {}).get("flow") or flows.initial_state(ctx.cfg)
    new, msg = flows.save(ctx.cfg, state, field, value)
    ctx.conversation.meta = {**(ctx.conversation.meta or {}), "flow": new}
    ctx.state["flow_state"] = new
    c = await _ensure_contact(ctx)
    c.fields = {**(c.fields or {}), field: value}
    return msg


async def t_datetime(ctx: ToolContext) -> str:
    tz = await _tz(ctx)
    return datetime.now(ZoneInfo(tz)).strftime(f"%A %d %B %Y, %H:%M ({tz})")


_BUILTIN = {
    "search_knowledge": t_search_knowledge, "query_table": t_query_table, "handoff_to_human": t_handoff,
    "capture_lead": t_capture_lead, "create_task": t_create_task, "check_availability": t_check_availability,
    "book_appointment": t_book_appointment, "send_message": t_send_message, "end_conversation": t_end, "get_datetime": t_datetime,
    "send_payment_link": t_send_payment_link, "transfer_call": t_transfer_call, "transfer_to_agent": t_transfer_to_agent,
    "press_keys": t_press_keys, "flow_goto": t_flow_goto, "flow_save": t_flow_save,
}


async def _custom(ctx: ToolContext, name: str, args: dict) -> str:
    tool = (await ctx.db.execute(select(Tool).where(Tool.workspace_id == ctx.ws.id, Tool.name == name, Tool.enabled.is_(True)))).scalar_one_or_none()
    if not tool:
        return f"Unknown tool {name}."
    if tool.type == "mcp":
        from ..services.mcp_client import call_mcp_tool

        return await call_mcp_tool(ctx.ws, tool, args)
    cfg = tool.config or {}
    secret = {}
    if tool.enc_secret:
        from ..security.crypto import decrypt_json

        secret = decrypt_json(ctx.ws.id, ctx.ws.settings["dek"], f"tool:{tool.id}", tool.enc_secret)
    variables = {**{k: str(v) for k, v in args.items()}, "contact_phone": (ctx.contact.phone if ctx.contact else "") or "",
                 "contact_email": (ctx.contact.email if ctx.contact else "") or "", "conversation_id": ctx.conversation.id, **secret}

    def sub(s: str) -> str:
        return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: variables.get(m.group(1), ""), s or "")

    method = (cfg.get("method") or "POST").upper()
    url = sub(cfg.get("url", ""))
    if not url.startswith("https://") and not url.startswith("http://"):
        return "Tool URL is invalid."
    headers = {k: sub(v) for k, v in (cfg.get("headers") or {}).items()}
    async with httpx.AsyncClient(timeout=float(cfg.get("timeout_s", 10))) as c:
        if method == "GET":
            r = await c.get(url, params=args, headers=headers)
        else:
            r = await c.request(method, url, json=args, headers=headers)
    body = r.text[:3000]
    return fence_untrusted(f"tool {name} (HTTP {r.status_code})", body)


async def tool_schemas(db: AsyncSession, ws: Workspace, cfg: dict, *, has_tables: bool, has_calendar: bool, channel: str) -> list[dict]:
    enabled = set(cfg.get("tools", {}).get("builtin") or [])
    schemas = []
    for name, schema in BUILTIN_SCHEMAS.items():
        if name not in enabled:
            continue
        if name == "query_table" and not has_tables:
            continue
        if name in {"check_availability", "book_appointment"} and not has_calendar:
            continue
        if name == "handoff_to_human" and not cfg.get("handoff", {}).get("enabled", True):
            continue
        schemas.append(schema)
    schemas += dynamic_schemas(cfg, channel)
    ids = cfg.get("tools", {}).get("custom_tool_ids") or []
    if ids:
        for t in (await db.execute(select(Tool).where(Tool.workspace_id == ws.id, Tool.id.in_(ids), Tool.enabled.is_(True)))).scalars():
            params = (t.config or {}).get("parameters") or {"type": "object", "properties": {}}
            schemas.append({"type": "function", "function": {"name": t.name, "description": t.description, "parameters": params}})
    return schemas


def dynamic_schemas(cfg: dict, channel: str) -> list[dict]:
    """Tools whose options come from the agent's own settings (transfer targets, specialist agents, IVR keys)."""
    out = []
    targets = [t for t in (cfg.get("handoff") or {}).get("transfer_targets") or [] if t.get("name") and t.get("number")]
    if targets and cfg.get("handoff", {}).get("enabled", True):
        desc = "; ".join(f"{t['name']}: {t.get('description') or 'team'}" for t in targets)
        out.append(_fn("transfer_call", f"Transfer the customer to a human team ({desc}). Use when they ask for a person or need something you cannot do.",
                       {"destination": {"type": "string", "enum": [t["name"] for t in targets]}, "reason": {"type": "string"}}, ["destination"]))
    members = [m for m in (cfg.get("squad") or {}).get("members") or [] if m.get("name") and m.get("agent_id")]
    if members:
        desc = "; ".join(f"{m['name']}: {m.get('when') or 'specialist'}" for m in members)
        out.append(_fn("transfer_to_agent", f"Hand the conversation to a specialist AI agent on the team ({desc}). Their memory of this conversation is kept.",
                       {"agent": {"type": "string", "enum": [m["name"] for m in members]}, "reason": {"type": "string"}}, ["agent"]))
    if channel == "phone" and (cfg.get("voice") or {}).get("ivr_navigation"):
        out.append(_fn("press_keys", "Press phone keypad keys (DTMF) to navigate an automated phone menu (IVR) you have called.",
                       {"digits": {"type": "string", "description": "Keys to press, e.g. '1', '2#', or '1w2' (w = short pause)"}}, ["digits"]))
    return out
