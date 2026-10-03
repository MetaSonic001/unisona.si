# DialogFabric — Product & Technical Plan (v1)

> Working name. See §17 for naming options.
> One brain, many mouths: a business builds **one agent** and deploys it on voice, web chat, the embeddable widget, WhatsApp and Telegram, with shared knowledge, personality, tools and cross-channel memory, plus a built-in AI-native CRM.

Status: plan only. Nothing is built yet. This document is the source of truth until code exists.

---

## 0. Decisions at a glance

| Area | Decision | Why |
|---|---|---|
| Monorepo | Turborepo + pnpm (JS) and a uv workspace (Python), one repository | One place for everything. Turbo runs the Python tasks through package.json scripts |
| Web app | Next.js 16 (App Router, RSC), React 19, Tailwind v4, shadcn/ui base | Matches both previous projects. Largest component ecosystem |
| Marketing visuals | Aceternity UI, Magic UI, 21st.dev blocks, Motion | Reserved for the marketing site, so the dashboard stays calm and fast |
| Widget | Separate Vite build (Preact plus Shadow DOM), ~40 KB gzipped, a single `<script>` | Must not ship React or Next to a customer's website |
| Backend API | Python 3.12, FastAPI, SQLAlchemy 2 async, Pydantic v2, Alembic | Requested. Reuses VoiceFlow knowledge |
| Realtime voice | **Pipecat** pipeline (Silero VAD, Smart Turn v3, STT, LLM, TTS) over **SmallWebRTC** (aiortc) and WebSocket transports | The VoiceFlow design (in-house STT→RAG→TTS with VAD and barge-in), but on a maintained framework. Not hand-rolled |
| Auth | Clerk (Organizations = workspaces, invitations, roles) | Requested. The backend verifies Clerk JWTs. Headers are never trusted |
| Database | PostgreSQL 16, installed natively (Windows installer, Homebrew or apt) **or** Neon/Supabase free tier | Docker is not allowed, so it's a native install or managed |
| Vectors | **Chroma** run as a separate local server (`chroma run`, pip installed) | Safe for API, worker and voice processes all writing at once. Embedded mode isn't |
| Sparse/BM25 | `bm25s` index per knowledge base, persisted to disk | Local Chroma does not support sparse indexing (cloud only) |
| Embeddings | `fastembed` (ONNX, no torch) by default, BYOK cloud embeddings optional | Free, CPU-only and fast |
| Reranker | FlashRank (ONNX, CPU) | Free and light |
| Job queue | **Procrastinate** (a Postgres-backed queue with periodic tasks) | No Redis needed, so no Docker. Windows has no native Redis |
| Pub/sub | Postgres LISTEN/NOTIFY plus an in-process bus. Redis/Valkey/Upstash optional via env | Live monitor and inbox realtime with zero extra infrastructure |
| File storage | Local filesystem behind an S3-style interface. Switch to R2/S3 by env | Free locally, cloud-ready later |
| Payments | Dodo Payments (subscriptions, usage metering, INR/UPI) | Requested. Native metering, merchant of record |
| BYOK | Every LLM, STT, TTS, embedding, telephony and messaging credential is tenant-supplied, validated on save and envelope-encrypted | Keeps provider costs off our books. Core to pricing |
| Realtime infra choice | Self-hosted Pipecat now. Later, swap the transport to LiveKit (self-hosted VM or Cloud) or Daily **without touching the pipeline**. Gemini Live / OpenAI Realtime as an optional "speech-to-speech" engine | See §6.6 for the cost reasoning on why Ultravox is not used now |

---

## 1. Positioning

### 1.1 The problem
- **Voice-only platforms** (Vapi, Retell, Bland, Bolna, Synthflow): no WhatsApp, web chat or chat fallback. They are developer-heavy, and their per-minute pricing piles up.
- **CRM suites** (GoHighLevel): they have multichannel AI, but it's a funnel and marketing tool with AI bolted on. Configuration is heavy, and pricing runs about $97–$497/month plus usage.
- **Chatbot builders** (WhatsHelp GPT, Intercom Fin, Tidio): text-only or text-first.
- Every one of them is a black box: "why did the bot say that?" has no answer.

### 1.2 Our answer
1. **One agent, every channel**, with channel toggles rather than rebuilds.
2. **Cross-channel memory** keyed on a *person*, not a channel.
3. **Glass-box RAG**: every answer shows its sources, scores and the prompt.
4. **Bring your own keys** for every provider. We charge for the platform, never mark up tokens.
5. **AI-native CRM** that fills itself from conversations.
6. **India-first and global**: Hindi and Hinglish, Indic voices, Exotel, UPI pricing, TRAI DND compliance, plus USD pricing.
7. **Local-first mode**: everything can run on one machine with free, open models, for privacy-sensitive buyers and on-prem enterprise deals.

### 1.3 Competitor snapshot (Oct 2026)

| | Pricing | Channels | Gaps we exploit |
|---|---|---|---|
| Vapi | $0.05–0.13/min platform fee, ~$0.13–0.32 all-in | Voice | Developer-only, no chat/WhatsApp, no CRM, opaque, weak support |
| Retell | $0.07–0.31/min bundled | Voice (+ some chat) | Little multichannel, no CRM, black box |
| Bolna (India) | ~4.5–6¢/min | Voice | Voice only, thin UI |
| Synthflow | ~$29/mo + usage | Voice | No-code, but voice only |
| GoHighLevel | $97–497/mo; AI Employee $97/sub-account; voice $0.07–0.25/min | Voice, SMS, chat, email | Bloated, marketing-first, AI is an add-on, US-centric |
| AgentPhone (YC) | API | Phone numbers, SMS, voice for agents, MCP | Infrastructure, not a product. A possible telephony **partner** |
| Ultravox / Gemini Live / OpenAI Realtime | $0.05 / ~$0.023 / ~$0.30 per min | Speech-to-speech APIs | Engines, not products. We can *offer them* as BYOK engines |

---

## 2. Personas and jobs-to-be-done

| Persona | Wants | Key surfaces |
|---|---|---|
| SMB owner (clinic, real estate, D2C) | "Answer my calls and WhatsApp 24/7 from my documents, today" | Onboarding wizard, templates, inbox, CRM |
| Support lead (mid-market) | Deflect tier-1 work, hand off cleanly, prove ROI | Handoff, analytics, improve loop |
| Sales/RevOps | Qualify leads, book meetings, outbound campaigns | CRM pipelines, campaigns, calendar |
| Agency | Build for 10–100 clients, white-label, rebill | Agency mode, Blueprints, sub-accounts |
| Developer at an enterprise | API, SDK, MCP, custom tools, SSO, data control | API keys, webhooks, MCP, local mode |
| Human support agent | Get alerted, take over, use AI copilot | Inbox, live monitor, notifications |

---

## 3. End-to-end user journey

### 3.1 Sign-up → live in 20 minutes
1. **Sign up** with Clerk (Google or email). A personal workspace is created automatically, and the Clerk Organization is synced through a webhook.
2. **Wizard step 1, "What does your business do?"**: enter a website URL.
   - Crawl4AI fetches up to 5–10 pages (homepage, about, pricing, FAQ, contact), found via sitemap first and then link heuristics.
   - The LLM drafts a **business profile**: name, industry, offerings, hours, contact, tone.
   - It suggests **2–3 templates** (for example Receptionist plus Lead Qualification) with name, persona, greeting and 10 starter Q&As pre-filled.
   - The scraped pages become the first knowledge source automatically.
   - *Bootstrap problem:* the user has no keys yet. Onboarding runs on **platform trial credits**, a rate-limited Gemini or Groq free-tier key we hold, capped at roughly 50 LLM calls per workspace. After that, BYOK is required. This keeps the 20-minute promise.
3. **Step 2, "Add your knowledge"**: drag in PDFs, DOCX, CSV or XLSX, paste URLs or text. Ingestion progress is live ("3 documents · 47 chunks indexed"). CSV and XLSX are detected as structured tables (§7.3).
4. **Step 3, "How should it sound?"**
   - Voice picker with instant previews, filtered by language, gender and accent.
   - A Professional ↔ Friendly slider and a Concise ↔ Detailed slider.
   - Language: auto, English, Hindi, Hinglish and so on.
   - **"Talk to it now"**: a browser WebRTC call to the agent inside the wizard. A phone test call comes later, once telephony exists.
5. **Step 4, "Where should it work?"** Toggles: Web chat page (hosted link) ☑, Website widget ☑, Browser voice call ☑, WhatsApp ☐, Telegram ☐, Phone ☐ (coming soon).
   - Result screen: the hosted link, a widget snippet with a copy button, and a QR code to talk.
   - WhatsApp runs Meta Embedded Signup. Telegram asks for a BotFather token, validated live.
6. **Post-onboarding checklist** (Canva/Notion style): add BYOK keys, invite a teammate, set handoff rules, connect calendar, run your first simulation.

