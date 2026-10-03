"""CRM: contacts (unified identities + memory + timeline), companies, pipelines, deals, tasks,
notes, calendars, appointments, public booking pages, DND list."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..brain.identity import add_identity, merge_contacts, normalize_phone
from ..brain.tools import free_slots
from ..db import get_db
from ..models import (Activity, Appointment, Calendar, Call, Company, Contact, ContactFact, ContactIdentity, Conversation, Deal,
                      DndEntry, Note, Pipeline, Task)
from ..security.auth import AuthContext, require_auth
from .common import audit, crud_router, get_scoped, to_dict

router = APIRouter(prefix="/crm")


@router.get("/contacts")
async def list_contacts(q: str | None = None, tag: str | None = None, lifecycle: str | None = None, limit: int = 200, offset: int = 0,
                        sort: str = "updated_at", auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    stmt = select(Contact).where(Contact.workspace_id == auth.ws)
    if q:
        stmt = stmt.where(or_(Contact.name.ilike(f"%{q}%"), Contact.email.ilike(f"%{q}%"), Contact.phone.ilike(f"%{q}%")))
    if tag:
        stmt = stmt.where(Contact.tags.contains([tag]))
    if lifecycle:
        stmt = stmt.where(Contact.lifecycle == lifecycle)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar()
    order = {"score": Contact.score.desc(), "name": Contact.name, "created_at": Contact.created_at.desc()}.get(sort, Contact.updated_at.desc())
    rows = (await db.execute(stmt.order_by(order).limit(min(limit, 1000)).offset(offset))).scalars().all()
    ids = [c.id for c in rows]
    channels: dict[str, set[str]] = {}
    if ids:
        for cid, t in (await db.execute(select(ContactIdentity.contact_id, ContactIdentity.type).where(ContactIdentity.contact_id.in_(ids)))).all():
            channels.setdefault(cid, set()).add(t)
    return {"items": [{**to_dict(c), "identity_types": sorted(channels.get(c.id, set()))} for c in rows], "total": total}


@router.post("/contacts")
async def create_contact(body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = Contact(workspace_id=auth.ws, name=body.get("name"), lifecycle=body.get("lifecycle", "lead"), tags=body.get("tags") or [],
                fields=body.get("fields") or {}, source_channel="manual")
    db.add(c)
    await db.flush()
    if body.get("phone"):
        await add_identity(db, c, "phone", body["phone"])
    if body.get("email"):
        await add_identity(db, c, "email", body["email"])
    db.add(Activity(workspace_id=auth.ws, contact_id=c.id, type="contact.created", title="Contact created manually", actor=auth.email or "user"))
    await db.commit()
    from ..services.webhooks import emit

    await emit(auth.ws, "contact.created", {"contact_id": c.id, "name": c.name, "phone": c.phone, "email": c.email})
    return to_dict(c)


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Contact, contact_id, auth)
    ids = [to_dict(i) for i in (await db.execute(select(ContactIdentity).where(ContactIdentity.contact_id == c.id))).scalars()]
    facts = [to_dict(f) for f in (await db.execute(select(ContactFact).where(ContactFact.contact_id == c.id).order_by(ContactFact.valid_from.desc()))).scalars()]
    convs = (await db.execute(select(Conversation).where(Conversation.contact_id == c.id).order_by(Conversation.last_message_at.desc()).limit(50))).scalars().all()
    deals = [to_dict(d) for d in (await db.execute(select(Deal).where(Deal.contact_id == c.id))).scalars()]
    tasks = [to_dict(t) for t in (await db.execute(select(Task).where(Task.contact_id == c.id).order_by(Task.created_at.desc()))).scalars()]
    notes = [to_dict(n) for n in (await db.execute(select(Note).where(Note.contact_id == c.id).order_by(Note.created_at.desc()))).scalars()]
    appts = [to_dict(a) for a in (await db.execute(select(Appointment).where(Appointment.contact_id == c.id).order_by(Appointment.start_at.desc()))).scalars()]
    acts = (await db.execute(select(Activity).where(Activity.contact_id == c.id).order_by(Activity.created_at.desc()).limit(100))).scalars().all()
    calls = {cl.conversation_id: cl for cl in (await db.execute(select(Call).where(Call.conversation_id.in_([cv.id for cv in convs] or [""])))).scalars()}
    timeline = [{"type": "conversation", "at": cv.last_message_at.isoformat(), "channel": cv.channel, "id": cv.id, "summary": cv.summary or cv.subject,
                 "outcome": cv.outcome, "sentiment": cv.sentiment, "status": cv.status, "messages": cv.message_count,
                 "call": {"id": calls[cv.id].id, "duration_s": calls[cv.id].duration_s} if cv.id in calls else None} for cv in convs]
    timeline += [{"type": "activity", "at": a.created_at.isoformat(), "id": a.id, "title": a.title, "kind": a.type, "data": a.data, "actor": a.actor} for a in acts]
    timeline += [{"type": "note", "at": n["created_at"], "id": n["id"], "title": n["body"], "actor": n["author"]} for n in notes]
    timeline.sort(key=lambda x: x["at"], reverse=True)
    return {"contact": to_dict(c), "identities": ids, "facts": facts, "deals": deals, "tasks": tasks, "notes": notes,
            "appointments": appts, "timeline": timeline,
            "channels": sorted({cv.channel for cv in convs})}


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Contact, contact_id, auth)
    for k in ("name", "lifecycle", "tags", "fields", "owner_id", "score", "consent", "company_id", "language"):
        if k in body:
            setattr(c, k, body[k])
    if body.get("phone"):
        await add_identity(db, c, "phone", body["phone"])
    if body.get("email"):
        await add_identity(db, c, "email", body["email"])
    db.add(Activity(workspace_id=auth.ws, contact_id=c.id, type="contact.updated", title="Contact updated", data={k: body[k] for k in body if k != "fields"},
                    actor=auth.email or "user"))
    await db.commit()
    from ..services.webhooks import emit

    await emit(auth.ws, "contact.updated", {"contact_id": c.id, "changes": list(body.keys())})
    return to_dict(c)


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """Right to erasure: removes the contact, identities, facts and conversations."""
    auth.require("admin")
    c = await get_scoped(db, Contact, contact_id, auth)
    for cv in (await db.execute(select(Conversation).where(Conversation.contact_id == c.id))).scalars():
        await db.delete(cv)
    await db.delete(c)
    await audit(db, auth, "contact.erase", contact_id)
    await db.commit()
    return {"ok": True}


@router.post("/contacts/{contact_id}/identities")
async def add_contact_identity(contact_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Contact, contact_id, auth)
    await add_identity(db, c, body["type"], body["value"], verified=bool(body.get("verified")))
    await db.commit()
    return {"ok": True}


@router.post("/contacts/{contact_id}/merge")
async def merge(contact_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    keep = await get_scoped(db, Contact, contact_id, auth)
    drop = await get_scoped(db, Contact, body["other_id"], auth)
    await merge_contacts(db, keep, drop)
    await db.commit()
    return to_dict(keep)


@router.post("/contacts/{contact_id}/facts")
async def add_fact(contact_id: str, body: dict, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    c = await get_scoped(db, Contact, contact_id, auth)
    f = ContactFact(workspace_id=auth.ws, contact_id=c.id, fact=body["fact"][:500], category=body.get("category", "other"), confidence=1.0, source_channel="manual")
    db.add(f)
    await db.commit()
    return to_dict(f)


@router.delete("/contacts/{contact_id}/facts/{fact_id}")
async def forget_fact(contact_id: str, fact_id: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    f = await get_scoped(db, ContactFact, fact_id, auth)
    await db.delete(f)
    await db.commit()
    return {"ok": True}


@router.post("/contacts/import")
async def import_contacts(file: UploadFile = File(...), auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    created = updated = 0
    for row in reader:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        phone, email = r.pop("phone", "") or r.pop("mobile", ""), r.pop("email", "")
        name = r.pop("name", "") or " ".join(x for x in [r.pop("first_name", ""), r.pop("last_name", "")] if x)
        tags = [t.strip() for t in r.pop("tags", "").split(",") if t.strip()]
        from ..brain.identity import find_contact

        existing = await find_contact(db, auth.ws, {"phone": phone, "email": email})
        c = existing or Contact(workspace_id=auth.ws, name=name or None, source_channel="import")
        if not existing:
            db.add(c)
            await db.flush()
            created += 1
        else:
            updated += 1
        c.name = c.name or name or None
        c.tags = sorted(set(c.tags or []) | set(tags))
        c.fields = {**(c.fields or {}), **{k: v for k, v in r.items() if v}}
        if phone:
            await add_identity(db, c, "phone", phone)
        if email:
            await add_identity(db, c, "email", email)
    await db.commit()
    return {"created": created, "updated": updated}


@router.get("/contacts-export")
async def export_contacts(auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Contact).where(Contact.workspace_id == auth.ws))).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "name", "phone", "email", "lifecycle", "score", "tags", "summary"])
    for c in rows:
        w.writerow([c.id, c.name or "", c.phone or "", c.email or "", c.lifecycle, c.score, ",".join(c.tags or []), c.summary])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=contacts.csv"})


# ── Generic CRUD resources ───────────────────────────────────────────────────
async def _deal_stage_changed(db, auth, deal: Deal, before: dict):
    if before.get("stage") != deal.stage:
        if deal.contact_id:
            db.add(Activity(workspace_id=auth.ws, contact_id=deal.contact_id, type="deal.stage_changed",
                            title=f"{deal.title}: {before.get('stage')} → {deal.stage}", actor=auth.email or "user"))
        from ..services.webhooks import emit

        await emit(auth.ws, "deal.stage_changed", {"deal_id": deal.id, "contact_id": deal.contact_id, "from": before.get("stage"), "to": deal.stage})


async def _task_log(db, auth, task: Task):
    if task.contact_id:
        db.add(Activity(workspace_id=auth.ws, contact_id=task.contact_id, type="task.created", title=f"Task: {task.title}", actor=auth.email or "user"))


async def _note_author(db, auth, note: Note):
    note.author = auth.name or auth.email or "user"


router.include_router(crud_router(Company, "/companies", writable={"name", "domain", "industry", "size", "fields"}, required={"name"}, search={"name", "domain"}))
router.include_router(crud_router(Pipeline, "/pipelines", writable={"name", "stages"}, required={"name"}, order_by="created_at"))
router.include_router(crud_router(Deal, "/deals", writable={"pipeline_id", "stage", "title", "value", "currency", "contact_id", "company_id", "owner_id",
                                                             "status", "position", "close_date", "fields"},
                                  required={"pipeline_id", "stage", "title"}, filters={"pipeline_id", "status", "contact_id"}, search={"title"},
                                  on_update=_deal_stage_changed))
router.include_router(crud_router(Task, "/tasks", writable={"title", "notes", "due_at", "status", "priority", "contact_id", "deal_id", "assignee_id"},
                                  required={"title"}, filters={"status", "contact_id", "assignee_id", "created_by"}, search={"title"}, on_create=_task_log, min_role="agent"))
router.include_router(crud_router(Note, "/notes", writable={"contact_id", "deal_id", "body"}, required={"body"}, filters={"contact_id", "deal_id"},
                                  on_create=_note_author, min_role="agent"))
router.include_router(crud_router(Calendar, "/calendars", writable={"name", "timezone", "slot_minutes", "buffer_minutes", "availability", "description"}, required={"name"}))
router.include_router(crud_router(Appointment, "/appointments", writable={"calendar_id", "contact_id", "title", "start_at", "end_at", "status", "notes", "source"},
                                  required={"calendar_id", "title", "start_at", "end_at"}, filters={"calendar_id", "status", "contact_id"}, order_by="start_at", min_role="agent"))
router.include_router(crud_router(DndEntry, "/dnd", writable={"value", "reason"}, required={"value"}, search={"value"}))


@router.get("/calendars/{calendar_id}/slots")
async def slots(calendar_id: str, date: str, auth: AuthContext = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    cal = await get_scoped(db, Calendar, calendar_id, auth)
    day = datetime.fromisoformat(date[:10])
    return {"slots": [s.isoformat() for s in await free_slots(db, cal, day)], "timezone": cal.timezone}


# ── Public booking page ──────────────────────────────────────────────────────
public = APIRouter(prefix="/public/booking")


@public.get("/{slug}")
async def booking_page(slug: str, date: str | None = None, db: AsyncSession = Depends(get_db)):
    cal = (await db.execute(select(Calendar).where(Calendar.slug == slug))).scalar_one_or_none()
    if not cal:
        raise HTTPException(404)
    from ..models import Workspace

    ws = await db.get(Workspace, cal.workspace_id)
    tz = ZoneInfo(cal.timezone)
    start = datetime.fromisoformat(date[:10]) if date else datetime.now(tz)
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        s = await free_slots(db, cal, d)
        days.append({"date": d.strftime("%Y-%m-%d"), "slots": [x.isoformat() for x in s]})
    return {"calendar": {"name": cal.name, "description": cal.description, "timezone": cal.timezone, "slot_minutes": cal.slot_minutes},
            "business": ws.name, "days": days}


@public.post("/{slug}")
async def book(slug: str, body: dict, db: AsyncSession = Depends(get_db)):
    cal = (await db.execute(select(Calendar).where(Calendar.slug == slug))).scalar_one_or_none()
    if not cal:
        raise HTTPException(404)
    st = datetime.fromisoformat(body["start"])
    if st.tzinfo is None:
        st = st.replace(tzinfo=ZoneInfo(cal.timezone))
    free = await free_slots(db, cal, st.astimezone(ZoneInfo(cal.timezone)))
    if not any(abs((s - st).total_seconds()) < 60 for s in free):
        raise HTTPException(409, "That slot was just taken. Please pick another.")
    from ..brain.identity import resolve_contact

    ids = {k: body[k] for k in ("phone", "email") if body.get(k)}
    contact = await resolve_contact(db, cal.workspace_id, ids, name=body.get("name"), channel="booking") if ids else None
    appt = Appointment(workspace_id=cal.workspace_id, calendar_id=cal.id, contact_id=contact.id if contact else None,
                       title=f"{cal.name}: {body.get('name') or 'Guest'}", start_at=st, end_at=st + timedelta(minutes=cal.slot_minutes),
                       source="booking_page", notes=body.get("notes", ""))
    db.add(appt)
    if contact:
        db.add(Activity(workspace_id=cal.workspace_id, contact_id=contact.id, type="appointment.booked", title=f"Booked {st:%d %b %H:%M} via booking page"))
    await db.commit()
    from ..services.webhooks import emit

    await emit(cal.workspace_id, "appointment.booked", {"appointment_id": appt.id, "contact_id": appt.contact_id, "start": st.isoformat()})
    return {"ok": True, "appointment_id": appt.id, "start": st.isoformat()}


_ = normalize_phone  # re-exported for import tools
