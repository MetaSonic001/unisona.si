"""BYOK key storage, resolution and validation.

Resolution order for any provider: the workspace's own key → the platform key from
.env (development, or while trial credits last) → None. Callers treat None as
"feature unavailable" and degrade gracefully; nothing raises because a key is missing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import utcnow
from ..log import feature_unavailable, get_logger
from ..models import ProviderCredential, Workspace
from ..security.crypto import decrypt_json, encrypt_json, mask
from .registry import PROVIDERS

log = get_logger("byok")
TRIAL_LLM_CALLS = 300
_cache: dict[tuple[str, str], tuple[dict | None, float]] = {}


@dataclass
class ResolvedKey:
    provider: str
    api_key: str | None
    base_url: str | None
    source: str  # workspace | platform | local | none
    extra: dict = field(default_factory=dict)  # provider-specific extras, e.g. a payment webhook secret

    @property
    def ok(self) -> bool:
        return self.source in {"workspace", "platform", "local"}


def _platform_key(provider: str) -> str:
    spec = PROVIDERS.get(provider)
    if not spec or not spec.env:
        return ""
    return getattr(settings, spec.env.lower(), "") or ""


def invalidate(ws_id: str) -> None:
    for k in [k for k in _cache if k[0] == ws_id]:
        _cache.pop(k, None)
    from ..brain.cache import invalidate_prefix

    invalidate_prefix("voicesnap:")  # voice calls snapshot resolved keys


async def _load(db: AsyncSession, ws: Workspace, provider: str) -> dict | None:
    hit = _cache.get((ws.id, provider))
    if hit and hit[1] > time.time():
        return hit[0]
    row = (await db.execute(select(ProviderCredential).where(
        ProviderCredential.workspace_id == ws.id, ProviderCredential.provider == provider))).scalar_one_or_none()
    data = None
    if row and row.status != "invalid":
        try:
            data = decrypt_json(ws.id, ws.settings["dek"], f"cred:{provider}", row.enc_payload)
        except Exception as e:
            log.error(f"Could not decrypt {provider} key for {ws.id}: {e}")
    _cache[(ws.id, provider)] = (data, time.time() + 60)
    return data


async def resolve(db: AsyncSession, ws: Workspace, provider: str, *, feature: str = "") -> ResolvedKey:
    spec = PROVIDERS.get(provider)
    if spec and not spec.needs_key:
        data = await _load(db, ws, provider) or {}
        return ResolvedKey(provider, data.get("api_key"), data.get("base_url") or spec.base_url, "local")
    data = await _load(db, ws, provider)
    if data and data.get("api_key"):
        extra = {k: v for k, v in data.items() if k not in {"api_key", "base_url"}}
        return ResolvedKey(provider, data["api_key"], data.get("base_url") or (spec.base_url if spec else None), "workspace", extra)
    platform = _platform_key(provider)
    if platform and (settings.is_dev or ws.trial_llm_calls < TRIAL_LLM_CALLS):
        return ResolvedKey(provider, platform, spec.base_url if spec else None, "platform")
    feature_unavailable(feature or f"{provider} provider", spec.env if spec and spec.env else f"a {provider} key")
    return ResolvedKey(provider, None, None, "none")


async def validate_key(provider: str, api_key: str | None, base_url: str | None = None) -> tuple[bool, str, dict]:
    """Make the cheapest possible authenticated call. Returns (ok, message, meta)."""
    spec = PROVIDERS.get(provider)
    if not spec:
        return False, f"Unknown provider '{provider}'", {}
    url = (base_url or spec.base_url).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            if spec.kind == "openai_compat":
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                if provider == "anthropic":
                    headers = {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"}
                r = await c.get(f"{url}/models", headers=headers)
                if r.status_code == 200:
                    body = r.json()
                    models = [m.get("id") for m in body.get("data", body.get("models", [])) if isinstance(m, dict)][:200]
                    return True, f"Key works. {len(models)} models available.", {"models": models}
                return False, f"{spec.name} rejected the key (HTTP {r.status_code}): {r.text[:160]}", {}
            if spec.kind == "deepgram":
                r = await c.get(f"{url}/projects", headers={"Authorization": f"Token {api_key}"})
            elif spec.kind == "cartesia":
                r = await c.get(f"{url}/voices", headers={"X-API-Key": api_key or "", "Cartesia-Version": "2025-04-16"})
            elif spec.kind == "elevenlabs":
                r = await c.get(f"{url}/user", headers={"xi-api-key": api_key or ""})
            elif spec.kind == "sarvam":
                r = await c.post(f"{url}/text-lid", headers={"api-subscription-key": api_key or ""}, json={"input": "namaste"})
            elif spec.kind == "gemini_live":
                r = await c.get(f"{url}/v1beta/models", params={"key": api_key or ""})
            elif spec.kind == "razorpay":
                key_id, _, secret = (api_key or "").partition(":")
                r = await c.get(f"{url}/payment_links", params={"count": 1}, auth=(key_id, secret))
            elif spec.kind == "stripe":
                r = await c.get(f"{url}/balance", auth=(api_key or "", ""))
            else:
                return True, "Runs locally, no key needed.", {}
            if r.status_code == 200:
                return True, "Key works.", {}
            return False, f"{spec.name} rejected the key (HTTP {r.status_code}).", {}
    except httpx.HTTPError as e:
        return False, f"Could not reach {spec.name}: {e}", {}


async def save_key(db: AsyncSession, ws: Workspace, provider: str, api_key: str | None, base_url: str | None,
                   extra: dict | None = None) -> ProviderCredential:
    spec = PROVIDERS[provider]
    ok, message, meta = await validate_key(provider, api_key, base_url)
    payload = {"api_key": api_key, "base_url": base_url, **(extra or {})}
    row = (await db.execute(select(ProviderCredential).where(
        ProviderCredential.workspace_id == ws.id, ProviderCredential.provider == provider))).scalar_one_or_none()
    if not row:
        row = ProviderCredential(workspace_id=ws.id, provider=provider, category=spec.categories[0], enc_payload="", masked="")
        db.add(row)
    row.enc_payload = encrypt_json(ws.id, ws.settings["dek"], f"cred:{provider}", payload)
    row.masked = mask(api_key or base_url or "")
    row.status = "valid" if ok else "invalid"
    row.error = None if ok else message
    row.meta = {k: v for k, v in meta.items() if k == "models"}
    row.last_validated_at = utcnow()
    await db.commit()
    invalidate(ws.id)
    log.info(f"{ws.id}: saved {provider} key → {row.status}")
    return row
