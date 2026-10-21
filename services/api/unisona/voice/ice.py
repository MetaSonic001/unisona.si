"""ICE servers for browser voice calls (WebRTC).

Locally, STUN is enough: the browser and the API are on the same machine/network. A hosted API behind an
HTTP-only load balancer (Render, Railway, Fly without UDP) cannot receive WebRTC media directly, so both
sides relay through a TURN server. Options (both have free tiers):
  - Cloudflare Realtime TURN: CLOUDFLARE_TURN_KEY_ID + CLOUDFLARE_TURN_API_TOKEN (short-lived credentials, refreshed here)
  - Any TURN provider with static credentials (e.g. Metered): TURN_URLS + TURN_USERNAME + TURN_CREDENTIAL
"""
from __future__ import annotations

import time

import httpx

from ..config import settings
from ..log import feature_unavailable, get_logger

log = get_logger("ice")
STUN = {"urls": ["stun:stun.l.google.com:19302", "stun:stun.cloudflare.com:3478"]}
_cache: tuple[float, list[dict]] = (0.0, [])


async def _cloudflare() -> list[dict]:
    url = f"https://rtc.live.cloudflare.com/v1/turn/keys/{settings.cloudflare_turn_key_id}/credentials/generate-ice-servers"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json={"ttl": 86400}, headers={"Authorization": f"Bearer {settings.cloudflare_turn_api_token}"})
        r.raise_for_status()
        data = r.json().get("iceServers") or []
    servers = data if isinstance(data, list) else [data]
    # Browsers warn about port 53 URLs; drop them.
    for s in servers:
        if isinstance(s.get("urls"), list):
            s["urls"] = [u for u in s["urls"] if ":53?" not in u and not u.endswith(":53")]
    return [s for s in servers if s.get("urls")]


async def ice_servers() -> list[dict]:
    """Browser-format ICE servers (`RTCIceServer` dicts). Cached; Cloudflare credentials are renewed every 12 h."""
    global _cache
    if _cache[1] and _cache[0] > time.time():
        return _cache[1]
    servers: list[dict] = [STUN]
    if settings.cloudflare_turn_key_id and settings.cloudflare_turn_api_token:
        try:
            servers += await _cloudflare()
        except Exception as e:
            log.error(f"Cloudflare TURN credentials failed: {e}. Browser voice calls may not connect from the hosted API.")
            _cache = (time.time() + 60, servers)
            return servers
    elif settings.turn_urls and settings.turn_username:
        servers.append({"urls": [u.strip() for u in settings.turn_urls.split(",") if u.strip()],
                        "username": settings.turn_username, "credential": settings.turn_credential})
    elif not settings.is_dev:
        feature_unavailable("WebRTC relay (TURN) for browser voice", "CLOUDFLARE_TURN_KEY_ID + CLOUDFLARE_TURN_API_TOKEN (or TURN_URLS)",
                            "browser calls to a hosted API usually fail without it; phone calls are unaffected")
    _cache = (time.time() + 12 * 3600, servers)
    return servers


async def rtc_servers():
    from pipecat.transports.smallwebrtc.connection import IceServer

    return [IceServer(urls=s["urls"], username=s.get("username"), credential=s.get("credential")) for s in await ice_servers()]
