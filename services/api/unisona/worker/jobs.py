"""Job handlers (registered with @handler) and the periodic scheduler."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import Contact, Conversation, KnowledgeSource, Workspace
from .queue import enqueue, handler

log = get_logger("jobs")


@handler("knowledge.ingest")
async def _ingest(p):
    from ..knowledge.ingest import ingest_source

    return await ingest_source(p["source_id"])


@handler("conversation.analyze")
async def _analyze(p):
    from ..brain.analysis import analyze_conversation

    async with SessionLocal() as db:
        return await analyze_conversation(db, p["conversation_id"])


@handler("memory.extract")
async def _memory(p):
    from ..brain.memory import extract_facts
    from ..providers.llm import get_llm

    async with SessionLocal() as db:
        conv = await db.get(Conversation, p["conversation_id"])
        if not conv or not conv.contact_id:
            return {"skipped": True}
        contact = await db.get(Contact, conv.contact_id)
        ws = await db.get(Workspace, conv.workspace_id)
        llm = await get_llm(db, ws, feature="memory extraction")
        if not llm.available:
            return {"skipped": "no llm"}
        return {"facts": await extract_facts(db, llm, contact, conv)}


@handler("webhook.deliver")
async def _deliver(p):
    from ..services.webhooks import deliver

    return await deliver(p["delivery_id"])


@handler("automation.event")
async def _auto_event(p):
    from ..services.automations import on_event

    return {"matched": await on_event(p["_ws"], p["event"], p["data"])}


@handler("integration.sync")
async def _integration_sync(p):
    from ..services.integrations import sync_event

    return await sync_event(p["_ws"], p["event"], p.get("data") or {})


@handler("eval.voice")
async def _eval_voice(p):
    from ..evals.voice_sim import run_voice_eval

    return await run_voice_eval(p["run_id"])


@handler("review.request")
async def _review_request(p):
    from ..services.reputation import send_request

    return await send_request(p["_ws"], p["contact_id"], p.get("channel"))


@handler("automation.resume")
async def _auto_resume(p):
    from ..services.automations import continue_run

    await continue_run(p["run_id"], int(p["step"]))
    return {"ok": True}


@handler("eval.run")
async def _eval(p):
    from ..evals.runner import execute_run

    return await execute_run(p["run_id"])


@handler("improve.workspace")
async def _improve(p):
    from ..brain.analysis import improve_flagged

    async with SessionLocal() as db:
        ws = await db.get(Workspace, p["workspace_id"])
        return {"review_items": await improve_flagged(db, ws)}


# ── scheduler ────────────────────────────────────────────────────────────────
async def scheduler_loop(stop: asyncio.Event) -> None:
    from ..services.campaigns import tick

    last_nightly: dict[str, str] = {}
    last_refresh = utcnow() - timedelta(hours=23)
    log.info("Scheduler started (campaigns every 20s, improve loop nightly 02:00 workspace time, source refresh daily)")
    while not stop.is_set():
        try:
            await tick()
            async with SessionLocal() as db:
                for ws in (await db.execute(select(Workspace))).scalars():
                    tz = ZoneInfo(ws.settings.get("timezone", "Asia/Kolkata"))
                    now = datetime.now(tz)
                    day = now.strftime("%Y-%m-%d")
                    if now.hour == 2 and last_nightly.get(ws.id) != day:
                        last_nightly[ws.id] = day
                        await enqueue("improve.workspace", {"workspace_id": ws.id}, workspace_id=ws.id, max_attempts=1)
                if utcnow() - last_refresh > timedelta(hours=24):
                    last_refresh = utcnow()
                    for src in (await db.execute(select(KnowledgeSource).where(KnowledgeSource.refresh_days > 0))).scalars():
                        if not src.last_ingested_at or utcnow() - src.last_ingested_at > timedelta(days=src.refresh_days):
                            await enqueue("knowledge.ingest", {"source_id": src.id}, workspace_id=src.workspace_id)
        except Exception as e:
            log.warning(f"Scheduler tick error: {e}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass
