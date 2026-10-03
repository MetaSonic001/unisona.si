# Progress Tracker

Update this file after every meaningful implementation change.

## Current Phase

- v1 + competitive roadmap (P1–P3) complete. Now in verification with real third-party accounts.

## Current Goal

- Exercise the remaining flows with real third-party accounts (Clerk sign-in, WhatsApp, phone numbers, Dodo).

## Completed

- Monorepo (pnpm + Turborepo), `pnpm setup`, `pnpm dev` (labelled API + web logs) and `sync-env`.
- API: config/feature matrix with startup banner, Supabase schema `app` via Alembic (~40 tables), Clerk/API-key/dev auth.
- BYOK vault + 18 providers with key validation and platform-key fallback.
- Knowledge: extraction, crawler, chunking, multilingual embeddings, Chroma + BM25 hybrid, policies, reranker, DuckDB tables and golden answers.
- Brain: language detection (25 langs + Hinglish), memory/identity merge, prompts, tools, handoff, render per channel, analysis and fact extraction.
- Voice: Pipecat WebRTC + telephony (Twilio/Exotel/Plivo/Telnyx), Edge/Kokoro/Groq TTS, Groq/local Whisper, live controls and recordings.
- Channels: widget, hosted chat, WhatsApp Cloud, Telegram polling, email and outbound.
- CRM: contacts, companies, deals kanban, tasks, calendars, public booking. Campaigns, automations, webhooks, notifications, billing (Dodo) and MCP server/client.
- Evals: QA (judge metrics), red team (12 attacks), simulations. Available in the UI, the dev page and `pnpm eval`.
- Web: landing, auth, onboarding, home, agents + builder + playground, inbox, live, calls, knowledge, CRM pages, campaigns, automations, evals, analytics, integrations, settings, dev mode.
- Verified (2026-10-03):
  - All 20 dashboard routes load.
  - Hosted chat (Hinglish, cited) and widget chat work.
  - A voice WebRTC call answered a Saturday-hours question correctly.
  - `pnpm eval --kind qa` scored 8/8.
  - 13 unit tests pass.
  - Cross-channel memory works.

