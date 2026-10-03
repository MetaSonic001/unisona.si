"""Durable job queue on Postgres (`app.jobs`) with SKIP LOCKED claiming.

No Redis, no extra service: the worker loop runs inside the API process by default
(RUN_WORKER=true) or standalone via `python -m unisona.worker`. Jobs survive restarts,
retry with backoff and record their result or error.
"""
from __future__ import annotations

import asyncio
import traceback
from datetime import timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import text

from ..config import settings
from ..db import SessionLocal, new_id, utcnow
from ..log import get_logger
from ..models import Job

log = get_logger("worker")
Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
HANDLERS: dict[str, Handler] = {}
_wake = asyncio.Event()


def handler(name: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return deco


async def enqueue(type_: str, payload: dict[str, Any], *, workspace_id: str | None = None, delay_s: float = 0,
                  max_attempts: int = 3) -> str:
    async with SessionLocal() as db:
        job = Job(id=new_id("job"), workspace_id=workspace_id, type=type_, payload=payload,
                  run_at=utcnow() + timedelta(seconds=delay_s), max_attempts=max_attempts)
        db.add(job)
        await db.commit()
    _wake.set()
    return job.id


async def _claim() -> Job | None:
    schema = settings.db_schema
    async with SessionLocal() as db:
        row = (await db.execute(text(f"""
            UPDATE "{schema}".jobs SET status='running', locked_at=now(), attempts=attempts+1
            WHERE id = (
              SELECT id FROM "{schema}".jobs
              WHERE (status='queued' AND run_at <= now())
                 OR (status='running' AND locked_at < now() - interval '10 minutes')
              ORDER BY run_at LIMIT 1 FOR UPDATE SKIP LOCKED)
            RETURNING id"""))).first()
        await db.commit()
        if not row:
            return None
        return await db.get(Job, row[0])


async def _finish(job_id: str, *, ok: bool, result: dict | None = None, error: str | None = None, retry_in: float | None = None):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            return
        if ok:
            job.status, job.result, job.error = "done", result or {}, None
        elif retry_in is not None and job.attempts < job.max_attempts:
            job.status, job.error, job.run_at = "queued", error, utcnow() + timedelta(seconds=retry_in)
        else:
            job.status, job.error = "failed", error
        await db.commit()


async def _run_one(job: Job) -> None:
    fn = HANDLERS.get(job.type)
    if not fn:
        log.error(f"No handler for job type {job.type}")
        await _finish(job.id, ok=False, error="no handler")
        return
    try:
        result = await fn(job.payload)
        await _finish(job.id, ok=True, result=result)
    except Exception as e:
        log.warning(f"Job {job.type} ({job.id}) failed on attempt {job.attempts}: {e}")
        log.debug(traceback.format_exc())
        await _finish(job.id, ok=False, error=str(e)[:1000], retry_in=15 * job.attempts)


async def run_pending(limit: int = 200) -> int:
    """Drain due jobs inline (CLI/tests, when no API process is running the worker)."""
    from . import jobs  # noqa: F401

    n = 0
    while n < limit and (job := await _claim()):
        await _run_one(job)
        n += 1
    return n


async def worker_loop(stop: asyncio.Event) -> None:
    from . import jobs  # noqa: F401  (registers handlers)

    sem = asyncio.Semaphore(settings.worker_concurrency)
    log.info(f"Worker started ({settings.worker_concurrency} slots, {len(HANDLERS)} job types)")
    running: set[asyncio.Task] = set()
    while not stop.is_set():
        try:
            await sem.acquire()
            job = await _claim()
            if not job:
                sem.release()
                _wake.clear()
                try:
                    await asyncio.wait_for(_wake.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass
                continue

            async def run(j=job):
                try:
                    await _run_one(j)
                finally:
                    sem.release()

            t = asyncio.create_task(run())
            running.add(t)
            t.add_done_callback(running.discard)
        except Exception as e:
            sem.release()
            log.error(f"Worker loop error: {e}")
            await asyncio.sleep(3)
    for t in running:
        t.cancel()
