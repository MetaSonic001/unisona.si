# Unisona

**One AI agent, every channel.** Build a multilingual AI agent once, from your docs, website and spreadsheets, then deploy it
to browser voice, phone, WhatsApp, Telegram, a website widget, a hosted chat page, email and the API. One customer memory
spans every channel. A built-in CRM, campaigns, automations, human handoff, analytics, evaluations and a glass-box trace of
every answer come included.
It is 100% free to run locally: Groq free tier, Edge TTS, local embeddings, Chroma and Supabase. Paid providers are optional BYOK.

---

## 1. Requirements

| Tool | Version | Install |
| ---- | ------- | ------- |
| Node.js | 20+ | https://nodejs.org |
| pnpm | 10+ | `npm i -g pnpm` |
| uv | latest | https://docs.astral.sh/uv/ (it installs Python 3.12 for you) |

There is **no Docker**. The database is Supabase Postgres (free tier). Vectors, indexes and recordings live on local disk.

## 2. First-time setup

```bash
cp .env.example .env
```

Fill in the **required** keys (everything else is optional):

| Key | Where to get it |
| --- | --- |
| `DATABASE_URL` | Supabase → Connect → **Session pooler** (port 5432): `postgresql://postgres.<ref>:<password>@aws-…pooler.supabase.com:5432/postgres` |
| `UNISONA_MASTER_KEY` | `uv run python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"` |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | Clerk dashboard → API keys (enable **Organizations** for B2B workspaces) |
| `GROQ_API_KEY` | https://console.groq.com/keys (free). It powers the LLM, speech-to-text and the injection guard |
| `DEV_TOKEN` | any random string (dev-mode login, local only) |

Then:

```bash
pnpm setup
```

This checks tools, installs JS and Python dependencies, syncs web env vars, runs the database migrations and builds the widget.

## 3. Running

### Option A: one terminal (recommended)

```bash
pnpm dev
```

This starts the **API** (`[api]`, magenta) and the **web app** (`[web]`, cyan) with labelled logs. Ctrl+C stops both.

### Option B: separate terminals

Terminal 1, the API (FastAPI + background worker + scheduler + Telegram pollers + MCP server):

```bash
pnpm dev:api
```

Terminal 2, the web app:

```bash
pnpm dev:web
```

Optional terminal 3, the widget in watch mode (only if you are editing `apps/widget`):

```bash
pnpm dev:widget
```

Optional: run the job worker as its own process. Set `RUN_WORKER=false` in `.env` for the API, then:

```bash
cd services/api && uv run python -m unisona.worker
```

| URL | What |
| --- | ---- |
| http://localhost:3000 | Landing page → Sign in → dashboard |
| http://localhost:3000/app/dev | **Dev mode** (local only) |
| http://127.0.0.1:8000/docs | API reference (Swagger) |
| http://127.0.0.1:8000/health | Health + feature matrix |
| http://127.0.0.1:8000/mcp | MCP server (auth with a workspace API key) |
| http://localhost:3000/widget-demo?key=pk_… | Widget on a sample website |
| http://localhost:3000/chat/pk_… | Hosted chat page for an agent |

### What you'll see on startup

The API prints a banner, then a **feature table** that shows every capability as ON or OFF and which `.env` key enables
it. It then logs each service as it starts: database, worker, scheduler, Telegram pollers, MCP, Chroma, embeddings, reranker,
voices and VAD. A feature whose key is missing is **skipped, never crashed**. When something tries to use it, you get a log line:

```
WARNING [features] SKIPPED: deepgram provider is not available. Add DEEPGRAM_API_KEY to .env or to the workspace's Providers page to enable it.
```

## 4. Dev mode (local only)

With `DEV_MODE=true`, `DEV_AUTH_BYPASS=true` and `NEXT_PUBLIC_DEV_MODE=true`:

- The sign-in page shows **"Continue in dev mode"**, which skips Clerk. It is accepted only from `127.0.0.1`/`localhost`.
- `/app/dev` provides:
  - **Seed demo**: a BrightSmile Dental receptionist and a ShopKart order-status agent, with docs, an orders table and eval suites.
  - **Channel simulator**: message an agent as a WhatsApp, Telegram, phone, web or email customer without real accounts. Reuse the same phone number across channels to see cross-channel memory.
  - **Run scheduler now**: campaigns tick and the nightly improve loop.
  - **Run all evals** for an agent.
  - **Live feature matrix**, job queue and recent jobs.

