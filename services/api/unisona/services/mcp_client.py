"""Connect agents to remote MCP servers (Streamable HTTP) as tools."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from ..log import get_logger
from ..models import Tool, Workspace

log = get_logger("mcp-client")


@asynccontextmanager
async def _client(url: str, token: str | None):
    from mcp import Client

    if token:
        try:
            import httpx2
            from mcp.client.streamable_http import streamable_http_client

            http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=30)

            class _T:  # transport adapter: Client accepts any async-context transport
                def __call__(self):
                    return streamable_http_client(url, http_client=http)

            async with Client(_T()) as c:  # type: ignore[arg-type]
                yield c
            return
        except Exception as e:  # fall back to unauthenticated URL transport
            log.debug(f"MCP header transport unavailable ({e}); using plain URL")
    async with Client(url) as c:
        yield c


async def list_remote_tools(url: str, token: str | None = None) -> list[dict]:
    async with _client(url, token) as c:
        res = await c.list_tools()
        return [{"name": t.name, "description": t.description or "", "parameters": t.inputSchema or {"type": "object", "properties": {}}}
                for t in res.tools]


async def call_mcp_tool(ws: Workspace, tool: Tool, args: dict) -> str:
    cfg = tool.config or {}
    token = None
    if tool.enc_secret:
        from ..security.crypto import decrypt_json

        token = decrypt_json(ws.id, ws.settings["dek"], f"tool:{tool.id}", tool.enc_secret).get("token")
    remote_name = cfg.get("remote_name") or tool.name
    async with _client(cfg["url"], token) as c:
        res = await c.call_tool(remote_name, args)
    parts = []
    for item in getattr(res, "content", []) or []:
        parts.append(getattr(item, "text", None) or json.dumps(getattr(item, "model_dump", lambda: str(item))(), default=str))
    from ..security.guard import fence_untrusted

    return fence_untrusted(f"mcp {remote_name}", "\n".join(parts)[:4000])