### 3.2 Daily operation
- A customer reaches out on any channel. **Identity resolution** finds or creates the contact. **Memory** loads. The same agent brain runs, and the **channel renderer** formats the reply.
- If handoff triggers, the right human is alerted, takes over, and the AI becomes a copilot.
- Everything lands in the contact timeline in the CRM. Post-conversation analysis fills fields, scores the lead, and creates tasks.
- Admins review flagged answers each morning (the improve loop) and watch analytics.

---

## 4. Product surface (information architecture)

### 4.1 Marketing site (`/`)
- **Hero**: a live animated voice orb with a "Talk to our demo agent" button that starts a real WebRTC call. Animated "one brain → many channels" diagram (Aceternity beams).
- **Sections**:
  - Channel toggle demo
  - Glass-box demo: a question, the sources and scores, the answer
  - Use-case tabs (support, receptionist, sales, collections and so on)
  - CRM preview
  - BYOK cost calculator (we show your provider cost next to ours)
  - Comparison table vs Vapi, Retell and GHL
  - Templates gallery
  - Testimonials and logos
  - Pricing in INR or USD, auto-detected with a toggle
  - FAQ and footer
- **Pages**: `/pricing`, `/templates`, `/compare/{vapi,retell,gohighlevel,bolna}`, `/use-cases/*`, `/docs` (Fumadocs), `/changelog`, `/blog`, legal pages.

### 4.2 App shell
Linear/Attio-style layout:
- A collapsible left sidebar.
- A top bar with workspace switcher, **⌘K command palette**, search, notifications bell and help.
- Right-side detail panels instead of page jumps wherever possible.

Sidebar:
```
Home                 – today: live conversations, handoffs waiting, KPIs, checklist
Agents               – grid of agents; create from template / blank / URL
Inbox                – unified omnichannel inbox (all channels, assignments, filters)
Live                 – live monitor: ongoing calls + chats, listen/whisper/take over
CRM
  ├ Contacts         – table + saved views (smart lists), import, dedupe
  ├ Companies
  ├ Deals            – kanban pipelines
  ├ Tasks
  └ Calendar         – booking calendars + booking pages
Campaigns            – outbound voice / WhatsApp broadcast / email (phase 3)
Knowledge            – knowledge bases (shareable across agents), sources, gaps
Automations          – workflow builder (triggers → actions)
Analytics            – workspace + per-agent + per-channel dashboards
Integrations         – catalog + connected apps + MCP servers
Settings
  ├ Workspace, Branding (white-label)
  ├ Members & Roles, Teams (for routing)
  ├ Providers & Keys (BYOK vault)
  ├ Channels (WhatsApp numbers, Telegram bots, phone numbers, widget domains)
  ├ Billing & Usage
  ├ API keys, Webhooks, MCP server
  ├ Compliance (DND, calling hours, retention, PII redaction)
  └ Audit log
```

### 4.3 Agent workspace (`/agents/[id]`)
Tabs:
1. **Overview**: status, channels, KPIs, recent conversations.
2. **Playground**: three panes.
   - Left: chat, plus a voice call button and a channel simulator dropdown (see how it renders on WhatsApp vs voice).
   - Middle: the conversation.
   - Right: **Diagnostics**: retrieved chunks, dense/sparse/rerank scores, policy multipliers, final prompt sections, tool calls, per-stage latency and cost.
3. **Persona and voice**:
   - Prompt editor (Tiptap) with `{{variables}}`, plus tone, language and greeting.
   - Voice with preview, speed and pitch.
   - Interruption sensitivity, end-of-turn patience, filler words on or off, background ambience.
4. **Knowledge**: attach knowledge bases, priority, "when to use" hints, policy rules (restrict / require / allow).
5. **Tools**: built-ins, HTTP tools with a test console, MCP servers, integrations.
6. **Flows** (optional): a scripted flow canvas for strict scripts like surveys, collections or KYC (React Flow). A hybrid of free LLM conversation and node gates.
7. **Handoff and escalation**: triggers, routing team, business hours, fallback (callback, ticket).
8. **Memory**: what to remember, retention, a fact-extraction schema.
9. **Post-conversation analysis**: user-defined extraction schema (outcome, budget, appointment date and so on) that maps to CRM fields.
10. **Channels**: toggles plus per-channel overrides (WhatsApp templates, widget theme, voice-only greeting).
11. **Evaluations**: test suites, AI caller personas, regression runs before publish.
12. **Analytics**, then **Versions** (draft vs published, diff, roll back), then **Settings**.

Agents have a **Draft → Publish** model, like Figma or Canva versions. Editing never breaks the live agent.

---

## 5. Architecture

### 5.1 System diagram
```
                          ┌───────────── Clerk (auth, orgs, invites) ─────────────┐
                          │                                                        │
┌──────────────┐   ┌──────▼─────────────┐    ┌────────────────────────────────┐   │
│ Next.js web  │──▶│  FastAPI  "api"     │◀──▶│ PostgreSQL (RLS, Procrastinate │   │
│ marketing +  │   │  REST + WS (inbox,  │    │  queue, LISTEN/NOTIFY)         │   │
│ dashboard    │   │  live monitor)      │    └────────────────────────────────┘   │
└──────┬───────┘   └──────┬───────▲──────┘    ┌──────────────┐ ┌───────────────┐   │
       │                  │       │           │ Chroma server│ │ File store    │   │
┌──────▼───────┐          │       │           │ (dense)      │ │ (local / S3)  │   │
│ Widget (JS)  │──────────┤       │           │ + bm25s files│ └───────────────┘   │
│ on customer  │  chat WS │       │           └──────────────┘                     │
│ sites        │  voice   │       │                                                │
└──────────────┘  WebRTC  │       │                                                │
                   ┌──────▼───────┴──────┐   ┌───────────────────────────────┐     │
 Browser / phone ─▶│  "voice" gateway     │   │ "worker" (Procrastinate)      │     │
 (WebRTC, WS,      │  Pipecat pipelines   │   │ ingestion, crawl, embeddings, │     │
  Twilio/Exotel    │  VAD/turn/STT/LLM/TTS│   │ post-call analysis, nightly   │     │
  later)           └──────────┬───────────┘   │ improve, campaigns, webhooks  │     │
                              │               └───────────────────────────────┘     │
                   ┌──────────▼────────────────────────────────────────┐            │
                   │ "brain" (shared Python library, used by all three) │◀───────────┘
                   │ identity · memory · RAG · prompt assembly · tools  │
                   │ channel renderers · handoff · provider registry    │
                   └────────────────────────────────────────────────────┘
 Inbound webhooks: Meta WhatsApp, Telegram, Dodo, Clerk(svix), Twilio/Exotel → api
```

**Key principle:** the **brain** is one library. The voice gateway, the chat API, WhatsApp, Telegram and the widget all call `brain.respond(turn)`. That is what makes "one agent, many channels" true in code rather than in marketing.

### 5.2 Processes (all `uv run` / `pnpm dev`, no Docker)

| Process | Command (dev) | Port |
|---|---|---|
| web | `pnpm --filter web dev` | 3000 |
| widget | `pnpm --filter widget dev` (Vite) | 5173 |
| api | `uv run --package df-api uvicorn ...` | 8000 |
| voice | `uv run --package df-voice python -m df_voice` | 8100 |
| worker | `uv run --package df-worker procrastinate worker` | n/a |
| chroma | `uv run chroma run --path ./data/chroma --port 8200` | 8200 |
| postgres | native service or Neon | 5432 |
| ollama (optional) | native app | 11434 |

`pnpm dev` at the root starts everything through Turbo. A `scripts/doctor.py` checks Postgres, Chroma, model downloads, ffmpeg and port conflicts.

### 5.3 Repository layout
```
dialogfabric/
├─ apps/
│  ├─ web/                 Next.js (marketing + dashboard)
│  ├─ widget/              Vite + Preact embeddable widget & hosted chat page
│  └─ docs/                Fumadocs (optional, can live in web)
├─ services/               Python (uv workspace)
│  ├─ api/                 FastAPI app (REST, WS, webhooks)
│  ├─ voice/               Pipecat voice gateway
│  └─ worker/              Procrastinate tasks + schedules
├─ libs/
│  ├─ brain/               identity, memory, rag, prompts, tools, renderers, handoff
│  ├─ providers/           BYOK adapters + validators (LLM/STT/TTS/embeddings/telephony/messaging)
│  ├─ core/                db models, settings, crypto, tenancy, events
│  └─ crm/                 CRM domain services
├─ packages/               JS
│  ├─ ui/                  shared shadcn-based components, tokens
│  ├─ api-client/          generated from FastAPI OpenAPI (openapi-typescript + openapi-fetch)
│  ├─ sdk-js/              public JS SDK (widget + headless)
│  └─ config/              eslint, tsconfig, tailwind preset
├─ sdks/python/            public Python SDK + MCP server package
├─ docs/                   this plan, ADRs
├─ turbo.json, pnpm-workspace.yaml, pyproject.toml (uv workspace), .env.example
```