Never enable dev mode on a server.

## 5. Tests and evaluations

```bash
pnpm test:api
```

Runs fast unit tests: language detection, injection guard, crypto vault, SQL guard, PII redaction, rendering, chunking, opt-out
detection, emotion, conversation flows and voice-eval scoring.

With the API running in dev mode, an end-to-end smoke test exercises every growth/calling feature against the real stack:
compliance, opt-out, escalation, forms, AI pages, reviews, payments, integrations, flows, squads and agency access control.

```bash
cd services/api && uv run python tests/smoke_suite.py
```

```bash
pnpm eval
```

Seeds the demo if needed, then runs, for every agent:

- **Knowledge QA**: Ragas-style LLM-judge metrics (correctness, faithfulness, answer relevancy, context precision/recall) plus deterministic checks (must-include, must-not-include, language, citations, latency).
- **Red team**: 12 attacks (prompt injection in EN/HI/Hinglish, system-prompt extraction, jailbreak/role-play, indirect injection, PII fishing, off-topic and tool abuse). Each is checked by an LLM judge and a canary-leak detector.
- **Simulated customers**: an LLM plays personas (happy path, frustrated, Hinglish) against your agent and grades the outcome.
- **Voice simulations** (Evaluations page → "Run voice tests"): real WebRTC calls from synthetic callers with Indian/US/UK accents,
  Hindi, street noise and barge-in. They score word-error-rate, latency (p95) and handling. The agent must be published.

Options: `pnpm eval -- --agent ag_xxx --kind redteam --out report.json`. It exits non-zero below 70%, so it's usable in CI.
The same suites run from the **Evaluations** page, which also has custom suites and history.

To smoke-test voice with the API running, use the agent's public key from its Channels tab:

```bash
cd services/api && uv run python tests/e2e_voice.py pk_xxx reply.wav
```

## 6. Keys and what they unlock

Every provider can be set **globally in `.env`** (the platform default) or **per workspace in Settings → AI providers**
(BYOK, encrypted, validated on save). Workspace keys always win.

| Feature | Key(s) | Free option |
| ------- | ------ | ----------- |
| LLM (chat, voice, judges) | `GROQ_API_KEY` (default), or BYOK OpenAI/Anthropic/Gemini/Mistral/DeepSeek/Together/Fireworks/OpenRouter/Cerebras/Ollama/any OpenAI-compatible | Groq free tier, Ollama |
| Speech-to-text | Groq (Whisper large-v3-turbo) by default; BYOK Deepgram Nova-3 / **Flux** (predictive end-of-turn), **Sarvam Saaras** (22 Indian languages), OpenAI | Groq, or local faster-whisper (`LOCAL_STT_ENABLED=true`) |
| Text-to-speech | none needed (Edge TTS, 25+ languages); BYOK Cartesia, ElevenLabs (incl. cloned voices), **Sarvam Bulbul**, Deepgram Aura, OpenAI | Edge TTS, Kokoro (offline) |
| Speech-to-speech | `GEMINI_API_KEY` (Gemini Live) or an OpenAI key (Realtime): set Agent → Voice → Engine | Gemini free tier |
| Instagram DMs + Messenger | same Meta app as WhatsApp; page access token per agent (Channels tab); webhook `/webhooks/meta` | ✔ |
| SMS (two-way) | the phone number's provider (Twilio/Plivo/Telnyx/Exotel); webhook `/telephony/<channel>/sms` | trial credits |
| Customer payments | the business's **Razorpay** (`key_id:key_secret`) or **Stripe** key in Settings → AI providers; webhook `/webhooks/payments/<provider>/<workspace>` | test mode |
| CRM / calendar sync | HubSpot private-app token, Salesforce connected app, Cal.com API key (Integrations page); Google Calendar needs `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` | ✔ |
| Zapier / Make / n8n | Incoming webhooks (Integrations page) push leads in; outgoing webhooks (Settings) push events out | ✔ |
| Prompt-injection guard | Groq (Llama Prompt Guard 2) | heuristics always on |
| Embeddings / RAG | none (local fastembed + Chroma) | ✔ |
| WhatsApp | `META_APP_ID`, `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`, `PUBLIC_WEBHOOK_URL` | Meta test number |
| Telegram | bot token per agent (Channels tab); uses polling, so no public URL is needed | ✔ |
| Phone calls | Twilio / Exotel / Plivo / Telnyx creds per workspace + `PUBLIC_WEBHOOK_URL` (e.g. `ngrok http 8000`) | trial credits |
| Email alerts / channel | `RESEND_API_KEY`, `ALERT_FROM_EMAIL` | Resend free tier |
| Slack alerts | `SLACK_ALERT_WEBHOOK_URL` | ✔ |
| Billing | `DODO_PAYMENTS_API_KEY`, `DODO_WEBHOOK_SECRET` (`DODO_ENVIRONMENT=test_mode`) | test mode |

