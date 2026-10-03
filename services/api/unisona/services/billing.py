"""Plans, entitlements and Dodo Payments (checkout + signed webhooks).

BYOK model: customers pay AI providers directly; Unisona charges for the platform.
Every paid plan includes unlimited channels.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

import httpx

from ..config import settings
from ..log import feature_unavailable, get_logger

log = get_logger("billing")

PLANS = [
    {"id": "free", "name": "Free", "inr": 0, "usd": 0, "agents": 1, "voice_minutes": 60, "messages": 500, "seats": 1, "contacts": 250,
     "features": ["Web chat, widget & browser voice", "1 agent", "60 voice min / month", "Knowledge base & glass-box RAG", "Bring your own AI keys"]},
    {"id": "starter", "name": "Starter", "inr": 1499, "usd": 19, "agents": 3, "voice_minutes": 1000, "messages": 10000, "seats": 3, "contacts": 2500,
     "features": ["Every channel incl. WhatsApp, Telegram & phone", "3 agents", "1,000 voice min", "Cross-channel memory", "CRM & booking calendar"]},
    {"id": "growth", "name": "Growth", "inr": 4999, "usd": 59, "agents": 10, "voice_minutes": 5000, "messages": 50000, "seats": 10, "contacts": 25000,
     "popular": True,
     "features": ["10 agents", "5,000 voice min", "Campaigns & automations", "Evaluations & red-teaming", "Remove branding", "Live monitor & takeover", "1 client sub-account"]},
    {"id": "scale", "name": "Scale", "inr": 14999, "usd": 179, "agents": 9999, "voice_minutes": 20000, "messages": 250000, "seats": 25, "contacts": 250000,
     "features": ["Unlimited agents", "20,000 voice min", "3 client sub-accounts", "Priority support", "1-year retention"]},
    {"id": "agency", "name": "Agency", "inr": 24999, "usd": 297, "agents": 9999, "voice_minutes": 25000, "messages": 300000, "seats": 50, "contacts": 10**7,
     "features": ["Unlimited client workspaces", "White-label app & widget", "Blueprints (clone setups)", "Rebill your clients"]},
    {"id": "enterprise", "name": "Enterprise", "inr": None, "usd": None, "agents": 10**6, "voice_minutes": 10**7, "messages": 10**8, "seats": 10**6, "contacts": 10**8,
     "features": ["SSO/SAML & SCIM", "On-prem / private cloud", "Data residency (India / EU / US)", "SLA & dedicated success", "Custom integrations"]},
]
SUB_ACCOUNTS = {"free": 0, "starter": 0, "growth": 1, "scale": 3, "agency": 1000, "enterprise": 10**6}
for _p in PLANS:
    _p["sub_accounts"] = SUB_ACCOUNTS.get(_p["id"], 0)
PLAN_BY_ID = {p["id"]: p for p in PLANS}
OVERAGE = {"voice_minute_inr": 0.80, "voice_minute_usd": 0.012, "message_inr": 0.04, "message_usd": 0.0006}


def api_base() -> str:
    return "https://live.dodopayments.com" if settings.dodo_environment.startswith("live") else "https://test.dodopayments.com"


async def create_checkout(plan_id: str, currency: str, email: str | None, workspace_id: str) -> dict:
    if not settings.dodo_payments_api_key:
        feature_unavailable("Paid plan checkout", "DODO_PAYMENTS_API_KEY")
        raise RuntimeError("Payments are not configured yet. Add DODO_PAYMENTS_API_KEY to .env.")
    product = os.getenv(f"DODO_PRODUCT_{plan_id.upper()}_{currency.upper()}") or os.getenv(f"DODO_PRODUCT_{plan_id.upper()}")
    if not product:
        raise RuntimeError(f"Set DODO_PRODUCT_{plan_id.upper()} (Dodo product id) in .env")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{api_base()}/checkouts", headers={"Authorization": f"Bearer {settings.dodo_payments_api_key}"}, json={
            "product_cart": [{"product_id": product, "quantity": 1}],
            "customer": {"email": email} if email else None,
            "return_url": f"{settings.app_url}/app/settings/billing?status=success",
            "metadata": {"workspace_id": workspace_id, "plan": plan_id},
        })
    if r.status_code >= 300:
        raise RuntimeError(f"Dodo checkout failed ({r.status_code}): {r.text[:200]}")
    return r.json()


def verify_webhook(body: bytes, headers) -> bool:
    """Standard Webhooks signature: base64(HMAC-SHA256(secret, f"{id}.{ts}.{body}"))."""
    secret = settings.dodo_webhook_secret
    if not secret:
        return False
    key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    msg_id, ts, sig = headers.get("webhook-id", ""), headers.get("webhook-timestamp", ""), headers.get("webhook-signature", "")
    expected = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, s.split(",", 1)[-1]) for s in sig.split())
