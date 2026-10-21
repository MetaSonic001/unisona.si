"""FastAPI application: routers, CORS, lifespan (worker, scheduler, pollers, warmups)."""
from __future__ import annotations

import asyncio
import time
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import ROOT_DIR, feature_matrix, settings
from .log import banner, console, get_logger, setup_logging, step

setup_logging()
log = get_logger("api")


async def _check_db() -> bool:
    from .db import engine
    from .ops import db_health

    try:
        async def _q():
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
                return (await conn.execute(text(f"select count(*) from information_schema.tables where table_schema = '{settings.db_schema}'"))).scalar()
        n = await asyncio.wait_for(_q(), 20)
        db_health.recovered()
        step(f"Database connected (schema '{settings.db_schema}', {n} tables)", True)
        if n < 10:
            log.warning("Schema looks empty. Run:  pnpm db:migrate  (on Render this runs on every start)")
        return True
    except Exception as e:
        db_health.failed(e, "startup")
        step(f"Database connection failed: {str(e).splitlines()[0][:300]}. The API keeps running and retries; "
             "check DATABASE_URL, and that the Supabase project is not paused.", False)
        return False


async def _warmup() -> None:
    t0 = time.perf_counter()
    try:
        from .knowledge.embed import warmup
        from .knowledge.store import chroma

        await asyncio.to_thread(chroma)
        step("Vector store (Chroma) ready", True)
        await warmup()
        step(f"Embedding model warmed up ({time.perf_counter() - t0:.1f}s). Knowledge search is ready.", True)
        from .knowledge.retrieve import _ranker_sync

        if settings.reranker_enabled:
            await asyncio.to_thread(_ranker_sync)
            step("Multilingual reranker ready", True)
        from .knowledge.heal import heal_indexes

        healed = await heal_indexes()
        if healed:
            step(f"Rebuilt local search indexes for {healed} knowledge base(s) from the database", True)
        from .providers.voices import catalog

        await catalog()
        step("Voice catalog loaded", True)
        from pipecat.audio.vad.silero import SileroVADAnalyzer

        await asyncio.to_thread(SileroVADAnalyzer)
        step(f"Voice engine ready (Silero VAD + Smart Turn). Browser calls can start. [{time.perf_counter() - t0:.1f}s total]", True)
        from .voice.session import prewarm_live_agents

        n = await prewarm_live_agents()
        step(f"Voice calls pre-warmed for {n} live agent(s): setup cached, greetings synthesized", True)
    except Exception as e:
        log.warning(f"Warmup issue (features will lazy-load on first use): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.plain_logs:
        setup_logging()
        for noisy in ("httpx", "httpcore", "openai", "groq"):
            __import__("logging").getLogger(noisy).setLevel("WARNING")
        log.info(f"Unisona API starting (env={settings.unisona_env}, port={settings.api_port})")
    else:
        console.rule("[bold magenta]Unisona API starting")
    rows = [(f.name, "[green]enabled[/green]" if f.enabled else "[yellow]disabled[/yellow]", f.env + (f" — {f.note}" if f.note else "")) for f in feature_matrix()]
    banner("Feature status (from .env)", rows)
    for f in feature_matrix():
        if not f.enabled and f.note != "required":
            log.info(f"Feature off: {f.name}. To enable, set {f.env}.")
        if not f.enabled and f.note == "required":
            log.error(f"REQUIRED setting missing: {f.env}. {f.name} will not work.")
    from .main import _exit_with_dev_runner
    from .ops import install_loop_handler, supervise, watchdog

    _exit_with_dev_runner()  # also in the auto-reload worker process, which outlives a hard-killed parent otherwise
    install_loop_handler()
    await _check_db()

    stop = asyncio.Event()
    tasks: list[asyncio.Task] = [asyncio.create_task(watchdog(stop))]
    async with AsyncExitStack() as stack:
        if settings.run_worker:
            from .worker.jobs import scheduler_loop
            from .worker.queue import worker_loop

            tasks.append(asyncio.create_task(supervise("worker", lambda: worker_loop(stop), stop)))
            tasks.append(asyncio.create_task(supervise("scheduler", lambda: scheduler_loop(stop), stop)))
            step("Background worker + scheduler running inside the API process", True)
        else:
            step("RUN_WORKER=false: start the worker separately with `pnpm dev:worker`", None)
        try:
            from .channels.telegram import start_all

            n = await start_all()
            if n:
                step(f"Telegram pollers started for {n} bot(s)", True)
        except Exception as e:
            log.warning(f"Telegram pollers not started: {e}")
        if getattr(app.state, "mcp", None) is not None:
            await stack.enter_async_context(app.state.mcp.session_manager.run())
            step("MCP server mounted at /mcp (auth: workspace API key)", True)
        tasks.append(asyncio.create_task(_warmup()))
        if settings.plain_logs:
            log.info(f"API ready on {settings.api_url} (docs: {settings.api_url}/docs)")
        else:
            console.rule(f"[bold green]API ready on {settings.api_url}  ·  docs: {settings.api_url}/docs")
        step("Waiting for: embedding model + voice engine warmup (watch for ✔ lines above/below)", None)
        yield
        stop.set()
        for t in tasks:
            t.cancel()
    from .knowledge.ingest import log as _  # noqa: F401
    log.info("API stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Unisona API", version="1.0.0", lifespan=lifespan,
                  description="One brain, many voices: omnichannel AI agents with shared memory, glass-box RAG and a built-in CRM.")
    from .ops import ErrorMiddleware

    origins = {settings.app_url, "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"}
    app.add_middleware(ErrorMiddleware)  # added first = inside CORS, so error responses still carry CORS headers
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_origin_regex=r"https?://.*",
                       allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    from .api import agents, analytics, calling, chat, conversations, core, crm, growth, knowledge, platform, public_suite, suite

    for r in (calling.router, suite.router, public_suite.router, core.router, agents.router, knowledge.router, conversations.router, chat.router, crm.router, crm.public,
              analytics.router, growth.router, platform.router, platform.dev):
        app.include_router(r)

    widget_dist = ROOT_DIR / "apps" / "widget" / "dist"
    if (widget_dist / "widget.js").exists():
        app.mount("/widget", StaticFiles(directory=str(widget_dist)), name="widget")
    else:
        # Hosted API without a widget build: the web app (Vercel) serves the same file from /widget/widget.js.
        from fastapi.responses import RedirectResponse

        @app.get("/widget/{path:path}", include_in_schema=False)
        async def widget_redirect(path: str):
            return RedirectResponse(f"{settings.app_url.rstrip('/')}/widget/{path}", status_code=307)

    try:
        from .services.mcp_server import ApiKeyMiddleware, build_server

        server = build_server()
        kwargs = {"streamable_http_path": "/", "stateless_http": True}
        try:
            from mcp.server.transport_security import TransportSecuritySettings

            kwargs["transport_security"] = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        except Exception:
            pass
        mcp_app = server.streamable_http_app(**kwargs)
        mcp_app.add_middleware(ApiKeyMiddleware)
        app.mount("/mcp", mcp_app)
        app.state.mcp = server
    except Exception as e:
        app.state.mcp = None
        log.warning(f"MCP server not mounted: {e}")
    return app


app = create_app()