## 7. Features (vs Bolna, Vapi, Retell, GoHighLevel)

- **Agents for every use case**: 18 templates (customer support, cold calling, lead qualification, technical support, receptionist, surveys, debt collection, appointment reminders, order status, onboarding, real estate, recruiting, healthcare triage, restaurant, insurance, education, feedback and FAQ).
- **Truly multilingual voice**: 25+ languages (Hindi, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Urdu, Odia, plus global languages). Language is detected per turn, including Hinglish, and the voice switches per sentence.
- **Bolna parity**: telephony (Twilio, Exotel, Plivo, Telnyx), batch calling campaigns with retries and calling windows, call recordings, transcripts and summaries, extraction to custom fields, webhooks, variables in prompts, tools and function calling, transfer to human, voicemail/idle handling, interruption control, knowledge bases, analytics, multiple LLM/STT/TTS providers and an API.
- **Calling (Vapi / Retell / Bland parity)**:
  - **Live transfer**, warm (the human hears an AI brief first) or cold, chosen by the agent or by a supervisor from Live.
  - **Voicemail detection**: carrier AMD plus spoken cues ("leave a message", "abhi vyast hai") → leave a message or hang up.
  - **Keypad (DTMF)** input, and IVR navigation for outbound calls.
  - **Concurrency limits** per plan, and **RNNoise** background-noise suppression.
- **Voice quality**:
  - Greeting about 0.4 s after connect.
  - Speculative knowledge lookup, streamed TTS and pre-synthesised fillers ("one moment…").
  - Smart Turn with tunable patience.
  - Optional Deepgram Flux eager end-of-turn.
  - Optional **Gemini Live / OpenAI Realtime** speech-to-speech.
- **Compliance (India/TRAI-friendly)**:
  - Opt-outs in EN/HI/Hinglish are honoured instantly on every channel.
  - Do-not-contact list with CSV import, consent records (promotional vs transactional) and calling hours.
  - All of it is enforced on every outbound path.
- **Flows & squads**:
  - A visual **conversation flow builder** whose steps, fields and transitions run on both chat and calls.
  - **AI specialist teams**: hand a conversation to another agent mid-chat or mid-call, keeping memory and history.
- **Omnichannel (respond.io / WATI / AiSensy)**:
  - Web, widget, voice, phone, **SMS**, WhatsApp (with **template** management and broadcasts), Telegram, **Instagram DMs**, **Messenger** and email.
  - One shared customer memory across all of them.
- **One brain, glass box**:
  - Cross-channel memory and per-answer traces (sources, confidence, guard verdict, cost).
  - Live **emotion** detection with auto-escalation.
  - Evals: QA, red team, simulations and **voice simulations**.
  - A self-improving loop.
- **CRM & growth (GoHighLevel parity)**:
  - Contacts, deals, tasks, calendars and booking pages.
  - Campaigns (calls, WhatsApp, SMS, email, Telegram, Instagram) and automations with 16 step types.
  - **Forms & surveys** with NPS and speed-to-lead AI follow-up.
  - **AI-generated landing pages** with embedded forms, booking and the agent.
  - **Reputation** (review requests with feedback gating).
  - **Payment links** (Razorpay/Stripe) sent by agents or automations.
