"""Seed a new workspace with sensible defaults: knowledge base, sales pipeline, calendar."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Calendar, KnowledgeBase, Pipeline, Workspace

DEFAULT_STAGES = [
    {"id": "new", "name": "New lead", "color": "#94a3b8"},
    {"id": "qualified", "name": "Qualified", "color": "#6D5EF8"},
    {"id": "meeting", "name": "Meeting booked", "color": "#0ea5e9"},
    {"id": "proposal", "name": "Proposal", "color": "#f59e0b"},
    {"id": "won", "name": "Won", "color": "#10b981"},
    {"id": "lost", "name": "Lost", "color": "#ef4444"},
]
DEFAULT_AVAILABILITY = {d: [["10:00", "13:00"], ["14:00", "18:00"]] for d in ["mon", "tue", "wed", "thu", "fri"]} | {"sat": [["10:00", "14:00"]]}


async def seed_workspace(db: AsyncSession, ws: Workspace) -> None:
    db.add(KnowledgeBase(workspace_id=ws.id, name="General knowledge", description="Default knowledge base"))
    db.add(Pipeline(workspace_id=ws.id, name="Sales pipeline", stages=DEFAULT_STAGES))
    db.add(Calendar(workspace_id=ws.id, name="Appointments", timezone=ws.settings.get("timezone", "Asia/Kolkata"),
                    availability=DEFAULT_AVAILABILITY, description="Book a time with our team"))
    await db.flush()
