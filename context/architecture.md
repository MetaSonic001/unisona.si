# Architecture Context

## Stack

| Layer      | Technology                                                    | Role                                                       |
| ---------- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| Monorepo   | pnpm workspaces + Turborepo                                   | `apps/*` (JS) + `services/api` (Python)                    |
| Web        | Next.js 16 (App Router, Turbopack) + TypeScript               | Dashboard, landing, hosted chat, booking pages             |
| UI         | Tailwind v4 + shadcn/ui (radix) + motion + recharts           | Component system and charts                                |
| Auth       | Clerk (B2B organisations)                                     | Users, orgs = workspaces, roles, invites                   |
| API        | FastAPI (Python 3.12, uv)                                     | REST, SSE, WebSocket, WebRTC offers, webhooks, MCP server  |
| ORM / DB   | SQLAlchemy 2 async + asyncpg + Alembic → Supabase Postgres    | All relational data in schema `app`                        |
| Vectors    | Chroma (embedded PersistentClient) + bm25s                    | Hybrid retrieval index per workspace                       |
| Embeddings | fastembed `paraphrase-multilingual-MiniLM-L12-v2` (local)     | 50+ languages, 384-dim, CPU                                |
| Tables     | DuckDB (file per knowledge base)                              | Exact lookups over CSV/XLSX                                |
| LLM        | OpenAI-compatible client; Groq by default (BYOK any provider) | Chat, voice, judges, extraction                            |
| Voice      | Pipecat 1.12 (SmallWebRTC + telephony serializers)            | Realtime STT → LLM → TTS                                   |
| TTS / STT  | Edge TTS, Kokoro (local), Groq Whisper, faster-whisper        | Free multilingual voice                                    |
| Jobs       | Postgres queue (`SKIP LOCKED`) in the API process             | Ingestion, analysis, campaigns, automations, evals         |
| Widget     | Vite IIFE bundle (`apps/widget`)                              | Embeddable chat + voice served at `/widget/widget.js`      |
| Billing    | Dodo Payments                                                 | Plans in INR/USD, webhooks via standardwebhooks            |

## System Boundaries

- `apps/web` — all UI. It never talks to the database. Everything goes through the API with a Clerk JWT (or a dev token).
- `apps/widget` — standalone embeddable script. It only uses `/public/*` endpoints with the agent public key.
- `services/api/unisona/api` — HTTP routers (thin): validation, auth scoping and delegation.
- `services/api/unisona/brain` — the turn pipeline (`respond.py`): guard → memory → retrieval → LLM/tools → render → side effects.
- `services/api/unisona/knowledge` — extraction, chunking, embedding, Chroma/BM25/DuckDB stores, retrieval.
- `services/api/unisona/voice` — Pipecat sessions shared by WebRTC and telephony.
- `services/api/unisona/channels` — adapters that all call `brain.respond`:
  - WhatsApp (+ templates), Telegram, Instagram/Messenger (`meta_messaging.py`).
  - Telephony + two-way SMS + live transfer; outbound, with the compliance gate.
- `services/api/unisona/services` — business engines:
  - automations, campaigns, notifications, billing, onboarding, demo, MCP;
  - compliance, forms, reputation, payments, integrations.
- `services/api/unisona/brain/flows.py`, `brain/emotion.py` — conversation flows and the live emotion signal, shared by text and voice.
- `services/api/unisona/api/suite.py` (authenticated) and `api/public_suite.py` (public) — growth suite + agency routes.
- `services/api/unisona/api/calling.py` — AMD, whisper/Plivo XML, SMS webhooks, live transfer, capacity, compliance.
- `services/api/unisona/worker` — job queue + scheduler loop (started from the API lifespan, or `python -m unisona.worker`).
- `services/api/unisona/security` — auth, crypto vault, prompt-injection guard, redaction, rate limiting.
- `services/api/unisona/evals` — metrics, runner and CLI.

## Storage Model

- **Postgres (Supabase, schema `app`)**: workspaces, members, encrypted provider keys, agents and versions, knowledge
  metadata, chunks (text), conversations, messages, traces, calls, contacts/identities/facts, CRM, campaigns, automations,
  jobs, evals and usage. Tables live outside `public`, so the Supabase Data API can never expose them.
- **Local disk `data/` (repo root, `DATA_DIR`)**: Chroma vectors, BM25 indexes, DuckDB tables, uploaded files, call recordings and the TTS preview cache.
- **Browser**: only the session id for anonymous widget/hosted chats.

## Auth and Access Model

- Dashboard: Clerk session JWT verified against JWKS. The org claim maps to a workspace (auto-provisioned). Users without an org get a personal workspace.
- Roles: owner, admin, member and viewer (from Clerk org roles). Mutations need member+, and settings/billing need admin+.
- API keys (`usk_…`, SHA-256 hashed) authenticate REST and `/mcp` as a workspace.
- Public endpoints (`/public/*`) use the agent public key, an optional domain allow-list and per-IP rate limits.
- Dev mode: `dev:<DEV_TOKEN>` bearer, accepted only when `DEV_MODE` + `DEV_AUTH_BYPASS` are set and the request is from loopback.
- Every query is scoped by `workspace_id` (`get_scoped`/`crud_router`).
- Agency mode: `x-workspace-id` (or `?workspace=` on the socket) switches to a client sub-account only if its `parent_id`
  is the caller's verified workspace and the caller is an admin there.

## Invariants

1. Every row read or written through the API is scoped to the caller's workspace.
2. Provider secrets are stored only encrypted (per-workspace DEK wrapped by `UNISONA_MASTER_KEY`), are never returned, and are masked in the UI.
3. A missing optional key never crashes anything. The feature is skipped and logged with `feature_unavailable`.
4. All channels go through `brain.respond` (text) or `voice.session.run_voice_session` (audio). No channel-specific answering logic.
5. Untrusted content (retrieved docs, tool output, user text) is fenced as data and never concatenated into system instructions.
6. Request handlers don't block on long work. Ingestion, analysis, campaigns and evals run as jobs; public submits background their side effects.
7. Every outbound contact (call, message, campaign, automation, hook) passes the compliance check (DND, opt-out, consent, hours).
8. No Docker. Everything runs locally with `uv` + `pnpm`.