- **Integrations**: HubSpot, Salesforce, Cal.com, Google Calendar (two-way), MCP (server + client), any REST API, and incoming/outgoing webhooks for Zapier, Make and n8n.
- **Agency (GoHighLevel agency mode)**:
  - Client sub-accounts with a switcher and an "acting as client" banner.
  - **Blueprints** to copy agents, automations and forms into a client.
  - **White-label** branding on every public page.
  - **Rebilling** with per-client fees, per-minute rates, AI-cost markup and a CSV statement.
- **Security**: envelope-encrypted BYOK vault, prompt-injection guard, canary tokens, spotlighting, PII redaction, rate limits, and verified agency access (a client header alone grants nothing).

## 8. Architecture

```
apps/web (Next.js 16) ──REST/SSE/WS──▶ services/api (FastAPI)
apps/widget (script) ──/public/*────▶   ├─ brain/      turn pipeline (guard → memory → RAG → LLM/tools → render)
phone / WhatsApp / Telegram ────────▶   ├─ voice/      Pipecat: VAD+SmartTurn → STT → LLM → TTS
                                        ├─ knowledge/  extract → chunk → embed → Chroma + BM25 + DuckDB
                                        ├─ services/   campaigns, automations, compliance, forms, reputation,
                                        │              payments, integrations, billing, MCP
Instagram / Messenger / SMS ────────▶   ├─ channels/   WhatsApp, Telegram, Meta (IG/Messenger), telephony + SMS
                                        ├─ worker/     Postgres job queue + scheduler
                                        └─ Supabase Postgres (schema app) + data/ (vectors, files, recordings)
```

See `context/architecture.md` for boundaries and invariants, and `docs/PRODUCT_PLAN.md` for the full plan.

## 9. Project layout

```
apps/web/            Next.js dashboard, landing, hosted chat, booking pages
apps/widget/         Embeddable chat + voice widget (Vite IIFE → served by the API at /widget/widget.js)
services/api/        FastAPI app (package: unisona), Alembic migrations, tests
scripts/             setup.mjs, dev.mjs, sync-env.mjs
context/             Living project context (read by AI assistants, see CLAUDE.md)
docs/                Product plan
```

## 10. Useful commands

| Command | What it does |
| ------- | ------------ |
| `pnpm db:migrate` | Apply DB migrations |
| `cd services/api && uv run alembic revision --autogenerate -m "msg"` | Create a migration after changing `models.py` |
| `pnpm build:widget` | Rebuild the widget bundle |
| `pnpm --filter web typecheck` | Typecheck the web app |
| `cd services/api && uv sync --all-extras` | Reinstall Python dependencies, including local voice models |

## 11. Troubleshooting

- **Every request feels slow (≈2 s)**: use `127.0.0.1` rather than `localhost` in `API_URL`/`NEXT_PUBLIC_API_URL` (Windows IPv6 fallback).
- **High latency from India**: each DB round-trip to a Tokyo/US Supabase project costs 100–250 ms. Create the Supabase project in **Mumbai (ap-south-1)**.
- **`DATABASE_URL` errors**: use the **session** pooler (port 5432), not the transaction pooler (6543) and not the IPv6-only direct host.
- **Turbopack can't resolve `next`**: keep the project's `.npmrc` (`virtual-store-dir=node_modules/.pnpm`), then run `pnpm install`.
- **Voice call has no audio**: allow microphone access. Behind strict NAT, WebRTC may need a TURN server. Phone calls need `PUBLIC_WEBHOOK_URL`.
- **First words of a call are cut**: wait for the greeting to finish. Barge-in during the first seconds is ignored by design.
- **Feature "SKIPPED" in logs**: add the named key to `.env` (platform-wide) or to Settings → AI providers (workspace).
- **Reset the local index**: stop the API, delete `data/chroma` (repo root) and re-ingest from the Knowledge page.

## 12. Security notes

- `.env` holds secrets and is gitignored. Provider keys saved in the UI are encrypted with a per-workspace data key wrapped by `UNISONA_MASTER_KEY`, so back that key up.
- App tables live in the `app` Postgres schema, which the Supabase Data API doesn't expose.
- Dev mode is loopback-only, but still turn it off anywhere other than your machine.
