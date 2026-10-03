"""Request authentication.

Three ways in, checked in order:
1. Dev bypass (local only): `Authorization: Bearer dev:<DEV_TOKEN>` from a loopback
   address while UNISONA_ENV=development and DEV_AUTH_BYPASS=true.
2. Workspace API key: `Authorization: Bearer usk_...` (hashed in the database).
3. Clerk session JWT, verified against Clerk's JWKS. The active organization becomes
   the workspace; a user with no active organization gets a personal workspace.

Tenant identity always comes from a verified token, never from a header the client
can set on its own.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_db, new_id, utcnow
from ..log import get_logger
from ..models import ApiKey, Member, Workspace
from .crypto import new_wrapped_dek

log = get_logger("auth")
_jwks_client: jwt.PyJWKClient | None = None
_org_name_cache: dict[str, tuple[str, float]] = {}

ROLE_RANK = {"viewer": 0, "agent": 1, "builder": 2, "admin": 3, "owner": 4}


@dataclass
class AuthContext:
    user_id: str
    workspace: Workspace
    role: str = "admin"
    email: str | None = None
    name: str | None = None
    via: str = "clerk"
    claims: dict = field(default_factory=dict)

    @property
    def ws(self) -> str:
        return self.workspace.id

    def require(self, role: str) -> None:
        if ROLE_RANK.get(self.role, 0) < ROLE_RANK[role]:
            raise HTTPException(403, f"This action needs the {role} role.")


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(f"{settings.clerk_issuer}/.well-known/jwks.json", cache_keys=True, lifespan=3600)
    return _jwks_client


def _is_loopback(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _map_role(clerk_role: str | None) -> str:
    if not clerk_role:
        return "owner"
    r = clerk_role.split(":")[-1]
    return {"admin": "admin", "member": "builder", "owner": "owner"}.get(r, "builder")


async def _clerk_org_name(org_id: str) -> str | None:
    hit = _org_name_cache.get(org_id)
    if hit and hit[1] > time.time():
        return hit[0]
    if not settings.clerk_secret_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(
                f"https://api.clerk.com/v1/organizations/{org_id}",
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            )
            if r.status_code == 200:
                name = r.json().get("name")
                _org_name_cache[org_id] = (name, time.time() + 600)
                return name
    except Exception as e:  # network hiccup should never block a request
        log.warning(f"Could not fetch Clerk org name: {e}")
    return None


async def ensure_workspace(db: AsyncSession, external_id: str, name: str) -> Workspace:
    ws = (await db.execute(select(Workspace).where(Workspace.clerk_org_id == external_id))).scalar_one_or_none()
    if ws:
        return ws
    ws_id = new_id("ws")
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")[:60] or "workspace"
    ws = Workspace(
        id=ws_id,
        clerk_org_id=external_id,
        name=name,
        slug=slug,
        plan="growth" if settings.is_dev else "free",
        settings={"dek": new_wrapped_dek(ws_id), "timezone": "Asia/Kolkata", "currency": "INR"},
    )
    db.add(ws)
    await db.flush()
    log.info(f"Provisioned workspace '{name}' ({ws.id})")
    from ..services.bootstrap import seed_workspace  # local import: avoids cycle

    await seed_workspace(db, ws)
    await db.commit()
    return ws


async def _ensure_member(db: AsyncSession, ws: Workspace, user_id: str, role: str, email: str | None, name: str | None) -> Member:
    m = (await db.execute(select(Member).where(Member.workspace_id == ws.id, Member.user_id == user_id))).scalar_one_or_none()
    if not m:
        m = Member(workspace_id=ws.id, user_id=user_id, role=role, email=email, name=name)
        db.add(m)
    else:
        m.role = role
        if email:
            m.email = email
        if name:
            m.name = name
    m.last_seen_at = utcnow()
    await db.commit()
    return m


async def _from_token(token: str, client_host: str | None, db: AsyncSession) -> AuthContext:
    # 1. Dev bypass
    if token.startswith("dev:"):
        if not settings.dev_bypass_active:
            raise HTTPException(401, "Dev auth bypass is disabled.")
        if not _is_loopback(client_host):
            raise HTTPException(401, "Dev auth bypass only works from localhost.")
        if token[4:] != settings.dev_token:
            raise HTTPException(401, "Invalid dev token.")
        ws = await ensure_workspace(db, "dev_org", "Dev Workspace")
        await _ensure_member(db, ws, "dev_user", "owner", "dev@unisona.local", "Dev User")
        return AuthContext(user_id="dev_user", workspace=ws, role="owner", email="dev@unisona.local", name="Dev User", via="dev")

    # 2. Workspace API key
    if token.startswith("usk_"):
        digest = hashlib.sha256(token.encode()).hexdigest()
        key = (await db.execute(select(ApiKey).where(ApiKey.hash == digest))).scalar_one_or_none()
        if not key:
            raise HTTPException(401, "Invalid API key.")
        key.last_used_at = utcnow()
        ws = await db.get(Workspace, key.workspace_id)
        await db.commit()
        return AuthContext(user_id=f"apikey:{key.id}", workspace=ws, role="admin", via="api_key")

    # 3. Clerk JWT
    if not settings.clerk_issuer:
        raise HTTPException(401, "Clerk is not configured.")
    try:
        signing_key = _jwks().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], issuer=settings.clerk_issuer,
                            options={"verify_aud": False}, leeway=10)
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid session token: {e}") from e

    user_id = claims["sub"]
    org = claims.get("o") or {}
    org_id = org.get("id") or claims.get("org_id")
    org_role = org.get("rol") or claims.get("org_role")
    email = claims.get("email")
    name = claims.get("name")
    if org_id:
        org_name = await _clerk_org_name(org_id) or org.get("slg") or "Workspace"
        ws = await ensure_workspace(db, org_id, org_name)
        role = _map_role(org_role)
    else:
        ws = await ensure_workspace(db, f"personal_{user_id}", "Personal workspace")
        role = "owner"
    await _ensure_member(db, ws, user_id, role, email, name)
    return AuthContext(user_id=user_id, workspace=ws, role=role, email=email, name=name, via="clerk", claims=claims)


_ctx_cache: dict[str, tuple[float, dict]] = {}


async def _cached(token: str, client_host: str | None, db: AsyncSession) -> AuthContext:
    """Verify once, then reuse the identity for 60s (saves several DB round-trips per request).
    Dev tokens are still checked against loopback on every request."""
    key = hashlib.sha256(token.encode()).hexdigest()
    hit = _ctx_cache.get(key)
    if hit and hit[0] > time.time():
        if token.startswith("dev:") and not _is_loopback(client_host):
            raise HTTPException(401, "Dev auth bypass only works from localhost.")
        d = hit[1]
        ws = await db.get(Workspace, d["ws_id"])
        if ws:
            return AuthContext(user_id=d["user_id"], workspace=ws, role=d["role"], email=d["email"], name=d["name"], via=d["via"], claims=d["claims"])
    ctx = await _from_token(token, client_host, db)
    exp = min(time.time() + 60, float(ctx.claims.get("exp", time.time() + 60))) if ctx.claims else time.time() + 60
    _ctx_cache[key] = (exp, {"ws_id": ctx.ws, "user_id": ctx.user_id, "role": ctx.role, "email": ctx.email, "name": ctx.name,
                             "via": ctx.via, "claims": ctx.claims})
    if len(_ctx_cache) > 2000:
        for k in [k for k, v in _ctx_cache.items() if v[0] < time.time()]:
            _ctx_cache.pop(k, None)
    return ctx


def _bearer(request_headers) -> str:
    auth = request_headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token.")
    return auth[7:].strip()


async def _as_client(ctx: AuthContext, target_id: str | None, db: AsyncSession) -> AuthContext:
    """Agency mode: an agency admin may act inside one of its client sub-accounts (workspaces whose parent is the agency).
    The target is always checked against the verified identity's own workspace; the header alone grants nothing."""
    if not target_id or target_id == ctx.ws:
        return ctx
    target = await db.get(Workspace, target_id)
    if not target or target.parent_id != ctx.ws:
        raise HTTPException(403, "You don't have access to that workspace.")
    if ROLE_RANK.get(ctx.role, 0) < ROLE_RANK["admin"]:
        raise HTTPException(403, "Only agency admins can open client accounts.")
    return AuthContext(user_id=ctx.user_id, workspace=target, role="admin", email=ctx.email, name=ctx.name, via=f"agency:{ctx.ws}",
                       claims={**ctx.claims, "agency_ws": ctx.ws})


async def require_auth(request: Request, db: AsyncSession = Depends(get_db)) -> AuthContext:
    token = _bearer(request.headers)
    ctx = await _cached(token, request.client.host if request.client else None, db)
    ctx = await _as_client(ctx, request.headers.get("x-workspace-id"), db)
    request.state.auth = ctx
    return ctx


async def ws_auth(websocket: WebSocket, db: AsyncSession) -> AuthContext:
    token = websocket.query_params.get("token", "")
    if not token:
        raise HTTPException(401, "Missing token.")
    ctx = await _cached(token, websocket.client.host if websocket.client else None, db)
    return await _as_client(ctx, websocket.query_params.get("workspace"), db)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