### 5.4 Multi-tenancy
- **Hierarchy**: Agency (optional) → **Workspace** (= Clerk Organization, billing boundary) → Agents, Knowledge Bases, Contacts, Channels…
- **Every** row has `workspace_id`. Postgres **Row-Level Security** is enforced with `SET LOCAL app.workspace_id` per request, so a missed `WHERE` clause cannot leak data. This fixes the header-trust and spoofable-cookie flaw seen in VoiceFlow.
- **Chroma**: one collection per workspace (`ws_<id>`), with `kb_id` and `source_id` metadata filters. **bm25s**: one index directory per knowledge base.
- **Files**: `/{workspace_id}/...` prefixes.
- **Rate limits and quotas** per workspace and per plan, enforced in the brain before any provider call.
- **Roles**: Owner, Admin, Builder (edits agents and knowledge), Agent (human, inbox only), Analyst (read-only), Billing. Optional per-agent access lists, like WhatsHelp's chatbot members.

### 5.5 Auth flow (Clerk)
- **Frontend**: `@clerk/nextjs` middleware protects `/app/*`. The organization switcher is the workspace switcher. Invitations, SSO and MFA come from Clerk.
- **Backend**: verify the Clerk session JWT using JWKS (cached) and read `sub`, `org_id` and `org_role`. `org_id` maps to `workspace_id`.
- **Webhooks**: Clerk webhooks (svix-signed) for `user.*`, `organization.*` and `organizationMembership.*` upsert local mirrors.
- **Public surfaces** (widget, hosted chat, WhatsApp, Telegram) use a channel public key plus allowed origins. **Identity verification**: the customer's backend signs `user_id` and `email` with an HMAC secret so we can trust "this is logged-in user X", the way Intercom does.
- **API keys** for developers are scoped and hashed. MCP server access uses the same keys.

---

## 6. Voice engine (the heart)

### 6.1 Why Pipecat instead of re-hand-rolling VoiceFlow
VoiceFlow built STT→RAG→TTS, RMS-energy VAD, sentence-chunked TTS and barge-in by hand. It worked, but energy VAD misfires on noise, and maintaining codecs, pacing and interruption logic ourselves is expensive. Pipecat is the same architecture, packaged and maintained:
- It's a frame-based pipeline: transport in → VAD → STT → user aggregator → LLM (our brain) → TTS → transport out.
- **Silero VAD** (ONNX, CPU) detects speech/non-speech. **Smart Turn v3** (BSD-2, ONNX, ~10–100 ms on CPU) decides whether the user is actually *finished*, using audio prosody. That's far better than fixed silence timeouts.
- **Interruptions and barge-in** are built in. When the user speaks while the bot talks, TTS stops, the output queue is cleared and the context is truncated to what was actually spoken.
- **Transports**: SmallWebRTC (aiortc, peer-to-peer, no server infrastructure) now. Telephony serializers (Twilio, Telnyx, Plivo, Exotel) later. Daily and LiveKit for scale. **We swap transports, not pipelines.**
- It has 40+ STT, TTS and LLM service integrations, which map neatly onto BYOK.

We wrap Pipecat in our own `VoiceSession` so the brain stays framework-agnostic. If Pipecat ever stops serving us, only the voice service changes.

### 6.2 Pipeline per call
```
WebRTC/WS in ─▶ (optional) noise suppression ─▶ Silero VAD ─▶ Smart Turn v3
   ─▶ STT (streaming if provider supports; else segment-on-VAD)
   ─▶ BrainProcessor:
        • identity + memory preloaded at call start (not per turn)
        • speculative retrieval on interim transcript (start RAG before user finishes)
        • LLM streaming with tools (filler phrase "let me check…" if tool >700 ms)
        • voice renderer: strip markdown/links, numbers/dates → words, ≤2 sentences per turn
   ─▶ TTS (streaming if provider supports; else sentence-chunked)
   ─▶ transport out  (+ recording tap → file store, + transcript tap → DB/live monitor)
```

### 6.3 Latency budget (target ≤ 1.0 s voice-to-voice on BYOK cloud models)

| Stage | Target | How |
|---|---|---|
| End-of-turn detection | 200–300 ms | Smart Turn instead of a 700 ms silence timeout |
| STT final | 100–300 ms | Deepgram or Groq Whisper (BYOK), or faster-whisper `small` int8 locally (~500 ms on CPU) |
| Retrieval | 50–150 ms | Speculative on interim text, cached embeddings, top-k small, FlashRank only on chat |
| LLM first token | 150–400 ms | Groq or Cerebras or Gemini Flash (BYOK). Ollama locally is slower |
| TTS first audio | 80–250 ms | Kokoro or Supertonic (ONNX, local) or Cartesia/Deepgram Aura (BYOK) |

We'll be honest in the UI: a "fully local, CPU-only" agent runs around 1.5–3 s per turn. That's acceptable for demos and on-prem, not for high-volume calls. The **latency meter** in the Playground shows real numbers per stage.

### 6.4 STT options

| Engine | Type | Cost to us | Notes |
|---|---|---|---|
| faster-whisper (CTranslate2) | Local CPU/GPU | Free (our CPU) | Default local. Multilingual including Hindi |
| Vosk | Local, streaming | Free | Tiny, fallback, a few languages |
| Groq Whisper (large-v3-turbo) | BYOK | User pays (free tier ~2k requests/day) | Very fast |
| Deepgram Nova/Flux | BYOK | User pays ($200 free credit) | True streaming, best for phone |
| AssemblyAI, Gladia, Speechmatics, OpenAI, Azure, Google | BYOK | User pays | Enterprise preferences |
| AI4Bharat IndicConformer | Local (GPU recommended) | Free | Optional Indic pack, phase 3 |

### 6.5 TTS and the voice library (150+ voices, free by default)

| Engine | Voices | Type | Notes |
|---|---|---|---|
| **Edge TTS** | 400+ neural voices, ~100 locales including Hindi, Tamil, Bengali and more | Free cloud, no key | ⚠️ Uses Microsoft's consumer endpoint, so it's **unofficial**. It can break or be throttled. Fine for free tier and demos. Don't promise an SLA on it |
| **Kokoro-82M** (kokoro-onnx) | ~54 | Local CPU | Apache-2.0, excellent quality and speed. English and a few other languages |
| **Supertonic 3** (ONNX) | Several voice styles, 31 languages including Hindi | Local CPU | ~99M params, extremely fast on CPU. Great default for multilingual |
| **Piper** | 100+ voices across many languages | Local CPU | Fastest, lower quality. Low-end fallback |
| **Chatterbox** (MIT) | Zero-shot cloning from 5–10 s | Local, GPU recommended | Voice cloning (phase 2). Requires a **recorded consent phrase** to prevent abuse |
| Indic Parler-TTS / IndicF5 | 22 Indian languages | Local GPU | Optional Indic premium pack (phase 3) |
| BYOK: Cartesia, Deepgram Aura, OpenAI, Azure, Google, Gemini TTS, ElevenLabs | Thousands | User pays | Never our cost. ElevenLabs is BYOK-only |

**Voice catalog** is one table (`voices`) with engine, voice_id, language, gender, accent, style tags and a cached preview URL. Previews are generated once and cached. The UI is a filterable gallery with play-on-hover, and a "favorites" list per workspace.

### 6.6 Build vs buy for realtime audio (cost view)