- Fixed: automation delete appeared to fail. The page re-selected the deleted item from a stale cache; the second click returned 404.
- `scripts/dev.mjs` no longer needs pnpm on PATH (it runs the local next/vite binaries), checks ports 8000/3000 first, and names the process that died.
- Voice latency pass (measured with the new ⏱ logs; per-turn numbers are measured from VAD end-of-speech):

  | Measure | Before | After |
  | --- | --- | --- |
  | Greeting | 9.8 s after offer | 0.36–0.5 s after offer, 14–25 ms after connect |
  | Turn latency | 3.4 s | 0.67–1.6 s |

  The changes:
  - Call prep (agent snapshot, keys, greeting audio) starts on the offer, in parallel with the WebRTC handshake. It is cached for 10 minutes, invalidated by agent, knowledge and key writes, and prewarmed at startup.
  - Contact, conversation and memory loading moved off the critical path. IDs are generated client-side, transcripts go through an ordered background writer, and the memory brief is injected before the first LLM turn.
  - Edge TTS decodes MP3 as it streams. Short phrases are cached, and the greeting is pre-synthesized.
  - Smart Turn fallback cut from 3 s to `voice.turn_patience_s` (default 1.2). `end_of_turn: vad` and `interruption_min_words` now actually apply.
  - Speculative knowledge lookup starts on the transcript, before turn commit. A single embedding is shared by retrieval and golden answers, keyword hits are read from Chroma instead of Postgres, and the agent row lookup on the hot path is gone.
  - The call latency metric now measures to the first audio (it previously measured to the end of the bot's speech).

- Competitive roadmap P1–P3 shipped (2026-10-03). Verified with `tests/smoke_suite.py` (32/32), 29 unit tests, typecheck,
  a voice call, and voice simulations (2/3 pass; see the known limitation below).
  - **Calling**:
    - Warm/cold live transfer (Twilio/Plivo/Telnyx) with an AI brief; browser calls fall back to a handoff.
    - Async AMD + spoken voicemail cues → leave a message or hang up.
    - DTMF collector, plus a `press_keys` IVR tool.
    - Per-plan concurrency limits; RNNoise on phone and WebRTC audio.
  - **Compliance** (`services/compliance.py`):
    - Opt-out detection in EN/HI/Hinglish on every channel.
    - DND list with CSV import; consent records (promotional vs transactional); calling hours.
    - Enforced in `send_to_contact`, `dial` and campaigns.
  - **Voice**:
    - Every agent tool works in calls, including custom HTTP and MCP tools.
    - Pre-synthesised fillers during tool calls; live emotion with escalation; squads switch the prompt, voice and tools mid-call.
    - Providers: Sarvam STT/TTS, Deepgram Nova-3/Flux (eager EOT), Cartesia, ElevenLabs, Deepgram Aura, OpenAI TTS.
    - Gemini Live / OpenAI Realtime engines (built; not tested live, no keys).
  - **Channels**: two-way SMS (4 providers), Instagram + Messenger (`channels/meta_messaging.py`, `/webhooks/meta`), WhatsApp template list/create/send, campaign types `sms`/`email`/`whatsapp_template`/`instagram`/`messenger`.
  - **Flows & squads**: `brain/flows.py` + a React Flow builder (Flow tab); `transfer_to_agent` with `squad_root` conversation routing (Team tab).
  - **Integrations** (`services/integrations.py`): HubSpot, Salesforce (client credentials), Cal.com, Google Calendar OAuth (busy times + events), incoming hooks `/hooks/{token}`, event-driven CRM sync job.
  - **Growth suite** (`api/suite.py`, `api/public_suite.py`):
    - Forms/surveys (`/f/[slug]`, NPS stats, speed-to-lead).
    - AI landing pages (`/p/[slug]`).
    - Reputation with feedback gating (`/r/[token]`).
    - Razorpay/Stripe payment links + webhooks; email unsubscribe (`/u/[token]`).
  - **Agency**:
    - Client sub-accounts via `x-workspace-id`, verified against `parent_id` and admin role.
    - Switcher + banner; blueprints; white-label branding; rebilling + CSV; plan `sub_accounts` limits.
  - **Evals**: voice simulations (`evals/voice_sim.py`) with accents, noise and barge-in; WER, latency and an LLM judge.
  - **Fixes found by testing**:
    - Handoff reason longer than 64 chars crashed the insert.
    - Noise-only transcripts ("।") were answered.
    - The greeting was saved twice.
    - The AI page builder failed when the model returned a list.
    - Public submits waited on side effects (now backgrounded).

## In Progress

- None.

## Next Up

- Verify with real accounts:
  - Clerk sign-in/invites.
  - Phone transfer, AMD and SMS (Twilio + `PUBLIC_WEBHOOK_URL`).
  - WhatsApp templates, Instagram/Messenger (Meta app).
  - Razorpay/Stripe webhooks; HubSpot/Salesforce/Cal.com/Google.
  - Gemini Live / OpenAI Realtime; Sarvam/Cartesia/ElevenLabs/Flux.
- Hindi in heavy noise: Groq Whisper auto-detect clips short noisy Hindi segments (the voice sim fails that scenario).
  Recommend Sarvam STT for Hindi-first agents, or add a per-agent STT language hint.
- Custom domains for white-label (stored; needs DNS/hosting setup), and a persistent Edge TTS socket (not supported by the library).
- Optional: lazy-load voice in the widget (120 KB gzip).

## Open Questions

- Production hosting target (API on a VM with a public IP for WebRTC/telephony; web on Vercel?).
- Move the Supabase project to the Mumbai region to cut ~130 ms per DB round-trip from India (form submit is 3.5 s today, mostly round-trips).

## Architecture Decisions

- SQLAlchemy (Python) owns the schema instead of Drizzle/Prisma, because every write goes through the FastAPI service.
  A second ORM would duplicate the schema.
- Tables live in the `app` schema so Supabase's auto-generated Data API can't expose them.
- Embedded Chroma + local fastembed: zero services to run and free. The Chroma server mode is switchable via `CHROMA_MODE`.
- The job queue runs on Postgres (`SKIP LOCKED`) inside the API process, so no Redis is needed.
- Groq is the default LLM: `openai/gpt-oss-120b` for chat and `qwen/qwen3.8-27b` (no reasoning) for voice and fast paths.
- Edge TTS is the default voice: free and natural across 25+ languages with per-sentence language switching. Kokoro is the offline fallback.
- `API_URL` uses `127.0.0.1` (not `localhost`) to avoid a ~2 s IPv6 fallback delay on Windows.
- Flows are our own lightweight engine (`brain/flows.py`), not pipecat-flows, so one flow runs identically on text and voice.
- Agency access uses an `x-workspace-id` header that is always re-verified against the caller's own workspace (`parent_id`) and admin role.
- Compliance checks live in `send_to_contact` / `dial`, so every outbound path (tools, automations, campaigns, hooks) inherits them.

## Session Notes

- Dev workspace `ws_409d04b854e74411950f` (external id `dev_org`). Demo agents: BrightSmile Dental and ShopKart.
- Speaking over the agent's greeting in the first seconds can clip the first words (Pipecat first-turn behaviour). This is normal.
- The old `C:\Users\shaun\projects\DialogFabric` folder is the pre-rename copy and can be deleted.
