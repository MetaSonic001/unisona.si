"""Core routes: health, status, workspace, members, BYOK providers, voices, templates, notifications, API keys."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..brain.templates import TEMPLATES
from ..config import feature_matrix, settings
from ..db import get_db
from ..models import Agent, ApiKey, AuditLog, Contact, Conversation, KnowledgeSource, Member, Notification, ProviderCredential
from ..providers import keys as keys_mod
from ..providers.registry import PROVIDERS, public_catalog
from ..providers.voices import LANGUAGES, catalog, preview
from ..security.auth import AuthContext, hash_api_key, require_auth
from .common import audit, to_dict

router = APIRouter()


@router.get("/health")
async def health():
    return {"ok": True, "service": "unisona-api"}


@router.get("/status")
async def status():
    return {"env": settings.unisona_env, "dev_mode": settings.dev_mode and settings.is_dev,
            "features": [f.__dict__ for f in feature_matrix()]}


@router.get("/me")
async def me(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    ws = auth.workspace
    labels = [("agents", Agent), ("contacts", Contact), ("conversations", Conversation), ("sources", KnowledgeSource)]
    row = (await db.execute(select(*[select(func.count()).select_from(m).where(m.workspace_id == ws.id).scalar_subquery() for _, m in labels]))).one()
    counts = {label: n for (label, _), n in zip(labels, row)}
    keys = (await db.execute(select(ProviderCredential.provider, ProviderCredential.status).where(ProviderCredential.workspace_id == ws.id))).all()
    platform_llm = any(f.enabled for f in feature_matrix() if f.name.startswith("Platform LLM"))
    return {
        "user": {"id": auth.user_id, "email": auth.email, "name": auth.name, "role": auth.role, "via": auth.via},
        "workspace": {k: v for k, v in to_dict(ws).items() if k not in {"settings"}} | {
            "timezone": ws.settings.get("timezone"), "currency": ws.settings.get("currency"), "llm": ws.settings.get("llm", {})},
        "counts": counts,
        "providers": [{"provider": p, "status": s} for p, s in keys],
        "ai_ready": platform_llm or any(s == "valid" for _, s in keys),
        "dev_mode": settings.dev_mode and settings.is_dev,
    }


@router.patch("/workspace")
async def update_workspace(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    ws = auth.workspace
    ws = await db.merge(ws)
    if "name" in body:
        ws.name = body["name"][:200]
    s = dict(ws.settings)
    for k in ("timezone", "currency", "llm", "pii_redaction", "retention_days", "business_hours", "identity_secret"):
        if k in body:
            s[k] = body[k]
    ws.settings = s
    if "branding" in body:
        ws.branding = body["branding"]
    if "onboarding" in body:
        ws.onboarding = {**ws.onboarding, **body["onboarding"]}
    await audit(db, auth, "workspace.update", ws.id, {k: v for k, v in body.items() if k != "branding"})
    await db.commit()
    return {"ok": True}


@router.get("/members")
async def members(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Member).where(Member.workspace_id == auth.ws).order_by(Member.created_at))).scalars().all()
    return {"items": [to_dict(m) for m in rows]}


@router.patch("/members/{member_id}")
async def update_member(member_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    m = await db.get(Member, member_id)
    if not m or m.workspace_id != auth.ws:
        raise HTTPException(404)
    if "teams" in body:
        m.teams = body["teams"]
    if "online" in body:
        m.online = bool(body["online"])
    await db.commit()
    return to_dict(m)


@router.post("/presence")
async def presence(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    m = (await db.execute(select(Member).where(Member.workspace_id == auth.ws, Member.user_id == auth.user_id))).scalar_one_or_none()
    if m:
        m.online = bool(body.get("online", True))
        await db.commit()
    return {"ok": True}


# ── BYOK providers ───────────────────────────────────────────────────────────
@router.get("/providers/catalog")
async def providers_catalog():
    platform = {p.id: bool(p.env and getattr(settings, p.env.lower(), "")) for p in PROVIDERS.values()}
    return {"providers": [dict(p, platform_key=platform.get(p["id"], False)) for p in public_catalog()]}


@router.get("/providers")
async def list_keys(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ProviderCredential).where(ProviderCredential.workspace_id == auth.ws))).scalars().all()
    return {"items": [to_dict(r, {"enc_payload"}) for r in rows]}


@router.put("/providers/{provider}")
async def save_key(provider: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    ws = await db.merge(auth.workspace)
    extra = {k: str(v).strip() for k, v in (body.get("extra") or {}).items() if k in {"webhook_secret"} and v}
    row = await keys_mod.save_key(db, ws, provider, (body.get("api_key") or "").strip() or None, (body.get("base_url") or "").strip() or None, extra)
    await audit(db, auth, "provider.key_saved", provider, {"status": row.status})
    await db.commit()
    return to_dict(row, {"enc_payload"})


@router.post("/providers/{provider}/test")
async def test_key(provider: str, body: dict, auth: AuthContext = Depends(require_auth)):
    ok, msg, meta = await keys_mod.validate_key(provider, (body.get("api_key") or "").strip() or None, body.get("base_url"))
    return {"ok": ok, "message": msg, "models": meta.get("models", [])[:50]}


@router.delete("/providers/{provider}")
async def delete_key(provider: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    await db.execute(delete(ProviderCredential).where(ProviderCredential.workspace_id == auth.ws, ProviderCredential.provider == provider))
    keys_mod.invalidate(auth.ws)
    await audit(db, auth, "provider.key_deleted", provider)
    await db.commit()
    return {"ok": True}


# ── Voices / languages / templates ───────────────────────────────────────────
@router.get("/voices")
async def voices(locale: str | None = None, engine: str | None = None, gender: str | None = None, q: str | None = None):
    items = await catalog()
    if locale:
        base = locale.split("-")[0].lower()
        items = [v for v in items if v["locale"].lower().startswith(base) or (v["multilingual"] and base != "en")]
    if engine:
        items = [v for v in items if v["engine"] == engine]
    if gender:
        items = [v for v in items if v["gender"] == gender]
    if q:
        items = [v for v in items if q.lower() in (v["name"] + v["locale"]).lower()]
    return {"items": items, "total": len(items)}


@router.get("/voices/preview")
async def voice_preview(voice_id: str = Query(...), locale: str | None = None, db: AsyncSession = Depends(get_db)):
    groq = settings.groq_api_key or None
    try:
        path, mime = await preview(voice_id, locale, groq)
    except Exception as e:
        raise HTTPException(400, f"Preview failed: {e}") from e
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/languages")
async def languages():
    return {"items": LANGUAGES}


@router.get("/templates")
async def templates():
    return {"items": [{k: v for k, v in t.items()} for t in TEMPLATES]}


# ── Notifications ────────────────────────────────────────────────────────────
@router.get("/notifications")
async def notifications(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Notification).where(Notification.workspace_id == auth.ws).order_by(Notification.created_at.desc()).limit(50))).scalars().all()
    unread = (await db.execute(select(func.count()).select_from(Notification).where(Notification.workspace_id == auth.ws, Notification.read.is_(False)))).scalar()
    return {"items": [to_dict(n) for n in rows], "unread": unread}


@router.post("/notifications/read")
async def read_notifications(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import update

    await db.execute(update(Notification).where(Notification.workspace_id == auth.ws).values(read=True))
    await db.commit()
    return {"ok": True}


# ── API keys & audit ─────────────────────────────────────────────────────────
@router.get("/api-keys")
async def api_keys(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ApiKey).where(ApiKey.workspace_id == auth.ws).order_by(ApiKey.created_at.desc()))).scalars().all()
    return {"items": [to_dict(k, {"hash"}) for k in rows]}


@router.post("/api-keys")
async def create_api_key(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    raw = "usk_" + secrets.token_urlsafe(32)
    k = ApiKey(workspace_id=auth.ws, name=body.get("name") or "API key", prefix=raw[:10], hash=hash_api_key(raw))
    db.add(k)
    await audit(db, auth, "api_key.create", k.name)
    await db.commit()
    return {**to_dict(k, {"hash"}), "secret": raw}


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    auth.require("admin")
    await db.execute(delete(ApiKey).where(ApiKey.id == key_id, ApiKey.workspace_id == auth.ws))
    await db.commit()
    return {"ok": True}


@router.get("/audit")
async def audit_log(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AuditLog).where(AuditLog.workspace_id == auth.ws).order_by(AuditLog.created_at.desc()).limit(300))).scalars().all()
    return {"items": [to_dict(a) for a in rows]}