| Option | Our cost/min | Latency | Control | Verdict |
|---|---|---|---|---|
| **Self-hosted Pipecat + BYOK providers** | ~₹0 (CPU only; providers billed to the user) | 0.8–1.2 s | Full | **Default.** Best margins, works locally |
| Self-hosted Pipecat + local models only | CPU cost | 1.5–3 s | Full | "Private/local mode" tier |
| Gemini Live (BYOK, speech-to-speech) | ₹0 to us (~$0.023/min to the user) | ~0.5–0.8 s | Less (tools work, RAG via tools) | **Offer as the "Realtime engine" option.** Cheapest premium S2S |
| OpenAI Realtime (BYOK) | ₹0 to us (~$0.30/min to the user) | ~0.5 s | Less | Offer, but expensive for customers |
| Ultravox | $0.05/min (we'd pay, or BYOK) | ~0.6 s | Medium | **Not now.** It would eat the whole platform fee. Add later as a BYOK engine only if asked |
| LiveKit / Daily as transport | VM or usage | Better global routing, SIP | Full | **Scale path.** Swap the transport once we have customers |

**Recommendation:** build on Pipecat now. Design an `engine` enum per agent (`pipeline` | `realtime_gemini` | `realtime_openai` | later `ultravox`). Every engine calls the same brain tools (`search_knowledge`, `crm_lookup`, `handoff`…), so knowledge, memory and CRM stay shared whichever engine runs.

### 6.7 Telephony (phase 3, interfaces designed now)
- A `TelephonyProvider` interface: `buy_number`, `list_numbers`, `configure_inbound(agent)`, `dial(to, agent, vars)`, `transfer(call, to)`, `hangup`, `validate_credentials`.
- Adapters: **Twilio** (Media Streams WS), **Exotel** (India, Voicebot applet streaming), **Plivo**, **Telnyx**, **Vonage**. Optional SIP trunk via LiveKit SIP later.
- All are BYOK: the tenant connects their own account and numbers. Optionally, a managed numbers marketplace later, possibly via a partner like AgentPhone.
- Answering-machine detection, voicemail drop, DTMF menus and warm transfer (reused from VoiceFlow's AMD, IVR and live-transfer ideas).
- Compliance (from VoiceFlow `compliance_service`): DND registry plus TRAI NCPR checks for India, calling-hours windows per recipient timezone, retry caps, consent logging, recording disclosure.

---

## 7. Knowledge and RAG ("glass box")

### 7.1 Ingestion pipeline (worker)

| Source | Extractor |
|---|---|
| Website / URL / sitemap | **Crawl4AI** (Playwright, LLM-ready markdown, `fit_markdown` boilerplate removal). Scheduled re-crawl |
| PDF (digital) | **pymupdf4llm**: fast, keeps headings and tables as markdown |
| PDF (complex layout or scanned), DOCX, PPTX | **Docling** "high-fidelity mode", with **RapidOCR** (ONNX) for scans. Lighter than PaddleOCR |
| CSV / XLSX / Google Sheets | **Structured path** (§7.3), plus row summaries for semantic search |
| TXT / MD / HTML / pasted text | Direct |
| Audio / video (call recordings, YouTube) | faster-whisper transcription, then text |
| Q&A pairs | Stored as "golden answers" (exact-match fast path plus few-shot) |
| Integrations (phase 3) | Google Drive, Notion, Confluence, Zendesk/Freshdesk help centers, Shopify catalog |

Steps: extract → clean → **structure-aware chunking** (split on markdown headings first, then recursive 800–1,000 tokens with 15% overlap, tables kept whole) → optional **contextual chunk headers** (a cheap LLM adds a "this chunk is from X, about Y" line; BYOK, toggleable, measurably better recall) → embed (fastembed `bge-small-en-v1.5`, or `multilingual-e5-small` for Indic and multilingual, or BYOK Gemini/OpenAI/Voyage/Cohere/Jina) → upsert into Chroma plus the bm25s index → store chunk rows in Postgres for diagnostics and citations.

Progress events stream to the UI. Each source gets status, chunk count, last-refreshed time, errors and a re-index button.

### 7.2 Retrieval (adaptive, "agentic where it pays")
A **router** (rules first, then a cheap LLM classification only when ambiguous) picks a path per turn:

| Path | When | What |
|---|---|---|
| **No-retrieval** | Small talk, confirmations | Skip RAG. Saves latency |
| **Golden answer** | Near-exact match to an approved Q&A | Return the curated answer (fast, zero hallucination) |
| **Fast hybrid** (default; always on voice) | Normal questions | Dense (Chroma) + sparse (bm25s) → **RRF** → policy scoring → top 4–6 |
| **Deep hybrid** (chat) | Complex or multi-part | Multi-query rewrite or decomposition → hybrid per sub-query → **FlashRank rerank** → top 6–8 |
| **Structured (SQL)** | Question is about a table (order status, price list, inventory) | Text-to-SQL over a sandboxed **DuckDB** view of that dataset, read-only with row limits |
| **Tool** | Needs live data | Call an integration or MCP tool instead of the knowledge base |

**Policy scoring** (VoiceFlow's best idea, kept): tenant, brand and agent rules multiply scores: restrict ×0.05, require ×2.0, allow ×1.0. Matched on topic, source or tag. Plus a **"when to use"** hint per source and **knowledge boundaries** ("never answer medical dosage questions").

**Confidence**: if the top score is below threshold, the agent says it doesn't know and offers handoff. It doesn't guess. Low-confidence turns are auto-flagged for the improve loop.

### 7.3 Structured data done right
A CSV of 10,000 orders should not become 10,000 chunks of noise.
- CSV and XLSX are loaded into DuckDB (a per-knowledge-base file), with a schema card (columns, types, sample rows) stored for the LLM.
- The agent gets a `query_table(kb, question)` tool. The LLM writes SQL, which is validated (SELECT only, allow-listed tables, LIMIT enforced) and executed. The result is summarized.
- Row-level semantic search is still built for fuzzy lookups ("the blue sneakers").
- This is a real differentiator for Order Status, Debt Collection (balances), Real Estate (listings) and Appointment Reminder (schedules).

### 7.4 Prompt assembly (layered, from VoiceFlow, extended)
Sections, each visible in Diagnostics:
1. Platform safety rules
2. Workspace/brand: name, industry, voice and tone, allowed and restricted topics
3. Agent persona and goals, plus template prompt with variables
4. **Channel style block** (§8.2)
5. Contact context: who this is, cross-channel memory facts, last interaction summary, CRM fields such as deal stage and open tickets
6. Retrieved knowledge with source IDs (for citations)
7. Golden examples (few-shot from the improve loop, top-k by similarity, not just "most recent 10")
8. Tools and when to use them
9. Escalation rules
10. Active policies summary

### 7.5 Citations and diagnostics
- **Chat**: superscript citations `[1]` link to a source drawer (document title, page or URL, highlighted snippet).
- **Voice**: "Based on your *return policy* document…" (natural reference, with no URL read aloud). The source is still logged.
- **Every turn writes a trace**: router decision, queries, candidates with dense, sparse, RRF, rerank and policy scores, final context, prompt sections (hashed and stored), tool calls, tokens, latency per stage, provider and model, estimated provider cost.
- **"Why did it say that?"** is available on any message in the inbox, the playground and analytics, not just in debug mode.

### 7.6 Evaluation
- Per-agent **test suites**: question → expected facts, or "must hand off" / "must not mention X".
- **AI caller simulations** (from VoiceFlow `simulation_service`): personas like an angry customer, a confused elderly caller or a Hinglish speaker run N conversations against the draft. An LLM judge scores them, and the **publish gate** blocks regressions.
- Knowledge **coverage report**: top unanswered questions and low-confidence topics, each with a one-click "Add answer".

---

## 8. Omnichannel runtime

### 8.1 Channels

| Channel | Transport | Phase |
|---|---|---|
| Web chat (hosted page `chat.<domain>/a/<slug>`) | WebSocket/SSE | 1 |
| Embeddable widget (chat + voice button) | Script tag, WS + WebRTC | 1 |
| Browser voice call (widget, hosted page, playground) | SmallWebRTC | 1 |
| WhatsApp (Cloud API, BYOK WABA, Embedded Signup) | Webhooks + Graph API | 2 |
| Telegram (BYOK bot token) | Bot API webhooks | 2 |
| Email (inbound parse + SMTP/Resend BYOK) | Webhooks | 3 |
| Phone (Twilio, Exotel, Plivo, Telnyx) | Media streams | 3 |
| SMS (via telephony provider) | Webhooks | 3 |
| Instagram / Messenger (Meta) | Webhooks | 4 |
| Slack / Teams (internal helpdesk agents) | Apps | 4 |

The **channel toggle** is a single switch. If credentials are missing, a side sheet asks for exactly what's needed (for example the Telegram token), validates it and goes live, all within seconds.

### 8.2 Channel-aware rendering
The brain produces a **Response IR**: `text`, `citations[]`, `actions[]` (buttons or quick replies), `cards[]`, `links[]`, `handoff?`, `end_call?`. Renderers then shape it:
- **Voice**: plain text. Markdown stripped, numbers and dates spoken naturally, links replaced by "I can send that to your WhatsApp" (a cross-channel action), at most about 2 sentences per turn, an SSML-lite pause hint.
- **Web/widget**: markdown, citation chips, buttons, carousels, forms, file links.
- **WhatsApp**: WhatsApp markdown, **reply buttons (≤3) or list messages (≤10)**, CTA URL. Outside the 24-hour window, it must use approved **templates**. Template manager included, as in WhatsHelp GPT.
- **Telegram**: HTML subset with inline keyboards.

The **style block** is injected into the prompt per channel, and the renderer enforces it afterwards (belt and braces).

### 8.3 Cross-channel actions (a differentiator)
Tools the agent can use regardless of the current channel:
- `send_whatsapp(contact, template|text)` and `send_email` / `send_sms`: "I've sent the payment link to your WhatsApp."
- `schedule_callback(contact, time)`: creates a CRM task, and later an outbound call.
- `continue_on(channel)`: generates a magic link that resumes the same conversation on the web.

### 8.4 Message ingestion patterns (lessons from WhatsHelp GPT)
- Webhook signature verification (Meta `X-Hub-Signature-256`, Telegram secret token).
- **Idempotency** on provider message ID.
- **Debounce/buffer**: rapid consecutive messages from the same user within about 2.5 s merge into one turn (WhatsHelp had this disabled, so we make it configurable and turn it on).
- Respond `200` immediately and process in the worker. A typing or read indicator fires right away.

---

## 9. Identity and cross-channel memory

### 9.1 Identity resolution
- `contacts` is the CRM person. `contact_identities` holds rows with (`type` ∈ phone_e164 | wa_id | telegram_id | email | web_session | external_user_id, `value`, `verified`).
- On each inbound event, normalize the value (phone to E.164 via `phonenumbers`), look up the identity, and attach it or create a contact.
- **Linking**:
  - Automatic when the identifiers match. WhatsApp `wa_id` is a phone number, so it links to calls from that number.
  - Through identity verification on the widget (HMAC user ID or email).
  - **Agent-assisted**: the AI asks "can I have your phone number to pull up your history?", then an OTP via WhatsApp or SMS verifies it before merging. This prevents spoofed merges.
- Merges are logged and reversible (unmerge), and appear in the timeline.

### 9.2 Memory layers
1. **Working memory**: current conversation turns (in DB, windowed).
2. **Episodic summaries**: per conversation, at the end or every N turns: summary, outcome, sentiment (worker).
3. **Semantic facts**: extracted facts with `fact`, `category` (preference, issue, intent, personal), `confidence`, `source_message_id`, `valid_from` / `valid_to` (temporal, the Graphiti idea without the graph database).
   - Embedded in the workspace's Chroma collection (`type=memory`, `contact_id`).
   - Contradictions close the old fact (`valid_to`) instead of overwriting it.
   - Implementation: our own small mem0-style extractor using the tenant's LLM. A conscious choice to avoid another heavy dependency. mem0 OSS is the fallback option if ours underperforms.
4. **CRM state**: deal stage, open tasks, tickets and appointments are injected as structured context.

At conversation start (voice: on call connect), we preload a **contact brief**: name, last 3 interaction summaries across channels, top facts and open items. Example: *"Rahul chatted on the website at 2 PM about refund #123. He's now calling. Mention the refund status."*

Privacy controls: per-agent "remember across channels" toggle, retention days per plan, "forget this contact" (DPDP Act and GDPR erasure), PII redaction in stored transcripts (Presidio-style regex plus an NER option).

---

## 10. Human handoff

### 10.1 Triggers (configurable per agent)
- The user asks for a human (explicit intent, any language: "insaan se baat karao").
- **Frustration**: sentiment drops sharply, repeated rephrasing, caps or profanity.
- **Repeated low confidence**: 2 consecutive turns under the retrieval threshold.
- **Policy topics**: refunds above X, legal, medical, cancellations of an enterprise plan…
- **Persistence**: the same question asked 3 times.
- The LLM calls the `handoff_to_human(reason, urgency, summary)` tool.
- Business rules: VIP contact, a deal value above X.

### 10.2 Flow
1. The conversation enters `handoff_pending`, with `reason`, `urgency` and an **AI-written brief** (who, what they want, what was tried, suggested next step).
2. **Routing**: team (Support/Sales/Billing), then a strategy (round-robin, least-busy, skills, sticky owner from the CRM), respecting online status and business hours.
3. **Alerts**:
   - In-app realtime toast with sound, a badge and a desktop Web Push (VAPID).
   - Email (Resend/SMTP).
   - Slack and MS Teams webhooks.
   - Optional WhatsApp to an on-call number.
   - Escalation if not accepted within the SLA (for example 2 minutes, then the team lead).
4. **The customer experience** while waiting:
   - Chat: "Connecting you to Priya from support. Usually under 2 minutes." The AI keeps helping in the meantime if allowed.
   - Voice (WebRTC): hold message with gentle ambience. **The human joins the same call from the browser** (Live monitor → "Take over"), and the AI goes silent.
   - Phone later: warm transfer with the brief read to the human ("whisper"), or cold transfer.
5. **No human available** (out of hours, SLA missed): the agent offers a callback slot (books into the calendar) or creates a ticket, and tells the customer precisely what will happen.
6. **Human mode**: the AI becomes a **copilot**. It suggests replies, surfaces knowledge snippets and drafts summaries. The human can hand back to the AI with one click.
7. Every handoff is logged and measured: handoff rate, time to accept, resolution, and CSAT after.

### 10.3 Live monitor
- A grid of live calls and chats. Each shows channel, agent, contact, duration, live transcript, sentiment and a "needs attention" flag.
- Actions: **Listen** (WebRTC subscribe), **Whisper** (coach the AI via a hidden instruction), **Barge/Take over**, **End**.
- Realtime comes over FastAPI WebSocket, fed by Postgres NOTIFY from the voice and worker processes.

---

## 11. Tools, integrations and MCP

### 11.1 Built-in tools
`search_knowledge`, `query_table`, `crm_lookup`, `crm_update` (fields, tags, deal stage), `create_task`, `book_appointment` / `reschedule` / `cancel` (our calendar, Google Calendar or Cal.com), `send_whatsapp`, `send_email`, `send_sms`, `create_ticket` (Freshdesk/Zendesk or internal), `payment_link` (Dodo or Razorpay, BYOK), `handoff_to_human`, `transfer_call`, `end_call`, `collect_dtmf` (phone), `schedule_callback`, `get_datetime`.

### 11.2 Custom tools
- **HTTP tool builder**: method, URL with `{{vars}}`, auth (API key, Bearer, Basic, OAuth2 client credentials), headers, JSON schema for arguments, response mapping, timeout, a **test console**, and a voice-specific "filler phrase" setting.
- **MCP client**: connect any remote MCP server (Streamable HTTP, OAuth). Its tools appear in the tool picker with per-tool allow-lists. This instantly gives access to thousands of integrations.
- **Python/JS code tool** (phase 4, sandboxed). Skipped until a sandbox exists.

### 11.3 MCP server (we expose)
The `dialogfabric-mcp` package, plus a hosted endpoint at `/mcp`. Tools include `list_agents`, `ask_agent`, `search_knowledge`, `add_knowledge`, `place_call` (phase 3), `crm_search_contacts`, `crm_create_task`, `get_conversation`, `analytics_summary`. This lets Claude, Cursor and other agents operate the platform, which matters to developer buyers. VoiceFlow already sketched this idea.

### 11.4 Integrations catalog (by phase)
- **Phase 2**: Google Calendar, Cal.com, Calendly, Google Sheets, Slack, Resend/SMTP, Zapier/Make/n8n (via our outbound webhooks and an inbound "trigger agent" endpoint).
- **Phase 3**: HubSpot, Salesforce, **Zoho CRM** (big in India), Freshdesk, Zendesk, Shopify, WooCommerce, Razorpay, MS Teams, Notion, Google Drive.
- **Outbound webhooks** (HMAC-signed, retries, delivery log): `conversation.started|ended`, `call.ended`, `handoff.requested`, `contact.created|updated`, `deal.stage_changed`, `appointment.booked`, `analysis.completed`.

---

## 12. CRM (GoHighLevel-class, AI-native)

GHL's strength is breadth. Its weakness is that AI is bolted on and setup is heavy. Ours is **conversation-first**: the CRM fills itself.

### 12.1 Core objects
- **Contacts** with unified identities, owner, tags, custom fields (typed), lifecycle stage, lead score, consent flags (WhatsApp opt-in, DND), and a timeline (every message, call with recording and transcript, email, note, task, deal change and appointment across all channels).
- **Companies**, **Deals** (multiple pipelines, stages, value, probability, kanban with dnd-kit), **Tasks** (due, assignee, reminders), **Notes** (with @mentions), **Appointments**.
- **Smart lists / saved views**: filter builder, shared or personal, column picker. TanStack Table with virtualization.
- **Import/export** CSV with column mapping, dedupe on phone or email, merge.

### 12.2 AI-native extras (where we beat GHL)
- **Auto-CRM**: post-conversation analysis writes fields (budget, timeline, product interest), moves deal stages, creates follow-up tasks and adds tags. Every AI change is labeled "AI" and is reversible.
- **AI lead scoring and next-best-action** on every contact.
- **Ask your CRM** (⌘K): "show hot leads from WhatsApp this week who haven't booked."
- **Meeting/call summaries** pinned to the timeline.

### 12.3 Calendar and booking
Availability rules, buffers, round-robin across team members, a **public booking page**, Google Calendar two-way sync, reminders (WhatsApp, email, voice via the Appointment Reminder agent), and no-show tracking.

### 12.4 Automations (workflow builder)
A React Flow canvas.
- **Triggers**: contact created, tag added, form submitted, conversation ended with outcome X, deal stage changed, appointment booked or no-show, inbound message keyword, schedule (cron), webhook.
- **Actions**: send WhatsApp template / email / SMS, **start outbound AI call**, assign owner, update field, add tag, create task, move deal, wait/delay, if/else, HTTP request, notify team, enroll in campaign.
- Runs in the worker with a durable, step-by-step execution log per contact.

### 12.5 Campaigns
- **Outbound voice**: upload a list or a smart list, pick an agent, set calling window, concurrency, retries, AMD and voicemail drop. Live progress with outcomes. Compliance gate on every dial.
- **WhatsApp broadcast** with approved templates, opt-in only, and a quality-rating watch.
- **Email** sequences (BYOK SMTP or Resend).

### 12.6 Agency mode (vs GHL's $297–497 plans)
- Agency workspace → **client sub-workspaces**, with a switcher.
- **Blueprints** (= GHL Snapshots): package agents, knowledge structure, pipelines, automations, templates and custom fields, then deploy them to a client in one click.
- **White-label**: custom domain for the app and widget, logo, colors, email sender, hidden "powered by".
- **Rebilling**: the agency sets its own prices. Dodo handles platform billing to the agency.

### 12.7 Deliberately out of scope (for now)
GHL's funnel and website builder, social planner, courses and memberships. These are huge, not core to "AI agents", and many tools already exist for them. We add **forms** (embeddable lead forms) and **review requests** (reputation lite) in phase 3. Everything else integrates through webhooks.

---

## 13. Analytics and quality

- **Workspace dashboard**: conversations by channel, **containment rate** (resolved without a human), handoff rate, CSAT, average handle time, bookings and leads created, provider spend (BYOK estimate), and active plan usage.
- **Per agent**: the same, plus latency p50/p95 per stage (voice), top intents (embedding clusters with LLM labels), knowledge-gap list, sentiment trend, tool success rates, and version comparison (A/B between versions, as VoiceFlow did).
- **Per conversation**: transcript, recording with waveform (wavesurfer.js), summary, extracted fields, score, trace.
- **Improve loop** (the user's step 7, implemented):
  1. **Flag**: customer thumbs-down, admin flag, or auto-flag (low confidence, handoff, negative sentiment, judge failure).
  2. **Nightly job** at 02:00 workspace local time: cluster flagged turns, have the LLM propose a corrected answer plus the source it should have used.
  3. **Review queue** (Tinder-style approve/edit/reject).
  4. Approved items become **golden answers**: exact-match and few-shot, retrieved by similarity. They can optionally be published as a knowledge source.
  5. A weekly email summary: "12 answers improved, containment +4%."
- Storage: Postgres with materialized views, refreshed by the worker. Upgrade path is ClickHouse when volume demands it.

---

## 14. BYOK: provider registry, validation and the vault

### 14.1 Provider matrix (initial)

| Category | Providers | Validation call |
|---|---|---|
| LLM | Groq, Google Gemini (AI Studio), OpenAI, Anthropic, OpenRouter, Cerebras, Mistral, DeepSeek, Together, Fireworks, Azure OpenAI, AWS Bedrock (phase 3), **Ollama/LM Studio (local, no key)**, any OpenAI-compatible base URL | `GET /models` or a 1-token completion. Store the returned model list for the dropdown |
| STT | Groq Whisper, Deepgram, AssemblyAI, Gladia, Speechmatics, OpenAI, Azure Speech, Google STT, **local faster-whisper/Vosk** | Transcribe a bundled 1-second sample |
| TTS | Cartesia, Deepgram Aura, OpenAI, Azure, Google, Gemini TTS, ElevenLabs, **Edge (no key), Kokoro, Supertonic, Piper (local)** | Synthesize "ok" |
| Speech-to-speech | Gemini Live, OpenAI Realtime, (later Ultravox) | Open and close a session |
| Embeddings | **fastembed local (default)**, Gemini, OpenAI, Voyage, Cohere, Jina, Mistral | Embed "ok", read dimensions |
| Reranking | **FlashRank local (default)**, Cohere, Jina, Voyage | Rerank 2 docs |
| Telephony | Twilio, Exotel, Plivo, Telnyx, Vonage | Account fetch |
| Messaging | WhatsApp Cloud (via Embedded Signup token), Telegram bot token, Resend, SMTP | `getMe` / phone number fetch / test send |
| Integrations | OAuth apps (Google, HubSpot, Zoho…) | Token introspection |

- Text LLM calls go through **LiteLLM** (Python SDK only, not its proxy server). It's one interface for 100+ providers, with cost tables and streaming.
- Voice uses the corresponding **Pipecat services**.
- Our `providers` lib wraps both behind `LLMProvider`, `STTProvider`, `TTSProvider` and so on, each with `validate()`, `list_models()`/`list_voices()` and `estimate_cost()`.

### 14.2 Vault
- **Envelope encryption**:
  - Each workspace has a random data key, encrypted with the master key-encryption key from `DF_MASTER_KEY` (later AWS KMS or GCP KMS).
  - Each secret is AES-256-GCM with the workspace data key. Associated data is `workspace_id|provider|field`, so ciphertext can't be swapped between rows.
- Secrets are never returned to the browser: masked as `gsk_••••3f9a`, with last-validated time, status and a rotate button.
- **Health checks**: daily re-validation. If a key fails (revoked, quota exhausted), the agent falls back to its configured fallback provider and the owner is alerted. **Fallback chains** per category, for example LLM: Groq → Gemini → Ollama.
- **Usage and cost meter** per provider, from token and second counts multiplied by public price tables: "This month your Groq usage ≈ $3.12." It's transparent, and it builds trust.

---

## 15. Billing and pricing

### 15.1 Model
- **BYOK platform pricing**: we never mark up tokens or minutes from providers. Customers pay providers directly.
- We charge a **subscription** (includes agents, seats and a pool of platform minutes and messages) plus **metered overage** through Dodo usage events.
- **Unlimited channels on every paid plan**, which is the strategic lever.
- Local engines (Kokoro, Supertonic, faster-whisper) consume *our* CPU, so they draw from the same minute pool.
- Phase 3 option: **"Managed keys" add-on**. We supply providers at cost plus 30% for customers who don't want BYOK, and it's a natural upsell.

### 15.2 Plans (proposal)

| | Free | Starter | Growth | Scale | Agency | Enterprise |
|---|---|---|---|---|---|---|
| India / month | ₹0 | ₹1,499 | ₹4,999 | ₹14,999 | ₹24,999 | Custom |
| Global / month | $0 | $19 | $59 | $179 | $297 | Custom |
| Agents | 1 | 3 | 10 | Unlimited | Unlimited | Unlimited |
| Voice minutes incl. (platform) | 60 | 1,000 | 5,000 | 20,000 | 25,000 pooled | Committed |
| Chat messages incl. | 500 | 10,000 | 50,000 | 250,000 | 300,000 pooled | Committed |
| Channels | Web + widget + browser voice | All | All | All | All | All + custom |
| Seats | 1 | 3 | 10 | 25 | 50 | Unlimited |
| CRM contacts | 250 | 2,500 | 25,000 | 250,000 | Unlimited | Unlimited |
| Automations & campaigns | – | Basic | ✔ | ✔ | ✔ | ✔ |
| Sub-accounts / white-label | – | – | – | 3 | Unlimited + white-label | ✔ |
| Branding removal | – | – | ✔ | ✔ | ✔ | ✔ |
| Retention | 7 d | 30 d | 90 d | 1 yr | 1 yr | Custom |
| SSO/SAML, audit export, SLA, data residency, on-prem | – | – | – | – | – | ✔ |

- **Overage**: voice ₹0.80/min ($0.012/min), chat ₹0.04/message ($0.0006). Compare Vapi's $0.05/min platform fee: we're roughly 4× cheaper.
- **Annual**: 2 months free.
- **Free trial of Growth**: 14 days, with no card on India UPI flows if Dodo allows. Otherwise card required at day 14.
- **Enterprise**: from ~₹2.5 lakh/yr or $10k/yr. Volume minute commits, private deployment (it's all docker-free Python and Node, so it installs on their VMs), and a DPA.
- Why this wins:
  - SMB: cheaper than GHL's $97 AI add-on alone.
  - Developers: platform fee below Vapi and Bolna.
  - MNCs: on-prem and local-model mode plus BYOK means their keys, their data.

> Validate pricing with 10–15 design partners before launch. Plan limits live in one config file, as WhatsHelp's `lib/plans.ts` did, so changes are cheap.

### 15.3 Dodo integration
Products per plan and interval, plus add-ons (extra agents, extra seats, minute packs, white-label). Checkout → webhook (standardwebhooks signature) → `subscriptions` table → entitlement cache. Usage events are batched hourly to Dodo meters. Customer portal link. Handle UPI mandate rules (RBI) for Indian recurring payments, as WhatsHelp did for plan changes.

---

## 16. Frontend and design system

### 16.1 Design direction: "calm, precise, alive"
- **References**: Linear (density, keyboard-first), Attio (best-in-class CRM UI), Vercel dashboard (clarity), Intercom Fin (inbox), Cal.com (booking), Canva and Notion (templates and onboarding warmth), and the Retell and Vapi dashboards (what voice users expect).
- **Typography**: **Geist Sans** (UI) plus **Geist Mono** (IDs, code, latency numbers). Marketing headlines in **Instrument Serif** italic for contrast. All free from Google Fonts or Vercel.
- **Color**: neutral zinc base, one accent (**indigo-violet `#6D5EF8`**), semantic colors, and **channel colors** used consistently everywhere (Voice = violet, Web = blue, WhatsApp = green, Telegram = sky, Phone = amber, Email = slate). Light and dark themes from day one, with OKLCH tokens in Tailwind v4.
- **Motion**: Motion (Framer) for meaningful transitions only in the app (panel slides, list reordering, live-status pulses). Spectacle is reserved for marketing.
- **Signature element**: the **voice orb**, a WebGL or canvas sphere reacting to mic and TTS amplitude. It appears in the playground, widget, live monitor and hero, so the brand feels "alive".

### 16.2 Component strategy
- **shadcn/ui** (Radix + Tailwind v4) is the base for the dashboard. We own the code and it's themeable.
- **HeroUI v3** was considered (Tailwind v4, React Aria, an MCP server). It's good, but mixing two primitive systems causes inconsistency. **Decision: shadcn for the app.** We borrow HeroUI patterns, not the package.
- **Aceternity UI, Magic UI and 21st.dev** blocks for marketing: beams, spotlight, bento grids, animated beam "one brain → channels", marquee logos, number tickers, globe. **21st.dev MCP** and **Aceternity MCP** speed up generation during development.
- **Specialised libraries**:
  - `@xyflow/react` (flows and automations), `@dnd-kit` (kanban), TanStack Table and Virtual (CRM tables), TanStack Query (server state).
  - cmdk (⌘K), Sonner (toasts), vaul (mobile drawers), shadcn charts (Recharts).
  - wavesurfer.js (recordings), Tiptap (prompt editor with variable chips), Monaco (JSON schemas and code), react-hook-form + zod, nuqs (URL state).
  - `@pipecat-ai/client-js` + `client-react` (voice UI), Fumadocs (docs).
- **Widget**: Preact + Shadow DOM, themeable through a JSON config, ~40 KB gzipped, lazy-loads the voice module only when the call button is pressed.

### 16.3 UX principles
1. **Templates first, blank second** (Canva). Twelve-plus use-case templates with sample knowledge so new users can try them instantly.
2. **Toggles, not rebuilds** for channels.
3. **Always show why**: diagnostics everywhere.
4. **Safe editing**: draft/publish, version history, undo for AI CRM changes.
5. **Keyboard-first** for power users (⌘K, J/K in inbox, E to resolve).
6. **Realtime everywhere**: presence on records, live counts, toasts.
7. **Empty states that teach**: each has a one-line explanation plus a primary action plus a sample.
8. **Collaboration** (Teams/SharePoint feel): @mentions in notes, assignments, shared views, activity feed, comments on conversations.
9. **Accessibility**: WCAG 2.1 AA, which Radix gives a head start on.
10. **Mobile-responsive inbox** (humans answer handoffs from their phones). Installable PWA with push.

---

## 17. Name

"DialogFabric" is accurate but sounds like enterprise middleware: hard to say, not memorable, and "dialog" spelling varies by country. Candidates, with the core idea "one voice, many places":

| Name | Why | Quick check (search only, **not** a trademark search) |
|---|---|---|
| **Unisona** | "In unison": one voice across every channel. Easy globally, feminine-agent friendly | No AI company found |
| **Chorale** | Many voices, one composition | Close to Chorus (taken by several AI companies), so riskier |
| **Omnivox** | "All voices" | ❌ Taken (omni-vox.ai) |
| **Voxloom** | Weaves voice and chat | ❌ Taken (voxloom.in) |
| **Parlance** | Way of speaking | ❌ Taken (healthcare voice AI) |
| **Tessel** | Tessellation: one pattern, every surface | Unchecked |
| **Hearth** | Warm, the "home" for customer conversations | Generic, likely domain-hard |

**Recommendation:** **Unisona**, if `.ai`/`.com` and an India and US trademark search come back clean. Otherwise keep DialogFabric as the codename. The codebase uses a neutral `df_` prefix, so renaming later is cheap. Run a proper trademark and domain check before any branding spend.

---

## 18. Data model (core tables, abridged)

```
workspaces(id, clerk_org_id, name, plan, region, agency_id?, branding jsonb, settings jsonb)
members(workspace_id, clerk_user_id, role, teams[], status)
provider_credentials(id, ws, category, provider, enc_payload, masked, status, last_validated_at, fallback_order)
agents(id, ws, name, template_id, status, engine, published_version_id, draft jsonb)
agent_versions(id, agent_id, number, config jsonb, created_by, created_at, notes)
knowledge_bases(id, ws, name) ; agent_knowledge(agent_id, kb_id, priority, when_to_use)
knowledge_sources(id, kb_id, type, uri, status, chunks, refresh_cron, error, meta)
chunks(id, source_id, kb_id, ordinal, text, tokens, meta)          -- mirror of Chroma for citations
datasets(id, kb_id, duckdb_path, schema_card jsonb)                 -- structured data
policies(id, ws, scope{workspace|agent}, scope_id, action, match_type, target)
channels(id, ws, agent_id, type, config jsonb, public_key, enabled)
contacts(id, ws, name, owner_id, lifecycle, score, fields jsonb, consent jsonb)
contact_identities(id, contact_id, type, value_normalized, verified, source)
contact_facts(id, contact_id, fact, category, confidence, valid_from, valid_to, source_msg_id)
conversations(id, ws, agent_id, contact_id, channel, status{ai|handoff_pending|human|closed},
              assignee_id, started_at, ended_at, summary, outcome, sentiment, csat, analysis jsonb)
messages(id, conversation_id, role, content, ir jsonb, channel_msg_id, created_at, flagged)
calls(id, conversation_id, transport, direction, duration_s, recording_uri, latency jsonb, cost jsonb)
turn_traces(id, message_id, router, retrieval jsonb, prompt_sections jsonb, tools jsonb, latency jsonb, tokens jsonb)
golden_answers(id, agent_id|kb_id, question, answer, source_ids, status, embedding_ref)
flags(id, message_id, reason, by, status) ; review_items(...)
handoffs(id, conversation_id, reason, urgency, brief, team_id, assignee_id, requested_at, accepted_at, resolved_at)
tools(id, ws, type{http|mcp|builtin|integration}, config jsonb, enc_auth)
integrations(id, ws, provider, enc_tokens, status)
companies, deals, pipelines, stages, tasks, notes, appointments, calendars, availability
automations(id, ws, graph jsonb, status) ; automation_runs(...steps)
campaigns, campaign_targets, dnd_entries
webhook_endpoints, webhook_deliveries ; api_keys(hash, scopes)
subscriptions, usage_events, entitlements ; audit_log
```

---

## 19. Security, privacy and compliance
- Clerk JWT verification on every request, Postgres RLS, and no tenant identity from headers or cookies.
- Envelope-encrypted secrets, signed webhooks in and out, CSRF-safe (token-based API), strict CORS per channel allow-list.
- Widget domain allow-list and HMAC identity verification.
- Prompt-injection hygiene: retrieved content is fenced as data. Tool calls are allow-listed per agent. `crm_update` cannot touch other contacts. SQL tool is read-only and sandboxed.
- PII redaction option, recording consent prompts, retention jobs, contact-level export and delete (DPDP Act 2023, GDPR).
- Outbound compliance: DND/NCPR, calling windows, frequency caps, opt-out handling ("stop calling me" triggers DND automatically).
- Voice cloning only with verified consent, and watermark metadata on generated audio.
- Audit log of every config change, key access, data export and AI CRM change.
- Observability: structlog JSON logs, OpenTelemetry traces (exportable to Langfuse Cloud, Grafana Cloud or Sentry, all with free tiers), plus our own `turn_traces`.

---

## 20. What I'll reuse from the two existing projects

| From | Reuse (adapted) | Don't reuse |
|---|---|---|
| VoiceFlow | Layered context assembly and policy scoring; template catalog (10 use cases); AES-GCM credential pattern (upgraded to envelope); compliance, campaign, AMD and IVR concepts; voice catalog idea; simulation and A/B concepts; retraining loop design; MCP and SDK ideas | Header-trust auth, Django frontend, hand-rolled RMS VAD, Redis/MinIO/Docker dependencies, `create_all` + column-patch migrations |
| WhatsHelp GPT | WhatsApp webhook (signature, idempotency, buffering), predefined prompts and Flows as tools, `handoff_to_human` tool pattern, conversation summaries, `customer_identities` and unified messages idea, plan-limits config file, Dodo integration and India mandate handling, onboarding stepper UX, team inbox UX, Pinecone/Chroma toggle pattern | Supabase-shim auth, Trigger.dev (replaced by Procrastinate), two divergent AI paths (we have one brain), Vertex-specific code |

---

## 21. Roadmap (build order)

Each phase ends with something demoable and usable.

**Phase 0: Foundations**
Monorepo, uv and pnpm workspaces, Turbo dev. Clerk (web plus backend JWT verification, org sync). Postgres with Alembic and RLS. Procrastinate. Chroma server. Settings, logging, the doctor script. Design tokens, app shell, ⌘K, marketing skeleton. Vault and provider registry with validators for Groq, Gemini, OpenAI, OpenRouter, Ollama, Deepgram, Cartesia and local engines.

**Phase 1: "One brain" MVP (web + voice)**
- Knowledge ingestion: URL/Crawl4AI, PDF, DOCX, text and CSV (DuckDB), with hybrid retrieval and diagnostics.
- Agent builder: persona, voice, knowledge, built-in tools, draft/publish.
- **Playground with glass-box diagnostics.**
- Pipecat voice gateway on SmallWebRTC: Silero, Smart Turn, faster-whisper/Groq/Deepgram, Kokoro/Supertonic/Edge/Cartesia, barge-in.
- Web chat hosted page and the **widget** (chat plus voice).
- Contacts and identity (web), conversations, inbox v1, handoff v1 (in-app alerts, take over chat, join WebRTC call).
- 4-step onboarding with auto-scrape and trial credits.
- Basic analytics.

**Phase 2: Omnichannel and CRM core**
- WhatsApp (Embedded Signup, templates, buttons/lists) and Telegram.
- Cross-channel identity linking and OTP verification, memory facts and contact brief.
- CRM: contacts, companies, deals/pipelines, tasks, notes, calendar and booking page, Google Calendar and Cal.com.
- Post-conversation analysis and Auto-CRM.
- Improve loop (flags, nightly job, review, golden answers).
- Handoff v2 (routing, SLA, email, Slack, push).
- Dodo billing and entitlements.
- Analytics v2. Live monitor (listen, whisper, take over).
- Gemini Live engine (BYOK). Voice cloning (Chatterbox, GPU optional).

**Phase 3: Telephony, automation, ecosystem**
- Twilio, Exotel and Plivo numbers (BYOK), inbound and outbound, AMD, transfer, DTMF.
- Campaigns with compliance. Automations builder.
- HTTP tools, MCP client and **MCP server**. Integrations (HubSpot, Zoho, Freshdesk, Shopify, Razorpay, Teams).
- Email channel. Simulations and the publish gate.
- Agency mode with Blueprints and white-label. Public API and SDKs. Indic voice and STT pack.

**Phase 4: Enterprise and scale**
- SSO/SAML and SCIM (Clerk), audit export, data residency, on-prem installer.
- LiveKit or Daily transport, SIP trunking, horizontal voice-worker autoscaling.
- ClickHouse analytics. Instagram/Messenger, Slack and Teams agents. SOC 2 preparation.

---

## 22. `.env` — what you'll need to fill in

**Required to run locally**
```
# Clerk
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=
CLERK_WEBHOOK_SIGNING_SECRET=
# Core
DATABASE_URL=postgresql+asyncpg://...      # native Postgres or Neon
CHROMA_URL=http://localhost:8200
DF_MASTER_KEY=                              # 32-byte base64; `uv run df keys gen`
FILE_STORE=local                            # local | s3
APP_URL=http://localhost:3000
API_URL=http://localhost:8000
VOICE_URL=http://localhost:8100
```

**Needed for specific features**
```
# Onboarding trial credits (your own free-tier key, heavily rate-limited)
TRIAL_LLM_PROVIDER=gemini   TRIAL_LLM_API_KEY=
# Payments
DODO_PAYMENTS_API_KEY=  DODO_WEBHOOK_SECRET=  DODO_ENVIRONMENT=test_mode
# WhatsApp (your Meta app; tenants bring their own WABA via Embedded Signup)
META_APP_ID=  META_APP_SECRET=  META_WHATSAPP_CONFIG_ID=  META_WEBHOOK_VERIFY_TOKEN=
# Transactional email for alerts (free tier)
RESEND_API_KEY=            # or SMTP_*
# Web push for handoff alerts (generate locally)
VAPID_PUBLIC_KEY=  VAPID_PRIVATE_KEY=
# OAuth apps for integrations
GOOGLE_OAUTH_CLIENT_ID=  GOOGLE_OAUTH_CLIENT_SECRET=
# Optional
SENTRY_DSN=  POSTHOG_KEY=  REDIS_URL=  S3_*=  OTEL_EXPORTER_OTLP_ENDPOINT=
```

**Not needed by us** (tenant BYOK, entered in the UI): Groq, Gemini, OpenAI, Anthropic, Deepgram, Cartesia, Twilio, Exotel, Telegram bot tokens and so on. For your own testing you'll add your personal keys through the UI like any tenant.

**Local model downloads** (automatic on first run, no keys): Silero VAD, Smart Turn v3, faster-whisper (`small`), Kokoro, Supertonic, fastembed `bge-small` / `multilingual-e5-small`, FlashRank, Crawl4AI's Chromium (`crawl4ai-setup`). Plus ffmpeg installed natively.

---

## 23. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Edge TTS is unofficial and may break | Never the only option. Kokoro and Supertonic are local defaults, and BYOK cloud is available. Feature-flag it |
| SmallWebRTC behind strict NATs and corporate networks | Configure free STUN, and add a TURN option (coturn is native, no Docker, or a free-tier Metered.ca TURN). Long-term: LiveKit or Daily transport |
| CPU load from local STT/TTS at scale | Separate voice workers. Per-plan engine limits. Push heavy users to BYOK cloud providers |
| WhatsApp policy (24-hour window, template approval, opt-in) | Template manager, opt-in tracking, quality-rating alerts |
| Scope explosion (CRM is huge) | Phased plan. Conversation-first CRM. Skip funnels and websites |
| Windows-specific dependency issues (aiortc, onnxruntime, Playwright) | Pin versions, a doctor script, test matrix on Windows and Linux in CI (GitHub Actions, no Docker) |
| Hallucination complaints | Confidence threshold, golden answers, citations and diagnostics, simulations before publish |

---

## 24. Sources (research, Oct 2026)
- Voice AI pricing comparisons: [caller.digital](https://caller.digital/voice-ai-pricing-comparison), [stackbinary.io](https://stackbinary.io/insights/voice-ai-pricing-per-minute-2026), [zeeg.me](https://zeeg.me/en/blog/post/ai-voice-agent-pricing-guide)
- Vapi/Retell gaps: [autocalls.ai](https://autocalls.ai/article/retell-ai-vs-vapi)
- GoHighLevel AI and pricing: [netpartners.marketing](https://netpartners.marketing/gohighlevel-ai-pricing/), [rocketlauncher.ai](https://rocketlauncher.ai/voice-ai); features: [thestackinsiders.com](https://www.thestackinsiders.com/blog/gohighlevel-features-list)
- AgentPhone: [agentphone.ai](https://agentphone.ai/), [YC launch](https://www.ycombinator.com/launches/QNE-agentphone-phone-numbers-for-ai-agents)
- Pipecat Smart Turn: [github.com/pipecat-ai/smart-turn](https://github.com/pipecat-ai/smart-turn); SmallWebRTC: [docs.pipecat.ai](https://docs.pipecat.ai/server/services/transport/small-webrtc), [Daily blog](https://www.daily.co/blog/you-dont-need-a-webrtc-server-for-your-voice-agents/)
- Pipecat vs LiveKit: [forasoft](https://www.forasoft.com/blog/article/pipecat-vs-livekit-agents), [channel.tel](https://www.channel.tel/blog/pipecat-vs-livekit-voice-framework-decision)
- Supertonic: [github.com/supertone-inc/supertonic](https://github.com/supertone-inc/supertonic)
- Open TTS landscape (Kokoro, Chatterbox): [ocdevel](https://ocdevel.com/blog/20250720-tts), [tryspeakeasy](https://www.tryspeakeasy.io/blog/open-source-text-to-speech-2026)
- Indic speech: [IndicF5](https://github.com/AI4Bharat/IndicF5), [vexyl-tts](https://github.com/vexyl-ai/vexyl-tts)
- Speech-to-speech pricing (Gemini Live, OpenAI Realtime, Ultravox): [inworld.ai](https://inworld.ai/resources/openai-realtime-api-alternatives), [layer3labs](https://www.layer3labs.io/guides/openai-realtime-api-pricing)
- Free LLM tiers: [ianlpaterson.com](https://ianlpaterson.com/blog/free-llm-api-2026/), [perkstack.co](https://perkstack.co/blog/free-ai-api-credits)
- Chroma sparse/BM25 locally: [chroma issue #6185](https://github.com/chroma-core/chroma/issues/6185), [Chroma BM25 docs](https://docs.trychroma.com/integrations/embedding-models/chroma-bm25)
- fastembed / FlashRank: [qdrant fastembed](https://qdrant.tech/documentation/fastembed/), [FlashRank](https://github.com/PrithivirajDamodaran/FlashRank)
- Crawl4AI: [github.com/unclecode/crawl4ai](https://github.com/unclecode/crawl4AI)
- Agent memory (mem0 vs Zep/Graphiti): [vectorize.io](https://vectorize.io/articles/mem0-vs-zep)
- Dodo Payments metering and UPI: [dodopayments.com](https://dodopayments.com/blogs/stripe-usage-based-billing-vs-dodo), [India methods](https://docs.dodopayments.com/features/payment-methods/india)
- UI: [HeroUI v3](https://www.infoq.com/news/2026/07/heroui-v3-rewrite/), [21st MCP](https://21st.dev/mcp), [Aceternity UI Pro](https://ui.aceternity.com/pro)
