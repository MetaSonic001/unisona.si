"""Native integrations: HubSpot, Salesforce, Cal.com and Google Calendar (all BYOK / your own account),
plus incoming webhooks so Zapier, Make, n8n or any app can push leads and trigger AI calls.

CRM sync is event-driven: lead captured, form submitted, conversation analysed, appointment booked
and payment received are mirrored to the connected CRM by a background job.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import SessionLocal, utcnow
from ..log import feature_unavailable, get_logger
from ..models import Appointment, Contact, Conversation, Integration, Workspace
from ..security.crypto import decrypt_json, encrypt_json

log = get_logger("integrations")

CATALOG = {
    "hubspot": {"name": "HubSpot", "kind": "crm", "fields": [{"key": "token", "label": "Private app access token", "secret": True}],
                "help": "HubSpot → Settings → Integrations → Private apps → create with CRM contacts/deals/notes scopes."},
    "salesforce": {"name": "Salesforce", "kind": "crm", "fields": [
        {"key": "domain", "label": "My Domain URL (https://yourco.my.salesforce.com)"},
        {"key": "client_id", "label": "Connected app consumer key"},
        {"key": "client_secret", "label": "Connected app consumer secret", "secret": True}],
        "help": "Create a Connected App with the OAuth Client Credentials flow enabled and a run-as user."},
    "calcom": {"name": "Cal.com", "kind": "calendar", "fields": [
        {"key": "api_key", "label": "API key", "secret": True}, {"key": "event_type_id", "label": "Event type ID"}],
        "help": "Cal.com → Settings → Developer → API keys. The agent offers and books this event type."},
    "google_calendar": {"name": "Google Calendar", "kind": "calendar", "fields": [], "oauth": True,
                        "help": "Connect with Google; busy times block slots and bookings appear on your calendar."},
}
SYNC_EVENTS = {"lead.captured", "contact.created", "form.submitted", "analysis.completed", "appointment.booked", "payment.received"}


def secret_of(ws: Workspace, it: Integration) -> dict:
    return decrypt_json(ws.id, ws.settings["dek"], f"integration:{it.type}", it.enc_secret) if it.enc_secret else {}


def set_secret(ws: Workspace, it: Integration, data: dict) -> None:
    it.enc_secret = encrypt_json(ws.id, ws.settings["dek"], f"integration:{it.type}", data)


async def get(db: AsyncSession, ws_id: str, type_: str) -> Integration | None:
    return (await db.execute(select(Integration).where(Integration.workspace_id == ws_id, Integration.type == type_,
                                                       Integration.status == "connected"))).scalar_one_or_none()


# ── HubSpot ──────────────────────────────────────────────────────────────────
class HubSpot:
    base = "https://api.hubapi.com"

    def __init__(self, token: str):
        self.h = {"Authorization": f"Bearer {token}", "content-type": "application/json"}

    async def test(self) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.base}/crm/v3/objects/contacts", headers=self.h, params={"limit": 1})
        if r.status_code >= 300:
            raise RuntimeError(f"HubSpot rejected the token ({r.status_code})")
        return "Connected to HubSpot"

    async def upsert_contact(self, contact: Contact) -> str | None:
        props = {k: v for k, v in {"email": contact.email, "phone": contact.phone, "firstname": (contact.name or "").split(" ")[0] or None,
                                   "lastname": " ".join((contact.name or "").split(" ")[1:]) or None,
                                   "lifecyclestage": {"lead": "lead", "customer": "customer"}.get(contact.lifecycle)}.items() if v}
        async with httpx.AsyncClient(timeout=15) as c:
            hid = None
            for prop in ("email", "phone"):
                if props.get(prop):
                    r = await c.post(f"{self.base}/crm/v3/objects/contacts/search", headers=self.h, json={
                        "filterGroups": [{"filters": [{"propertyName": prop, "operator": "EQ", "value": props[prop]}]}], "limit": 1})
                    res = r.json().get("results") if r.status_code < 300 else []
                    if res:
                        hid = res[0]["id"]
                        break
            if hid:
                await c.patch(f"{self.base}/crm/v3/objects/contacts/{hid}", headers=self.h, json={"properties": props})
            else:
                r = await c.post(f"{self.base}/crm/v3/objects/contacts", headers=self.h, json={"properties": props})
                if r.status_code >= 300:
                    raise RuntimeError(f"HubSpot create failed: {r.text[:200]}")
                hid = r.json()["id"]
        return hid

    async def note(self, hubspot_contact_id: str, body: str) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(f"{self.base}/crm/v3/objects/notes", headers=self.h, json={
                "properties": {"hs_note_body": body[:60000], "hs_timestamp": int(time.time() * 1000)},
                "associations": [{"to": {"id": hubspot_contact_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]}]})


# ── Salesforce (client-credentials connected app) ────────────────────────────
class Salesforce:
    def __init__(self, domain: str, client_id: str, client_secret: str):
        self.domain, self.cid, self.secret = domain.rstrip("/"), client_id, client_secret
        self.token: str | None = None

    async def _auth(self, c: httpx.AsyncClient) -> dict:
        if not self.token:
            r = await c.post(f"{self.domain}/services/oauth2/token", data={"grant_type": "client_credentials", "client_id": self.cid,
                                                                          "client_secret": self.secret})
            if r.status_code >= 300:
                raise RuntimeError(f"Salesforce auth failed: {r.text[:200]}")
            self.token = r.json()["access_token"]
        return {"Authorization": f"Bearer {self.token}"}

    async def test(self) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            await self._auth(c)
        return "Connected to Salesforce"

    async def upsert_lead(self, contact: Contact) -> str | None:
        async with httpx.AsyncClient(timeout=15) as c:
            h = await self._auth(c)
            api = f"{self.domain}/services/data/v61.0"
            lid = None
            if contact.email:
                q = f"SELECT Id FROM Lead WHERE Email = '{contact.email.replace(chr(39), '')}' LIMIT 1"
                r = await c.get(f"{api}/query", headers=h, params={"q": q})
                recs = r.json().get("records", []) if r.status_code < 300 else []
                lid = recs[0]["Id"] if recs else None
            name = (contact.name or "Unknown").split(" ")
            body = {"LastName": " ".join(name[1:]) or name[0], "FirstName": name[0] if len(name) > 1 else None,
                    "Company": (contact.fields or {}).get("company") or "Unknown", "Email": contact.email, "Phone": contact.phone,
                    "LeadSource": "Unisona AI agent"}
            body = {k: v for k, v in body.items() if v}
            if lid:
                await c.patch(f"{api}/sobjects/Lead/{lid}", headers=h, json=body)
            else:
                r = await c.post(f"{api}/sobjects/Lead", headers=h, json=body)
                if r.status_code >= 300:
                    raise RuntimeError(f"Salesforce lead failed: {r.text[:200]}")
                lid = r.json()["id"]
            return lid

    async def task(self, who_id: str, subject: str, description: str) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            h = await self._auth(c)
            await c.post(f"{self.domain}/services/data/v61.0/sobjects/Task", headers=h, json={
                "WhoId": who_id, "Subject": subject[:255], "Description": description[:32000], "Status": "Completed", "TaskSubtype": "Call"})


# ── Cal.com ──────────────────────────────────────────────────────────────────
class CalCom:
    base = "https://api.cal.com/v2"

    def __init__(self, api_key: str, event_type_id: str):
        self.h = {"Authorization": f"Bearer {api_key}", "cal-api-version": "2024-09-04"}
        self.event_type_id = int(event_type_id) if str(event_type_id).isdigit() else event_type_id

    async def test(self) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.base}/me", headers={**self.h, "cal-api-version": "2024-06-11"})
        if r.status_code >= 300:
            raise RuntimeError(f"Cal.com rejected the key ({r.status_code})")
        return "Connected to Cal.com"

    async def slots(self, day: datetime, tz: str) -> list[str]:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.base}/slots", headers=self.h, params={
                "eventTypeId": self.event_type_id, "start": day.strftime("%Y-%m-%d"), "end": day.strftime("%Y-%m-%d"), "timeZone": tz})
        data = r.json().get("data", {}) if r.status_code < 300 else {}
        return [s.get("start") if isinstance(s, dict) else s for v in data.values() for s in v]

    async def book(self, start_iso: str, name: str, email: str, tz: str, phone: str | None = None) -> dict:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{self.base}/bookings", headers={**self.h, "cal-api-version": "2024-08-13"}, json={
                "eventTypeId": self.event_type_id, "start": start_iso,
                "attendee": {"name": name or "Customer", "email": email or "noreply@unisona.local", "timeZone": tz,
                             **({"phoneNumber": phone} if phone else {})}})
        if r.status_code >= 300:
            raise RuntimeError(f"Cal.com booking failed: {r.text[:200]}")
        return r.json().get("data", {})


# ── Google Calendar (OAuth) ──────────────────────────────────────────────────
GOOGLE_SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.freebusy"


def google_redirect_uri() -> str:
    return f"{(settings.public_webhook_url or settings.api_url).rstrip('/')}/integrations/google/callback"


def google_auth_url(state: str) -> str:
    if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
        feature_unavailable("Google Calendar sync", "GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET")
        raise RuntimeError("Google Calendar needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env")
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.google_oauth_client_id, "redirect_uri": google_redirect_uri(), "response_type": "code",
        "scope": GOOGLE_SCOPES, "access_type": "offline", "prompt": "consent", "state": state})


async def google_exchange(code: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": settings.google_oauth_client_id, "client_secret": settings.google_oauth_client_secret,
            "redirect_uri": google_redirect_uri(), "grant_type": "authorization_code"})
    if r.status_code >= 300:
        raise RuntimeError(f"Google token exchange failed: {r.text[:200]}")
    return r.json()


class GoogleCalendar:
    def __init__(self, refresh_token: str, calendar_id: str = "primary"):
        self.refresh, self.cal = refresh_token, calendar_id

    async def _h(self, c: httpx.AsyncClient) -> dict:
        r = await c.post("https://oauth2.googleapis.com/token", data={
            "client_id": settings.google_oauth_client_id, "client_secret": settings.google_oauth_client_secret,
            "refresh_token": self.refresh, "grant_type": "refresh_token"})
        if r.status_code >= 300:
            raise RuntimeError("Google authorization expired; reconnect Google Calendar")
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    async def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post("https://www.googleapis.com/calendar/v3/freeBusy", headers=await self._h(c), json={
                "timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": self.cal}]})
        periods = ((r.json().get("calendars") or {}).get(self.cal) or {}).get("busy", []) if r.status_code < 300 else []
        return [(datetime.fromisoformat(p["start"].replace("Z", "+00:00")), datetime.fromisoformat(p["end"].replace("Z", "+00:00"))) for p in periods]

    async def create_event(self, summary: str, start: datetime, end: datetime, description: str = "", attendee: str | None = None) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"https://www.googleapis.com/calendar/v3/calendars/{self.cal}/events", headers=await self._h(c), json={
                "summary": summary, "description": description, "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()},
                **({"attendees": [{"email": attendee}]} if attendee else {})})
        return r.json().get("id", "") if r.status_code < 300 else ""


async def client_for(db: AsyncSession, ws: Workspace, type_: str):
    it = await get(db, ws.id, type_)
    if not it:
        return None
    sec = secret_of(ws, it)
    if type_ == "hubspot":
        return HubSpot(sec.get("token", ""))
    if type_ == "salesforce":
        return Salesforce(it.config.get("domain", ""), it.config.get("client_id", ""), sec.get("client_secret", ""))
    if type_ == "calcom":
        return CalCom(sec.get("api_key", ""), it.config.get("event_type_id", ""))
    if type_ == "google_calendar":
        return GoogleCalendar(sec.get("refresh_token", ""), it.config.get("calendar_id", "primary"))
    return None


async def google_busy(db: AsyncSession, ws: Workspace, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    try:
        gc = await client_for(db, ws, "google_calendar")
        return await gc.busy(start, end) if gc else []
    except Exception as e:
        log.warning(f"Google free/busy failed: {e}")
        return []


# ── Event-driven CRM sync ────────────────────────────────────────────────────
async def sync_event(ws_id: str, event: str, data: dict[str, Any]) -> dict:
    if event not in SYNC_EVENTS:
        return {"skipped": event}
    out: dict[str, Any] = {}
    async with SessionLocal() as db:
        ws = await db.get(Workspace, ws_id)
        its = (await db.execute(select(Integration).where(Integration.workspace_id == ws_id, Integration.status == "connected"))).scalars().all()
        if not its:
            return {"skipped": "no integrations"}
        contact_id = data.get("contact_id")
        conv = await db.get(Conversation, data["conversation_id"]) if data.get("conversation_id") else None
        if not contact_id and conv:
            contact_id = conv.contact_id
        contact = await db.get(Contact, contact_id) if contact_id else None
        for it in its:
            try:
                if it.type == "hubspot" and contact:
                    hs = await client_for(db, ws, "hubspot")
                    hid = await hs.upsert_contact(contact)
                    if event == "analysis.completed" and conv and conv.summary:
                        await hs.note(hid, f"<b>Unisona AI conversation ({conv.channel})</b><br>{conv.summary}<br>Outcome: {conv.outcome or '-'}")
                    elif event in {"appointment.booked", "payment.received", "form.submitted"}:
                        await hs.note(hid, f"Unisona: {event.replace('.', ' ')} {data}")
                    out["hubspot"] = hid
                elif it.type == "salesforce" and contact:
                    sf = await client_for(db, ws, "salesforce")
                    lid = await sf.upsert_lead(contact)
                    if event == "analysis.completed" and conv and conv.summary:
                        await sf.task(lid, f"AI {conv.channel} conversation: {conv.outcome or 'completed'}", conv.summary)
                    out["salesforce"] = lid
                elif it.type == "google_calendar" and event == "appointment.booked" and data.get("appointment_id"):
                    appt = await db.get(Appointment, data["appointment_id"])
                    gc = await client_for(db, ws, "google_calendar")
                    if appt and gc:
                        out["google_event"] = await gc.create_event(appt.title, appt.start_at, appt.end_at, appt.notes,
                                                                    contact.email if contact else None)
                it.last_sync_at, it.error = utcnow(), None
            except Exception as e:
                it.error = str(e)[:300]
                log.warning(f"{it.type} sync failed for {event}: {e}")
        await db.commit()
    return out


async def test(type_: str, config: dict, secret: dict) -> str:
    if type_ == "hubspot":
        return await HubSpot(secret.get("token", "")).test()
    if type_ == "salesforce":
        return await Salesforce(config.get("domain", ""), config.get("client_id", ""), secret.get("client_secret", "")).test()
    if type_ == "calcom":
        return await CalCom(secret.get("api_key", ""), config.get("event_type_id", "")).test()
    return "ok"


def day_window(day: datetime) -> tuple[datetime, datetime]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)
