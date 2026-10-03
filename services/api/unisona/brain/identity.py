"""Cross-channel identity: one contact per person, many identifiers.

Identifier types: phone (E.164), wa_id (WhatsApp, which *is* a phone number), telegram_id,
email, web_session, external_id. A WhatsApp message and a phone call from the same
number resolve to the same contact automatically. A web visitor links to a contact when
they share an email/phone (verified by OTP when `verify=True`) or through widget HMAC
identity verification.
"""
from __future__ import annotations

import phonenumbers
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import utcnow
from ..log import get_logger
from ..models import (Activity, Appointment, Contact, ContactFact, ContactIdentity, Conversation, Deal, Note, Task)

log = get_logger("identity")


def normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit() and len(raw) > 10:
        raw = "+" + raw
    try:
        num = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_possible_number(num):
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def normalize(type_: str, value: str) -> str | None:
    if not value:
        return None
    if type_ in {"phone", "wa_id"}:
        return normalize_phone(value)
    if type_ == "email":
        return value.strip().lower()
    return str(value).strip()


async def find_contact(db: AsyncSession, ws_id: str, identifiers: dict[str, str]) -> Contact | None:
    for type_, raw in identifiers.items():
        value = normalize(type_, raw)
        if not value:
            continue
        types = ["phone", "wa_id"] if type_ in {"phone", "wa_id"} else [type_]
        row = (await db.execute(select(ContactIdentity).where(
            ContactIdentity.workspace_id == ws_id, ContactIdentity.type.in_(types), ContactIdentity.value == value))).scalars().first()
        if row:
            return await db.get(Contact, row.contact_id)
    return None


async def add_identity(db: AsyncSession, contact: Contact, type_: str, raw: str, *, verified: bool = False) -> None:
    value = normalize(type_, raw)
    if not value:
        return
    existing = (await db.execute(select(ContactIdentity).where(
        ContactIdentity.workspace_id == contact.workspace_id, ContactIdentity.type == type_, ContactIdentity.value == value))).scalar_one_or_none()
    if existing:
        if existing.contact_id != contact.id:
            other = await db.get(Contact, existing.contact_id)
            if other:
                await merge_contacts(db, keep=contact, drop=other)
        return
    db.add(ContactIdentity(workspace_id=contact.workspace_id, contact_id=contact.id, type=type_, value=value, verified=verified))
    if type_ in {"phone", "wa_id"} and not contact.phone:
        contact.phone = value
    if type_ == "email" and not contact.email:
        contact.email = value
    await db.flush()


async def resolve_contact(db: AsyncSession, ws_id: str, identifiers: dict[str, str], *, name: str | None = None,
                          channel: str | None = None) -> Contact:
    """Find the contact for these identifiers or create one, attaching any new identifiers."""
    identifiers = {k: v for k, v in identifiers.items() if v}
    contact = await find_contact(db, ws_id, identifiers)
    if not contact:
        contact = Contact(workspace_id=ws_id, name=name, source_channel=channel, last_seen_at=utcnow())
        db.add(contact)
        await db.flush()
        db.add(Activity(workspace_id=ws_id, contact_id=contact.id, type="contact.created", title=f"New contact via {channel or 'unknown'}"))
        log.info(f"New contact {contact.id} via {channel}")
    else:
        contact.last_seen_at = utcnow()
        if name and not contact.name:
            contact.name = name
    for type_, raw in identifiers.items():
        await add_identity(db, contact, type_, raw)
    # wa_id is also a phone identity so calls from the same number link up
    if "wa_id" in identifiers:
        await add_identity(db, contact, "phone", identifiers["wa_id"])
    await db.flush()
    return contact


async def merge_contacts(db: AsyncSession, keep: Contact, drop: Contact) -> None:
    if keep.id == drop.id:
        return
    ws = keep.workspace_id
    for model in (ContactIdentity, ContactFact, Conversation, Task, Note, Activity, Appointment, Deal):
        await db.execute(update(model).where(model.workspace_id == ws, model.contact_id == drop.id).values(contact_id=keep.id))
    keep.name = keep.name or drop.name
    keep.email = keep.email or drop.email
    keep.phone = keep.phone or drop.phone
    keep.tags = sorted(set(keep.tags or []) | set(drop.tags or []))
    keep.fields = {**(drop.fields or {}), **(keep.fields or {})}
    keep.score = max(keep.score or 0, drop.score or 0)
    db.add(Activity(workspace_id=ws, contact_id=keep.id, type="contact.merged", title=f"Merged duplicate contact {drop.name or drop.id}",
                    data={"merged_id": drop.id}))
    await db.flush()
    await db.delete(drop)
    await db.flush()
    log.info(f"Merged contact {drop.id} into {keep.id}")
