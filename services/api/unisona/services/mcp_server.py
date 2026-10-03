"""Unisona as an MCP server: lets Claude, Cursor or any MCP client operate a workspace.

Mounted at /mcp (Streamable HTTP). Authenticate with a workspace API key:
`Authorization: Bearer usk_...`.
"""
from __future__ import annotations

import contextvars
import hashlib

from sqlalchemy import func, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..db import SessionLocal
from ..log import get_logger
from ..models import Agent, ApiKey, Contact, Conversation, KnowledgeBase, Message, Task, Workspace

log = get_logger("mcp")
_ws: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_ws", default="")


def build_server():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name="unisona", instructions="Operate a Unisona workspace: agents, knowledge, conversations and CRM.")

    @server.tool(description="List the workspace's AI agents with their status.")
    async def list_agents() -> list[dict]:
        async with SessionLocal() as db:
            rows = (await db.execute(select(Agent).where(Agent.workspace_id == _ws.get()))).scalars().all()
            return [{"id": a.id, "name": a.name, "status": a.status, "template": a.template_id} for a in rows]

    @server.tool(description="Ask an agent a question exactly as a customer would (uses its knowledge, memory and tools).")
    async def ask_agent(agent_id: str, question: str) -> dict:
        from ..brain.respond import Turn, respond

        async with SessionLocal() as db:
            ws = await db.get(Workspace, _ws.get())
            agent = await db.get(Agent, agent_id)
            if not agent or agent.workspace_id != ws.id:
                return {"error": "agent not found"}
            r = await respond(db, Turn(ws=ws, agent=agent, channel="playground", text=question, use_draft=False))
            return {"answer": r.get("text"), "citations": r.get("citations"), "conversation_id": r.get("conversation_id")}

    @server.tool(description="Search the workspace knowledge base and return the most relevant passages.")
    async def search_knowledge(query: str, k: int = 5) -> list[dict]:
        from ..knowledge.retrieve import retrieve

        async with SessionLocal() as db:
            kb_ids = (await db.execute(select(KnowledgeBase.id).where(KnowledgeBase.workspace_id == _ws.get()))).scalars().all()
            res = await retrieve(db, _ws.get(), list(kb_ids), query, k=min(k, 10), mode="deep")
            return [{"title": c.title, "text": c.text[:800], "score": round(c.score, 4)} for c in res.chunks]

    @server.tool(description="Add a text document to the default knowledge base.")
    async def add_knowledge(title: str, text: str) -> dict:
        from ..models import KnowledgeSource
        from ..worker.queue import enqueue

        async with SessionLocal() as db:
            kb = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.workspace_id == _ws.get()).order_by(KnowledgeBase.created_at))).scalars().first()
            src = KnowledgeSource(workspace_id=_ws.get(), kb_id=kb.id, type="text", title=title[:300], meta={"text": text})
            db.add(src)
            await db.commit()
            await enqueue("knowledge.ingest", {"source_id": src.id}, workspace_id=_ws.get())
            return {"source_id": src.id, "status": "ingesting"}

    @server.tool(description="Search CRM contacts by name, phone or email.")
    async def crm_search_contacts(query: str) -> list[dict]:
        async with SessionLocal() as db:
            rows = (await db.execute(select(Contact).where(Contact.workspace_id == _ws.get(), (Contact.name.ilike(f"%{query}%")) |
                                                           (Contact.phone.ilike(f"%{query}%")) | (Contact.email.ilike(f"%{query}%"))).limit(20))).scalars().all()
            return [{"id": c.id, "name": c.name, "phone": c.phone, "email": c.email, "lifecycle": c.lifecycle, "score": c.score, "summary": c.summary} for c in rows]

    @server.tool(description="Create a CRM follow-up task, optionally for a contact.")
    async def crm_create_task(title: str, contact_id: str | None = None) -> dict:
        async with SessionLocal() as db:
            t = Task(workspace_id=_ws.get(), title=title[:300], contact_id=contact_id, created_by="mcp")
            db.add(t)
            await db.commit()
            return {"task_id": t.id}

    @server.tool(description="Get a conversation transcript and its AI summary.")
    async def get_conversation(conversation_id: str) -> dict:
        async with SessionLocal() as db:
            c = await db.get(Conversation, conversation_id)
            if not c or c.workspace_id != _ws.get():
                return {"error": "not found"}
            msgs = (await db.execute(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at))).scalars().all()
            return {"channel": c.channel, "summary": c.summary, "outcome": c.outcome, "messages": [{"role": m.role, "content": m.content} for m in msgs]}

    @server.tool(description="Headline numbers for the workspace: conversations, contacts, open tasks.")
    async def workspace_summary() -> dict:
        async with SessionLocal() as db:
            ws = _ws.get()
            return {
                "conversations": (await db.execute(select(func.count()).select_from(Conversation).where(Conversation.workspace_id == ws))).scalar(),
                "contacts": (await db.execute(select(func.count()).select_from(Contact).where(Contact.workspace_id == ws))).scalar(),
                "open_tasks": (await db.execute(select(func.count()).select_from(Task).where(Task.workspace_id == ws, Task.status == "open"))).scalar(),
            }

    return server


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not token.startswith("usk_"):
            return JSONResponse({"error": "Use a workspace API key: Authorization: Bearer usk_..."}, status_code=401)
        async with SessionLocal() as db:
            key = (await db.execute(select(ApiKey).where(ApiKey.hash == hashlib.sha256(token.encode()).hexdigest()))).scalar_one_or_none()
        if not key:
            return JSONResponse({"error": "Invalid API key"}, status_code=401)
        tok = _ws.set(key.workspace_id)
        try:
            return await call_next(request)
        finally:
            _ws.reset(tok)
