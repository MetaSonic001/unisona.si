"""Phone calls via Twilio, Exotel, Plivo or Telnyx (credentials per workspace = BYOK).

Phone audio arrives over a provider media-stream WebSocket. Pipecat's serializer for that
provider converts it, and the call runs through the *same* voice session as browser calls.
A public URL (PUBLIC_WEBHOOK_URL, e.g. an ngrok tunnel) is required for providers to reach us.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlencode
from xml.sax.saxutils import escape

import httpx
from fastapi import WebSocket
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..log import feature_unavailable, get_logger
from ..models import Channel, DndEntry, Workspace
from .common import channel_secret

log = get_logger("telephony")


def public_base() -> str | None:
    if not settings.public_webhook_url:
        feature_unavailable("Phone calls", "PUBLIC_WEBHOOK_URL", "providers need a public HTTPS URL, e.g. ngrok")
        return None
    return settings.public_webhook_url.rstrip("/")


def ws_url(channel_id: str, **params) -> str:
    base = public_base() or settings.api_url
    wss = base.replace("https://", "wss://").replace("http://", "ws://")
    q = f"?{urlencode(params)}" if params else ""
    return f"{wss}/telephony/{channel_id}/ws{q}"


PLAN_CONCURRENCY = {"free": 2, "starter": 5, "growth": 20, "scale": 100, "agency": 50}


def call_limit(ws: Workspace) -> int:
    """Simultaneous calls allowed for a workspace (plan default, overridable in workspace settings)."""
    override = (ws.settings or {}).get("max_concurrent_calls")
    return int(override) if override else PLAN_CONCURRENCY.get(ws.plan, 2)


def active_calls(ws_id: str) -> int:
    from ..voice.session import ACTIVE

    return sum(1 for s in ACTIVE.values() if s.ws_id == ws_id)


def at_capacity(ws: Workspace) -> bool:
    return active_calls(ws.id) >= call_limit(ws)


def twiml_stream(channel_id: str, from_number: str = "", to_number: str = "", direction: str = "inbound", target_id: str = "") -> str:
    url = escape(ws_url(channel_id))
    params = "".join(f'<Parameter name="{k}" value="{escape(v)}"/>' for k, v in
                     {"from": from_number, "to": to_number, "direction": direction, "target_id": target_id}.items() if v)
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Connect><Stream url="{url}">{params}</Stream></Connect></Response>'


def verify_twilio(auth_token: str, url: str, form: dict, signature: str | None) -> bool:
    if not auth_token:
        return settings.is_dev
    data = url + "".join(f"{k}{form[k]}" for k in sorted(form))
    expected = base64.b64encode(hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature or "")


async def handle_media_ws(websocket: WebSocket, channel_id: str) -> None:
    """Accept a provider media stream and run the voice session on it."""
    from pipecat.runner.utils import parse_telephony_websocket
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

    from ..voice.session import run_voice_session

    await websocket.accept()
    transport_type, call_data = await parse_telephony_websocket(websocket)
    async with SessionLocal() as db:
        ch = await db.get(Channel, channel_id)
        if not ch or not ch.enabled:
            await websocket.close()
            return
        ws = await db.get(Workspace, ch.workspace_id)
        secret = channel_secret(ws, ch)
    params = FastAPIWebsocketParams(audio_in_enabled=True, audio_out_enabled=True, add_wav_header=False)
    body = call_data.get("body", {}) or {}
    from_number = body.get("from") or call_data.get("from") or ""
    to_number = body.get("to") or call_data.get("to") or ""
    direction = body.get("direction", "inbound")
    if transport_type == "twilio":
        from pipecat.serializers.twilio import TwilioFrameSerializer

        params.serializer = TwilioFrameSerializer(stream_sid=call_data["stream_id"], call_sid=call_data["call_id"],
                                                  account_sid=ch.config.get("account_sid", ""), auth_token=secret.get("auth_token", ""))
    elif transport_type == "exotel":
        from pipecat.serializers.exotel import ExotelFrameSerializer

        params.serializer = ExotelFrameSerializer(stream_sid=call_data["stream_id"], call_sid=call_data["call_id"])
    elif transport_type == "plivo":
        from pipecat.serializers.plivo import PlivoFrameSerializer

        params.serializer = PlivoFrameSerializer(stream_id=call_data["stream_id"], call_id=call_data["call_id"],
                                                 auth_id=ch.config.get("auth_id", ""), auth_token=secret.get("auth_token", ""))
    elif transport_type == "telnyx":
        from pipecat.serializers.telnyx import TelnyxFrameSerializer

        params.serializer = TelnyxFrameSerializer(stream_id=call_data["stream_id"], call_control_id=call_data["call_id"],
                                                  outbound_encoding=call_data.get("outbound_encoding", "PCMU"), inbound_encoding="PCMU",
                                                  api_key=secret.get("api_key", ""))
    agent_id = body.get("agent_id") or ch.agent_id
    try:
        from ..voice.session import _agent_snapshot

        snap = await _agent_snapshot(ch.workspace_id, agent_id, False)
        if snap["cfg"]["voice"].get("noise_filter", True):
            from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

            params.audio_in_filter = RNNoiseFilter()  # phone lines in busy streets/markets: suppress background noise
    except Exception as e:
        log.warning(f"Noise filter unavailable: {e}")
    transport = FastAPIWebsocketTransport(websocket=websocket, params=params)
    caller = to_number if direction == "outbound" else from_number
    await run_voice_session(transport, ws_id=ch.workspace_id, agent_id=agent_id, channel="phone",
                            identifiers={"phone": caller} if caller else {}, sample_rate=8000,
                            call_meta={"transport": transport_type, "from": from_number, "to": to_number, "direction": direction,
                                       "provider_call_id": call_data.get("call_id"), "target_id": body.get("target_id"),
                                       "channel_id": channel_id, "provider": ch.config.get("provider", transport_type)})


async def is_blocked(ws_id: str, number: str) -> bool:
    async with SessionLocal() as db:
        return (await db.execute(select(DndEntry).where(DndEntry.workspace_id == ws_id, DndEntry.value == number))).scalar_one_or_none() is not None


async def dial(ws: Workspace, ch: Channel, to: str, *, target_id: str = "", variables: dict | None = None,
               purpose: str = "transactional", skip_compliance: bool = False) -> dict:
    """Place an outbound AI call. Returns provider response."""
    base = public_base()
    if not base:
        raise RuntimeError("Outbound calls need PUBLIC_WEBHOOK_URL")
    if at_capacity(ws):
        raise RuntimeError(f"All {call_limit(ws)} call lines are busy (plan limit); retry shortly")
    if not skip_compliance:
        from ..brain.identity import find_contact
        from ..services.compliance import check_outbound

        async with SessionLocal() as db:
            contact = await find_contact(db, ws.id, {"phone": to})
            ok, why = await check_outbound(db, ws, contact, to, "voice", purpose)
        if not ok:
            raise RuntimeError(f"Not calling {to}: {why}")
    secret = channel_secret(ws, ch)
    provider = ch.config.get("provider", "twilio")
    from_number = ch.config.get("phone_number", "")
    async with httpx.AsyncClient(timeout=20) as c:
        if provider == "twilio":
            sid = ch.config.get("account_sid", "")
            r = await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json", auth=(sid, secret.get("auth_token", "")),
                             data={"To": to, "From": from_number, "Twiml": twiml_stream(ch.id, from_number, to, "outbound", target_id),
                                   "MachineDetection": "DetectMessageEnd", "AsyncAmd": "true",
                                   "AsyncAmdStatusCallback": f"{base}/telephony/{ch.id}/amd", "AsyncAmdStatusCallbackMethod": "POST",
                                   "StatusCallback": f"{base}/telephony/{ch.id}/status"})
        elif provider == "exotel":
            sub = ch.config.get("subdomain", "api.exotel.com")
            sid = ch.config.get("account_sid", "")
            r = await c.post(f"https://{sub}/v1/Accounts/{sid}/Calls/connect.json", auth=(secret.get("api_key", ""), secret.get("api_token", "")),
                             data={"From": to, "CallerId": from_number, "Url": ch.config.get("exoml_url", ""), "CustomField": target_id})
        elif provider == "plivo":
            auth_id = ch.config.get("auth_id", "")
            r = await c.post(f"https://api.plivo.com/v1/Account/{auth_id}/Call/", auth=(auth_id, secret.get("auth_token", "")),
                             json={"from": from_number, "to": to, "answer_url": f"{base}/telephony/{ch.id}/plivo-answer?target_id={target_id}",
                                   "answer_method": "GET", "machine_detection": "true",
                                   "machine_detection_url": f"{base}/telephony/{ch.id}/amd"})
        elif provider == "telnyx":
            r = await c.post("https://api.telnyx.com/v2/calls", headers={"Authorization": f"Bearer {secret.get('api_key', '')}"},
                             json={"connection_id": ch.config.get("connection_id", ""), "to": to, "from": from_number,
                                   "answering_machine_detection": "detect", "stream_url": ws_url(ch.id), "stream_track": "inbound_track",
                                   "client_state": base64.b64encode(target_id.encode()).decode()})
        else:
            raise RuntimeError(f"Outbound calls not supported for {provider}")
    if r.status_code >= 300:
        raise RuntimeError(f"{provider} dial failed ({r.status_code}): {r.text[:200]}")
    log.info(f"Outbound call to {to} via {provider} queued")
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else {"status": r.status_code}


async def send_sms(ws: Workspace, ch: Channel, to: str, text: str) -> None:
    secret = channel_secret(ws, ch)
    provider = ch.config.get("provider", "twilio")
    from_number = ch.config.get("sms_number") or ch.config.get("phone_number", "")
    async with httpx.AsyncClient(timeout=15) as c:
        if provider == "twilio":
            sid = ch.config.get("account_sid", "")
            r = await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, secret.get("auth_token", "")),
                             data={"To": to, "From": from_number, "Body": text[:1500]})
        elif provider == "plivo":
            auth_id = ch.config.get("auth_id", "")
            r = await c.post(f"https://api.plivo.com/v1/Account/{auth_id}/Message/", auth=(auth_id, secret.get("auth_token", "")),
                             json={"src": from_number, "dst": to, "text": text[:1500]})
        elif provider == "telnyx":
            r = await c.post("https://api.telnyx.com/v2/messages", headers={"Authorization": f"Bearer {secret.get('api_key', '')}"},
                             json={"from": from_number, "to": to, "text": text[:1500]})
        elif provider == "exotel":
            sub, sid = ch.config.get("subdomain", "api.exotel.com"), ch.config.get("account_sid", "")
            r = await c.post(f"https://{sub}/v1/Accounts/{sid}/Sms/send.json", auth=(secret.get("api_key", ""), secret.get("api_token", "")),
                             data={"From": from_number, "To": to, "Body": text[:1500], "DltEntityId": ch.config.get("dlt_entity_id", ""),
                                   "DltTemplateId": ch.config.get("dlt_template_id", "")})
        else:
            raise RuntimeError(f"SMS not supported for {provider}")
        if r.status_code >= 300:
            raise RuntimeError(f"SMS failed ({r.status_code}): {r.text[:200]}")


async def handle_inbound_sms(channel_id: str, sender: str, text: str, msg_id: str | None = None) -> dict | None:
    """Two-way SMS: the same brain answers texts sent to the agent's phone number."""
    from ..brain.respond import Turn, respond
    from ..models import Agent

    async with SessionLocal() as db:
        ch = await db.get(Channel, channel_id)
        if not ch or not ch.enabled or not ch.config.get("sms_enabled", True):
            return None
        ws = await db.get(Workspace, ch.workspace_id)
        agent = await db.get(Agent, ch.agent_id)
        reply = await respond(db, Turn(ws=ws, agent=agent, channel="sms", text=text, identifiers={"phone": sender},
                                       channel_ref=f"sms:{sender}", channel_msg_id=msg_id))
        if reply.get("text"):
            try:
                await send_sms(ws, ch, sender, reply["text"])
            except Exception as e:
                log.error(f"SMS reply failed: {e}")
        return reply


