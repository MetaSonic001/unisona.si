# Unisona

## Overview

Unisona is a multi-tenant, omnichannel AI agent platform. A business builds one agent once, from a template plus its own
documents, website and spreadsheets. That agent then answers on every channel: browser voice calls, phone (Twilio, Exotel,
Plivo, Telnyx), WhatsApp, Telegram, a website widget, a hosted chat page, email and the API. The agent speaks and understands
25+ Indian and global languages, including Hinglish. A customer gets one memory across all channels.
Unisona includes a CRM (contacts, deals, tasks, calendars and booking pages), campaigns, automations, human handoff with
live takeover, analytics, and a "glass-box" trace of every answer. It is built only on free/open tools. Keys are BYOK and
validated.
The audience is SMBs and agencies in India and globally. It competes with Bolna, Vapi, Retell, AgentPhone and GoHighLevel.

## Goals

1. A new workspace can go from sign-up to a live, grounded agent on web + voice in under 20 minutes (onboarding wizard).
2. Zero mandatory spend: Groq free tier for LLM and STT, Edge TTS/Kokoro for voice, local embeddings, Chroma and Supabase.
3. Every answer is explainable (sources, confidence, latency, guard verdict). Every agent is measurable through evals.
4. The same customer is recognised across channels. Their history, facts and open tickets follow them.

## Core User Flow

1. Sign in with Clerk (B2B organisations = workspaces). Locally you can use "Continue in dev mode".
2. Onboarding: describe the business → pick a template → add knowledge (files, URLs, text, CSV) → choose a voice/language.
3. Test in the Playground (chat + voice) with the diagnostics panel. Approve golden answers.
4. Publish → deploy channels (widget snippet, hosted page, phone number, WhatsApp, Telegram).
5. Conversations land in the Inbox. Handoffs notify humans, who can take over, whisper or end calls.
6. Contacts and deals update automatically. Automations and campaigns run. Analytics and evals track quality.
7. A nightly improve loop proposes knowledge gaps and fixes for review.

## Features

### Agents
- 18 templates covering every Bolna use case (support, cold calling, lead qualification, receptionist, surveys, collections, reminders, order status, onboarding, …).
- Versioned draft/published config: persona, prompts, voice, language, guardrails, tools, handoff rules and variables.
- Built-in tools: KB search, table SQL, booking, CRM update, handoff, end call, transfer, send message. Also custom HTTP tools and MCP servers.

### Knowledge (RAG)
- PDF/DOCX/PPTX/HTML/MD/TXT/URL crawl; CSV/XLSX loaded into DuckDB for exact lookups.
- Hybrid retrieval (multilingual embeddings in Chroma + BM25) with RRF fusion, source policies and an optional reranker. Golden answers take priority.

### Voice
- Pipecat pipeline: Silero VAD + Smart Turn, Groq Whisper (or local faster-whisper), any LLM, Edge TTS with per-sentence language switching (or Kokoro or Groq TTS).
- Browser WebRTC, phone media streams, recordings, live monitoring, whisper/take over/say/end.

### Channels
- Web widget (one script tag), hosted chat page, WhatsApp Cloud API, Telegram (polling), phone, email (Resend) and REST/MCP.

### CRM and growth
- Contacts with merged identities, companies, deals pipeline (kanban), tasks, calendars + public booking pages.
- Campaigns (outbound calls/messages with throttling and retry), automations (trigger → conditions → actions), webhooks.

### Calling, compliance & growth suite
- Live warm/cold transfer, voicemail detection, DTMF/IVR, concurrency limits, noise suppression.
- Opt-out/DND/consent/calling hours on every outbound path.
- Visual conversation flows and AI specialist teams (squads).
- SMS, Instagram, Messenger and WhatsApp templates.
- HubSpot/Salesforce/Cal.com/Google Calendar, incoming webhooks.
- Forms & surveys, AI landing pages, reputation (review gating) and payment links (Razorpay/Stripe).
- Agency mode: client sub-accounts, blueprints, white-label and rebilling.
- Voice simulations in evals.

### Platform
- Clerk orgs, roles and invites. BYOK vault (AES-GCM envelope encryption). Usage metering, Dodo billing (INR/USD), API keys.
- Security: Prompt Guard 2 + heuristics (EN/HI/Hinglish), canary tokens, spotlighting, PII redaction and rate limits.
- Evals: knowledge QA (Ragas-style judge metrics), a 12-attack red team and simulated customers. Available in the UI and through `pnpm eval`.
- Dev mode (local only): channel simulator, demo seeding, scheduler tick, feature matrix.

## Scope

### In Scope
- Everything above, running fully locally (no Docker) against Supabase Postgres.

### Out of Scope (for now)
- Hosting/deployment automation, a native mobile app, video agents.
- Paid voice infrastructure by default. ElevenLabs, Cartesia, Deepgram and others are only BYOK options.

## Success Criteria

1. `pnpm setup && pnpm dev` starts the API and web app, and logs which features are on or off based on `.env`.
2. A dev-mode user can seed the demo, chat with the agent and get grounded, cited answers in English/Hindi/Hinglish.
3. A browser voice call to an agent transcribes the user and answers with grounded speech.
4. Cross-channel memory: a WhatsApp chat, then a call from the same number, is recognised as the same contact.
5. `pnpm eval` runs QA, red-team and simulation suites with ≥70% pass rate on the demo agents.
