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

    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
            n = (await conn.execute(text(f"select count(*) from information_schema.tables where table_schema = '{settings.db_schema}'"))).scalar()
        step(f"Database connected (schema '{settings.db_schema}', {n} tables)", True)
        if n < 10:
            log.warning("Schema looks empty. Run:  pnpm db:migrate")
        return True
    except Exception as e:
        step(f"Database connection failed: {e}", False)
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

        await asyncio.to_thread(_ranker_sync)
        step("Multilingual reranker ready", True)
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
    console.rule("[bold magenta]Unisona API starting")
    rows = [(f.name, "[green]enabled[/green]" if f.enabled else "[yellow]disabled[/yellow]", f.env + (f" — {f.note}" if f.note else "")) for f in feature_matrix()]
    banner("Feature status (from .env)", rows)
    for f in feature_matrix():
        if not f.enabled and f.note != "required":
            log.info(f"Feature off: {f.name}. To enable, set {f.env}.")
        if not f.enabled and f.note == "required":
            log.error(f"REQUIRED setting missing: {f.env}. {f.name} will not work.")
    await _check_db()

    stop = asyncio.Event()
    tasks: list[asyncio.Task] = []
    async with AsyncExitStack() as stack:
        if settings.run_worker:
            from .worker.jobs import scheduler_loop
            from .worker.queue import worker_loop

            tasks.append(asyncio.create_task(worker_loop(stop)))
            tasks.append(asyncio.create_task(scheduler_loop(stop)))
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
    origins = {settings.app_url, "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"}
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_origin_regex=r"https?://.*",
                       allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    from .api import agents, analytics, calling, chat, conversations, core, crm, growth, knowledge, platform, public_suite, suite

    for r in (calling.router, suite.router, public_suite.router, core.router, agents.router, knowledge.router, conversations.router, chat.router, crm.router, crm.public,
              analytics.router, growth.router, platform.router, platform.dev):
        app.include_router(r)

    widget_dist = ROOT_DIR / "apps" / "widget" / "dist"
    widget_dist.mkdir(parents=True, exist_ok=True)
    app.mount("/widget", StaticFiles(directory=str(widget_dist)), name="widget")

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
