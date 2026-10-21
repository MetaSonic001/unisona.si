"""Production safety net: request IDs, crash logging, DB-outage detection, supervised background tasks.

- `ErrorMiddleware` gives every request an id (`x-request-id`), logs any unhandled exception once with the
  method, path, id and full traceback, and answers JSON (500, or 503 when the database is unreachable)
  instead of dropping the connection. It sits inside CORS, so the browser sees the real error, not
  "Failed to fetch".
- `db_health` remembers whether the database is reachable so the worker/scheduler back off quietly
  during an outage (one log line per state change instead of a traceback every few seconds).
- `supervise()` restarts a crashed background loop with backoff; `install_loop_handler()` logs
  exceptions from fire-and-forget tasks that nobody awaited.
- Truly fatal states (out of memory, the event loop wedged) end the process: the host restarts it,
  and the last log lines say why.
"""
from __future__ import annotations

import asyncio
import os
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable

import orjson

from .log import get_logger

log = get_logger("ops")

_DB_MARKERS = (
    "tenant/user", "could not connect", "connection refused", "connection was closed", "connectionreseterror",
    "timeout", "temporary failure in name resolution", "getaddrinfo failed", "server closed the connection",
    "too many connections", "max client connections", "connection is closed", "cannot connect now",
    "the database system is starting up", "the database system is shutting down",
)


def is_db_unavailable(exc: BaseException) -> bool:
    """True for errors that mean "the database can't be reached", not "this query is wrong"."""
    import sqlalchemy.exc as sa_exc

    chain: list[BaseException] = []
    e: BaseException | None = exc
    while e is not None and len(chain) < 6:
        chain.append(e)
        e = e.__cause__ or e.__context__
    from_db = any(type(err).__module__.split(".")[0] in {"sqlalchemy", "asyncpg"} for err in chain)
    if not from_db:
        return False  # an LLM/HTTP timeout is not a database outage
    for err in chain:
        if isinstance(err, (ConnectionError, asyncio.TimeoutError, TimeoutError)) or (
                isinstance(err, OSError) and not isinstance(err, (FileNotFoundError, PermissionError))):
            return True
        if isinstance(err, sa_exc.DisconnectionError):
            return True
        if any(m in str(err).lower() for m in _DB_MARKERS):
            return True
    return False


class _DbHealth:
    def __init__(self) -> None:
        self.ok = True
        self.since = time.time()
        self.last_error = ""
        self.note = ""  # user-facing status, e.g. "the database is waking up"

    def failed(self, exc: BaseException, where: str) -> None:
        msg = str(exc).splitlines()[0][:300]
        if self.ok:
            log.error(f"DATABASE UNREACHABLE ({where}): {msg}. Requests that need the database return 503 until it is back.")
            self.ok, self.since = False, time.time()
            try:  # free Supabase projects pause after 7 idle days: check and restore it automatically
                from .supabase_wake import wake_if_paused

                asyncio.get_running_loop().create_task(wake_if_paused())
            except RuntimeError:
                pass  # no running loop (CLI)
        self.last_error = msg

    def recovered(self) -> None:
        if not self.ok:
            log.info(f"Database reachable again after {time.time() - self.since:.0f}s")
            self.ok, self.since, self.last_error, self.note = True, time.time(), "", ""


db_health = _DbHealth()


async def check_db(timeout: float = 5.0) -> bool:
    from sqlalchemy import text

    from .db import engine

    try:
        async def _q():
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
        await asyncio.wait_for(_q(), timeout)
        db_health.recovered()
        return True
    except Exception as e:
        db_health.failed(e, "health check")
        return False


def _json(status: int, body: dict, request_id: str) -> tuple[dict, bytes]:
    payload = orjson.dumps(body)
    return ({"type": "http.response.start", "status": status,
             "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode()),
                         (b"x-request-id", request_id.encode())]}, payload)


class ErrorMiddleware:
    """Pure ASGI (works with streaming responses and websockets)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        rid = (headers.get(b"x-request-id") or b"").decode()[:64] or uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["request_id"] = rid
        started = False
        t0 = time.perf_counter()

        async def _send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            path = scope.get("path", "")
            method = scope.get("method", "WS")
            ms = int((time.perf_counter() - t0) * 1000)
            if is_db_unavailable(exc):
                db_health.failed(exc, f"{method} {path}")
                status, body = 503, {"detail": db_health.note or "The database is temporarily unavailable. Please retry in a minute.",
                                     "request_id": rid, "code": "db_unavailable"}
            else:
                log.error(f"Unhandled error on {method} {path} [request_id={rid}, {ms} ms]: {type(exc).__name__}: {exc}\n"
                          f"{''.join(traceback.format_exception(exc))}")
                status, body = 500, {"detail": "Internal server error. Quote this request id when reporting it.",
                                     "request_id": rid, "code": "internal_error"}
            if isinstance(exc, MemoryError):
                fatal("out of memory while handling a request")
            if scope["type"] == "http" and not started:
                start, payload = _json(status, body, rid)
                await send(start)
                await send({"type": "http.response.body", "body": payload})


def fatal(reason: str, code: int = 1) -> None:
    """Exit so the host restarts a clean process. The reason is the last thing in the logs."""
    log.critical(f"FATAL: {reason}. Exiting so the platform restarts the service.")
    for h in __import__("logging").getLogger().handlers:
        try:
            h.flush()
        except Exception:
            pass
    os._exit(code)


async def supervise(name: str, factory: Callable[[], Awaitable[None]], stop: asyncio.Event) -> None:
    """Run a long-lived loop; if it crashes, log the traceback and restart it with backoff (max 60 s)."""
    delay = 2.0
    while not stop.is_set():
        t0 = time.time()
        try:
            await factory()
            return  # clean exit (stop was set)
        except asyncio.CancelledError:
            raise
        except MemoryError:
            fatal(f"{name} ran out of memory")
        except Exception as e:
            if time.time() - t0 > 300:
                delay = 2.0
            log.error(f"Background task '{name}' crashed: {type(e).__name__}: {e}. Restarting in {delay:.0f}s.\n"
                      f"{''.join(traceback.format_exception(e))}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            delay = min(delay * 2, 60.0)


def install_loop_handler() -> None:
    loop = asyncio.get_running_loop()

    def handler(loop, context):
        exc = context.get("exception")
        msg = context.get("message", "")
        if exc is not None and is_db_unavailable(exc):
            db_health.failed(exc, "background task")
            return
        if isinstance(exc, MemoryError):
            fatal("out of memory in a background task")
        detail = "".join(traceback.format_exception(exc)) if exc else ""
        log.error(f"Unhandled error in background task: {msg} {type(exc).__name__ if exc else ''}: {exc or ''}\n{detail}")

    loop.set_exception_handler(handler)


async def watchdog(stop: asyncio.Event, max_lag_s: float = 90.0) -> None:
    """If the event loop is blocked for too long (a stuck sync call), nothing can be served: restart."""
    import threading

    last = {"t": time.monotonic()}

    def _check():
        while not stop.is_set():
            time.sleep(5)
            lag = time.monotonic() - last["t"]
            if lag > max_lag_s:
                fatal(f"event loop blocked for {lag:.0f}s (a synchronous call is stuck)")

    threading.Thread(target=_check, name="loop-watchdog", daemon=True).start()
    while not stop.is_set():
        last["t"] = time.monotonic()
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass
