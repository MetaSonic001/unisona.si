"""Restore a paused Supabase project automatically (free tier pauses projects after 7 days without activity).

A paused project does not wake up from a database connection: the pooler answers "tenant/user ... not found"
until someone presses Restore in the dashboard. With SUPABASE_ACCESS_TOKEN (a personal access token, local
.env only) the API does that itself through the Supabase Management API, waits until the project is healthy,
then finishes the startup work that needed the database.

Runs whenever the database goes from reachable to unreachable (including at startup). Without a token it logs
the exact dashboard link instead.
"""
from __future__ import annotations

import asyncio
import re
import time

import httpx

from .config import settings
from .log import get_logger

log = get_logger("supabase")
API = "https://api.supabase.com/v1"
_running = False


def project_ref() -> str:
    m = re.match(r"https://([a-z0-9]{20})\.supabase\.co", settings.next_public_supabase_url or "")
    if m:
        return m.group(1)
    m = re.search(r"postgres\.([a-z0-9]{20})[:@]", settings.database_url or "")  # pooler user: postgres.<ref>
    if m:
        return m.group(1)
    m = re.search(r"db\.([a-z0-9]{20})\.supabase\.co", settings.database_url or "")
    return m.group(1) if m else ""


async def _status(client: httpx.AsyncClient, ref: str) -> str:
    r = await client.get(f"{API}/projects/{ref}")
    r.raise_for_status()
    return r.json().get("status", "UNKNOWN")


async def _after_restore() -> None:
    """Startup steps that were skipped while the database was down."""
    from .ops import check_db

    for _ in range(30):  # the pooler can lag a little behind ACTIVE_HEALTHY
        if await check_db(timeout=10):
            break
        await asyncio.sleep(5)
    else:
        log.error("Project is active but the database still refuses connections. Check DATABASE_URL.")
        return
    try:
        from .knowledge.heal import heal_indexes
        from .voice.session import prewarm_live_agents

        await heal_indexes()
        n = await prewarm_live_agents()
        log.info(f"Startup completed after restore (voice pre-warmed for {n} agent(s))")
        from .channels.telegram import start_all

        await start_all()
    except Exception as e:
        log.warning(f"Post-restore warmup incomplete (features load on first use): {e}")


async def wake_if_paused() -> None:
    global _running
    if _running or "supabase" not in (settings.database_url or ""):
        return
    _running = True
    from .ops import db_health

    ref = project_ref()
    dashboard = f"https://supabase.com/dashboard/project/{ref}" if ref else "https://supabase.com/dashboard"
    try:
        if not settings.supabase_access_token:
            if "tenant/user" in db_health.last_error or "not found" in db_health.last_error:
                log.error(f"The Supabase project looks PAUSED (free projects pause after 7 idle days). Restore it at {dashboard} "
                          "or add SUPABASE_ACCESS_TOKEN to .env so the API restores it automatically next time.")
            return
        if not ref:
            log.error("Can't auto-restore: no project ref found in NEXT_PUBLIC_SUPABASE_URL or DATABASE_URL.")
            return
        async with httpx.AsyncClient(timeout=20, headers={"Authorization": f"Bearer {settings.supabase_access_token}"}) as client:
            try:
                status = await _status(client, ref)
            except httpx.HTTPStatusError as e:
                log.error(f"Supabase Management API refused the status check ({e.response.status_code}). "
                          f"Is SUPABASE_ACCESS_TOKEN valid for this project? Restore manually: {dashboard}")
                return
            if status == "ACTIVE_HEALTHY":
                log.warning("Supabase reports the project as healthy, so this outage is not a pause (network, credentials or pooler).")
                return
            if status in {"INACTIVE", "PAUSED"}:
                r = await client.post(f"{API}/projects/{ref}/restore")
                if r.status_code >= 400:
                    log.error(f"Supabase refused to restore the project ({r.status_code}: {r.text[:300]}). Common causes: the free "
                              f"plan's limit of 2 active projects, or a pause longer than 90 days. Restore manually: {dashboard}")
                    return
                log.warning("Supabase project was PAUSED: restore requested automatically. It usually takes 2–5 minutes; "
                            "the API answers 503 until then and finishes starting by itself.")
            else:
                log.info(f"Supabase project status is {status}: waiting for it to become healthy")
            db_health.note = "The database is waking up after being paused (about 2–5 minutes). Please retry shortly."
            t0 = time.time()
            while time.time() - t0 < 15 * 60:
                await asyncio.sleep(10)
                try:
                    status = await _status(client, ref)
                except Exception:
                    continue
                if status == "ACTIVE_HEALTHY":
                    log.info(f"Supabase project is active again ({time.time() - t0:.0f}s)")
                    await _after_restore()
                    return
            log.error(f"Supabase project still not healthy after 15 minutes (status {status}). Check {dashboard}")
    except Exception as e:
        log.error(f"Automatic Supabase restore failed: {e}. Restore manually: {dashboard}")
    finally:
        _running = False
