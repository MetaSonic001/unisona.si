"""Database models. Every tenant-owned row carries `workspace_id`.

Grouped by domain: tenancy, BYOK, agents & knowledge, people & memory,
conversations, CRM, campaigns & automation, platform (jobs, usage, billing, audit).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, utcnow


def _id(prefix: str):
    return mapped_column(String(32), primary_key=True, default=lambda: new_id(prefix))


def _ws():
    return mapped_column(String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


def _json(default=dict):
    return mapped_column(JSONB, default=default, nullable=False)


def _created():
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


def _updated():
    return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ── Tenancy ──────────────────────────────────────────────────────────────────
class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = _id("ws")
    clerk_org_id: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), index=True)
    plan: Mapped[str] = mapped_column(String(32), default="free")
    parent_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("workspaces.id"), nullable=True)
    settings: Mapped[dict[str, Any]] = _json()
    branding: Mapped[dict[str, Any]] = _json()
    onboarding: Mapped[dict[str, Any]] = _json()
    trial_llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[str] = _id("mem")
    workspace_id: Mapped[str] = _ws()
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="admin")
    teams: Mapped[list[str]] = _json(list)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("workspace_id", "provider"),)
    id: Mapped[str] = _id("key")
    workspace_id: Mapped[str] = _ws()
    category: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(48))
    enc_payload: Mapped[str] = mapped_column(Text)
    masked: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="unverified")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = _json()
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


# ── Agents & knowledge ───────────────────────────────────────────────────────
class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = _id("ag")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | live | paused
    config: Mapped[dict[str, Any]] = _json()            # working draft
    published_config: Mapped[dict[str, Any]] = _json()  # what customers talk to
    published_version: Mapped[int] = mapped_column(Integer, default=0)
    public_key: Mapped[str] = mapped_column(String(40), unique=True, default=lambda: new_id("pk"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    id: Mapped[str] = _id("agv")
    workspace_id: Mapped[str] = _ws()
    agent_id: Mapped[str] = mapped_column(String(32), ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = _json()
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created()


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id: Mapped[str] = _id("kb")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class AgentKnowledge(Base):
    __tablename__ = "agent_knowledge"
    agent_id: Mapped[str] = mapped_column(String(32), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(32), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True)
    workspace_id: Mapped[str] = _ws()


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id: Mapped[str] = _id("src")
    workspace_id: Mapped[str] = _ws()
    kb_id: Mapped[str] = mapped_column(String(32), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16))  # url | website | file | text | table | qa
    title: Mapped[str] = mapped_column(String(300))
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|processing|ready|error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    when_to_use: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = _json()
    refresh_days: Mapped[int] = mapped_column(Integer, default=0)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = _id("ch")
    workspace_id: Mapped[str] = _ws()
    kb_id: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = _json()


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = _id("ds")
    workspace_id: Mapped[str] = _ws()
    kb_id: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("knowledge_sources.id", ondelete="CASCADE"))
    table_name: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    schema_card: Mapped[dict[str, Any]] = _json()
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class GoldenAnswer(Base):
    __tablename__ = "golden_answers"
    id: Mapped[str] = _id("ga")
    workspace_id: Mapped[str] = _ws()
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="approved")
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual|improve_loop|onboarding
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


# ── People, identity & memory ────────────────────────────────────────────────
class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[str] = _id("ct")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    company_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(24), default="lead")
    score: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str]] = _json(list)
    fields: Mapped[dict[str, Any]] = _json()
    consent: Mapped[dict[str, Any]] = _json()
    summary: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class ContactIdentity(Base):
    __tablename__ = "contact_identities"
    __table_args__ = (UniqueConstraint("workspace_id", "type", "value"),)
    id: Mapped[str] = _id("cid")
    workspace_id: Mapped[str] = _ws()
    contact_id: Mapped[str] = mapped_column(String(32), ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(24))  # phone|wa_id|telegram_id|email|web_session|external_id
    value: Mapped[str] = mapped_column(String(254))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class ContactFact(Base):
    __tablename__ = "contact_facts"
    id: Mapped[str] = _id("fct")
    workspace_id: Mapped[str] = _ws()
    contact_id: Mapped[str] = mapped_column(String(32), ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    fact: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(24), default="general")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    source_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    valid_from: Mapped[datetime] = _created()
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Conversations ────────────────────────────────────────────────────────────
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = _id("cv")
    workspace_id: Mapped[str] = _ws()
    agent_id: Mapped[str] = mapped_column(String(32), ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(16))  # web|widget|voice|phone|whatsapp|telegram|email|playground
    channel_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="ai")  # ai|handoff_pending|human|closed
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    assignee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subject: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    csat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    analysis: Mapped[dict[str, Any]] = _json()
    meta: Mapped[dict[str, Any]] = _json()
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = _created()
    last_message_at: Mapped[datetime] = _created()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_conv_ws_last", "workspace_id", "last_message_at"),)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = _id("msg")
    workspace_id: Mapped[str] = _ws()
    conversation_id: Mapped[str] = mapped_column(String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))  # user|assistant|human|system|tool
    content: Mapped[str] = mapped_column(Text)
    ir: Mapped[dict[str, Any]] = _json()
    author_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_msg_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 up, -1 down
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = _created()


class Trace(Base):
    __tablename__ = "traces"
    id: Mapped[str] = _id("tr")
    workspace_id: Mapped[str] = _ws()
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    data: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[str] = _id("call")
    workspace_id: Mapped[str] = _ws()
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(10), default="inbound")
    transport: Mapped[str] = mapped_column(String(16), default="webrtc")
    from_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    disposition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    recording_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict[str, Any]] = _json()
    started_at: Mapped[datetime] = _created()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Handoff(Base):
    __tablename__ = "handoffs"
    id: Mapped[str] = _id("ho")
    workspace_id: Mapped[str] = _ws()
    conversation_id: Mapped[str] = mapped_column(String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(64))
    urgency: Mapped[str] = mapped_column(String(12), default="normal")
    brief: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|accepted|resolved|expired
    team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_at: Mapped[datetime] = _created()
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = _id("ntf")
    workspace_id: Mapped[str] = _ws()
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class ReviewItem(Base):
    __tablename__ = "review_items"
    id: Mapped[str] = _id("rev")
    workspace_id: Mapped[str] = _ws()
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    bad_answer: Mapped[str] = mapped_column(Text, default="")
    proposed_answer: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(String(64), default="flagged")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|rejected
    created_at: Mapped[datetime] = _created()


# ── Channels & tools ─────────────────────────────────────────────────────────
class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = _id("chn")
    workspace_id: Mapped[str] = _ws()
    agent_id: Mapped[str] = mapped_column(String(32), ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16))  # web|widget|voice|whatsapp|telegram|phone|email
    name: Mapped[str] = mapped_column(String(120), default="")
    config: Mapped[dict[str, Any]] = _json()
    enc_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()


class Tool(Base):
    __tablename__ = "tools"
    id: Mapped[str] = _id("tool")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(16), default="http")  # http|mcp
    config: Mapped[dict[str, Any]] = _json()
    enc_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


# ── CRM ──────────────────────────────────────────────────────────────────────
class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = _id("co")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fields: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()


class Pipeline(Base):
    __tablename__ = "pipelines"
    id: Mapped[str] = _id("pl")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(120))
    stages: Mapped[list[dict[str, Any]]] = _json(list)
    created_at: Mapped[datetime] = _created()


class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[str] = _id("dl")
    workspace_id: Mapped[str] = _ws()
    pipeline_id: Mapped[str] = mapped_column(String(32), ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    value: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    company_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|won|lost
    position: Mapped[float] = mapped_column(Float, default=0)
    close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fields: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = _id("tsk")
    workspace_id: Mapped[str] = _ws()
    title: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|done
    priority: Mapped[str] = mapped_column(String(12), default="normal")
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    deal_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="user")  # user|ai|automation
    created_at: Mapped[datetime] = _created()


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = _id("note")
    workspace_id: Mapped[str] = _ws()
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    deal_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(120), default="user")
    created_at: Mapped[datetime] = _created()


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[str] = _id("act")
    workspace_id: Mapped[str] = _ws()
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict[str, Any]] = _json()
    actor: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = _created()


class Calendar(Base):
    __tablename__ = "calendars"
    id: Mapped[str] = _id("cal")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True, default=lambda: new_id("book"))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)
    availability: Mapped[dict[str, Any]] = _json()  # {"mon": [["09:00","17:00"]], ...}
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = _id("apt")
    workspace_id: Mapped[str] = _ws()
    calendar_id: Mapped[str] = mapped_column(String(32), ForeignKey("calendars.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="booked")  # booked|cancelled|completed|no_show
    source: Mapped[str] = mapped_column(String(24), default="manual")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


# ── Campaigns & automation ───────────────────────────────────────────────────
class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = _id("cmp")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(16))  # voice|whatsapp|telegram
    agent_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|scheduled|running|paused|completed
    settings: Mapped[dict[str, Any]] = _json()
    stats: Mapped[dict[str, Any]] = _json()
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class CampaignTarget(Base):
    __tablename__ = "campaign_targets"
    id: Mapped[str] = _id("tgt")
    workspace_id: Mapped[str] = _ws()
    campaign_id: Mapped[str] = mapped_column(String(32), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str] = mapped_column(String(128))
    variables: Mapped[dict[str, Any]] = _json()
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|in_progress|done|failed|skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any]] = _json()
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = _updated()


class Automation(Base):
    __tablename__ = "automations"
    id: Mapped[str] = _id("auto")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(200))
    trigger: Mapped[dict[str, Any]] = _json()
    steps: Mapped[list[dict[str, Any]]] = _json(list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    id: Mapped[str] = _id("arun")
    workspace_id: Mapped[str] = _ws()
    automation_id: Mapped[str] = mapped_column(String(32), ForeignKey("automations.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    log: Mapped[list[dict[str, Any]]] = _json(list)
    created_at: Mapped[datetime] = _created()


class DndEntry(Base):
    __tablename__ = "dnd_entries"
    __table_args__ = (UniqueConstraint("workspace_id", "value"),)
    id: Mapped[str] = _id("dnd")
    workspace_id: Mapped[str] = _ws()
    value: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(120), default="opt-out")
    created_at: Mapped[datetime] = _created()


# ── Platform ─────────────────────────────────────────────────────────────────
class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    id: Mapped[str] = _id("wh")
    workspace_id: Mapped[str] = _ws()
    url: Mapped[str] = mapped_column(Text)
    events: Mapped[list[str]] = _json(list)
    secret: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = _id("whd")
    workspace_id: Mapped[str] = _ws()
    endpoint_id: Mapped[str] = mapped_column(String(32), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = _id("ak")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    hash: Mapped[str] = mapped_column(String(128))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class EvalSuite(Base):
    __tablename__ = "eval_suites"
    id: Mapped[str] = _id("evs")
    workspace_id: Mapped[str] = _ws()
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), default="qa")  # qa|redteam|simulation
    cases: Mapped[list[dict[str, Any]]] = _json(list)
    created_at: Mapped[datetime] = _created()


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[str] = _id("evr")
    workspace_id: Mapped[str] = _ws()
    suite_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="qa")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    scores: Mapped[dict[str, Any]] = _json()
    results: Mapped[list[dict[str, Any]]] = _json(list)
    created_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = _id("job")
    workspace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(48), index=True)
    payload: Mapped[dict[str, Any]] = _json()
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_at: Mapped[datetime] = _created()
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[str] = _id("use")
    workspace_id: Mapped[str] = _ws()
    kind: Mapped[str] = mapped_column(String(24))  # llm|stt|tts|message|voice_minute|embedding
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (Index("ix_usage_ws_created", "workspace_id", "created_at"),)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[str] = _id("sub")
    workspace_id: Mapped[str] = _ws()
    plan: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = _id("aud")
    workspace_id: Mapped[str] = _ws()
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(120), default="")
    data: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()


# ── Growth suite: forms, sites, reputation, payments, integrations ───────────
class Form(Base):
    __tablename__ = "forms"
    id: Mapped[str] = _id("frm")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, default=lambda: new_id("f"))
    kind: Mapped[str] = mapped_column(String(16), default="form")  # form|survey
    fields: Mapped[list[dict[str, Any]]] = _json(list)  # [{id,label,type,required,options,map_to}]
    settings: Mapped[dict[str, Any]] = _json()  # {thank_you, redirect_url, tags, agent_id, follow_up}
    submissions: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


class FormSubmission(Base):
    __tablename__ = "form_submissions"
    id: Mapped[str] = _id("fsub")
    workspace_id: Mapped[str] = _ws()
    form_id: Mapped[str] = mapped_column(String(32), ForeignKey("forms.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    data: Mapped[dict[str, Any]] = _json()
    meta: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[str] = _id("pg")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, default=lambda: new_id("p"))
    blocks: Mapped[list[dict[str, Any]]] = _json(list)  # [{id,type,props}]
    theme: Mapped[dict[str, Any]] = _json()
    seo: Mapped[dict[str, Any]] = _json()
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class ReviewRequest(Base):
    __tablename__ = "review_requests"
    id: Mapped[str] = _id("rev")
    workspace_id: Mapped[str] = _ws()
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    token: Mapped[str] = mapped_column(String(40), unique=True, default=lambda: new_id("r"))
    channel: Mapped[str] = mapped_column(String(16), default="whatsapp")
    status: Mapped[str] = mapped_column(String(16), default="sent")  # sent|opened|reviewed|feedback|failed
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime] = _created()
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentLink(Base):
    __tablename__ = "payment_links"
    id: Mapped[str] = _id("pay")
    workspace_id: Mapped[str] = _ws()
    contact_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str] = mapped_column(String(16))  # razorpay|stripe
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    description: Mapped[str] = mapped_column(String(300), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    provider_ref: Mapped[str] = mapped_column(String(128), default="", index=True)
    status: Mapped[str] = mapped_column(String(16), default="created")  # created|sent|paid|expired|cancelled|failed
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("workspace_id", "type"),)
    id: Mapped[str] = _id("int")
    workspace_id: Mapped[str] = _ws()
    type: Mapped[str] = mapped_column(String(32))  # hubspot|salesforce|calcom|google_calendar
    config: Mapped[dict[str, Any]] = _json()
    enc_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="connected")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class IncomingHook(Base):
    __tablename__ = "incoming_hooks"
    id: Mapped[str] = _id("ih")
    workspace_id: Mapped[str] = _ws()
    name: Mapped[str] = mapped_column(String(120))
    token: Mapped[str] = mapped_column(String(48), unique=True, default=lambda: new_id("hook") + new_id("x")[2:])
    action: Mapped[str] = mapped_column(String(24), default="upsert_contact")  # upsert_contact|start_call|send_message|event_only
    config: Mapped[dict[str, Any]] = _json()
    calls: Mapped[int] = mapped_column(Integer, default=0)
    last_payload: Mapped[dict[str, Any]] = _json()
    created_at: Mapped[datetime] = _created()