# ── Live call transfer ───────────────────────────────────────────────────────
def whisper_url(channel_id: str, text: str) -> str:
    from urllib.parse import quote

    return f"{public_base() or settings.api_url}/telephony/{channel_id}/whisper?text={quote(text[:600])}"


async def transfer_call(ws: Workspace, ch: Channel, provider_call_id: str, to: str, *, mode: str = "warm", summary: str = "",
                        caller_id: str | None = None) -> str:
    """Move a live phone call to a human. Warm = the human first hears an AI summary of the call, then is connected."""
    from urllib.parse import quote

    secret = channel_secret(ws, ch)
    provider = ch.config.get("provider", "twilio")
    from_number = caller_id or ch.config.get("phone_number", "")
    base = public_base() or settings.api_url
    async with httpx.AsyncClient(timeout=15) as c:
        if provider == "twilio":
            sid = ch.config.get("account_sid", "")
            number_attr = f' url="{escape(whisper_url(ch.id, summary))}"' if mode == "warm" and summary else ""
            twiml = (f'<?xml version="1.0" encoding="UTF-8"?><Response><Dial callerId="{escape(from_number)}" timeout="25">'
                     f"<Number{number_attr}>{escape(to)}</Number></Dial>"
                     "<Say>Sorry, nobody is available right now. We will call you back shortly.</Say></Response>")
            r = await c.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls/{provider_call_id}.json",
                             auth=(sid, secret.get("auth_token", "")), data={"Twiml": twiml})
        elif provider == "plivo":
            auth_id = ch.config.get("auth_id", "")
            r = await c.post(f"https://api.plivo.com/v1/Account/{auth_id}/Call/{provider_call_id}/", auth=(auth_id, secret.get("auth_token", "")),
                             json={"legs": "aleg", "aleg_url": f"{base}/telephony/{ch.id}/plivo-dial?to={quote(to)}&summary={quote(summary[:500])}",
                                   "aleg_method": "GET"})
        elif provider == "telnyx":
            r = await c.post(f"https://api.telnyx.com/v2/calls/{provider_call_id}/actions/transfer",
                             headers={"Authorization": f"Bearer {secret.get('api_key', '')}"}, json={"to": to, "from": from_number})
        else:
            raise RuntimeError(f"live transfer is not supported for {provider}")
    if r.status_code >= 300:
        raise RuntimeError(f"{provider} transfer failed ({r.status_code}): {r.text[:200]}")
    log.info(f"Transferred call {provider_call_id} to {to} ({mode})")
    return "transferred"
