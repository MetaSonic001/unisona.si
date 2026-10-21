# Deploying Unisona (Vercel + Render, no Docker)

| Part | Where | Config file |
| --- | --- | --- |
| Web app (Next.js, `apps/web`) + embeddable widget | **Vercel** | `apps/web/vercel.json` |
| API (FastAPI + voice + worker + scheduler, `services/api`) | **Render** (native Python runtime) | `render.yaml` (Blueprint) |
| Database + file storage | **Supabase** (already set up) | `DATABASE_URL`, `SUPABASE_SECRET_KEY` |
| WebRTC relay for browser voice calls | **Cloudflare Realtime TURN** (free tier) | `CLOUDFLARE_TURN_*` |

## What it costs

| Service | Plan | Why |
| --- | --- | --- |
| Render | **Standard (2 GB RAM)**, about $25/month | The API keeps a multilingual embedding model, a reranker and voice models in memory: about 0.8–1.1 GB measured. Render's Free and Starter instances have 512 MB and would crash out of memory. Free instances also sleep after 15 minutes, which kills phone calls, Telegram polling and the job scheduler. |
| Vercel | Hobby (free) to start | Hobby is for non-commercial use. Move to Pro when you charge customers. |
| Supabase | Free | 500 MB database and 1 GB storage. A free project **pauses after 7 days without activity**. The deployed API queries it every few seconds, so it stays awake while the API runs. |
| Cloudflare TURN | Free tier (1,000 GB/month) | Only browser voice calls use it. |
| Groq | Free tier | Rate-limited: you will see `429 Too Many Requests` retries under load. Customers can bring their own keys (BYOK), or upgrade the platform key. |

**Fully free alternative:** an Oracle Cloud "Always Free" ARM VM (4 cores, 24 GB RAM, public IP) runs the API without Docker using `uv` + `systemd` + Caddy for HTTPS. WebRTC also works there without TURN, because the VM receives UDP directly. Ask if you want a script for that.

## 1. Before you start

1. Commit and push this repo to GitHub (`origin` = `MetaSonic001/unisona.si`).
2. **Supabase:** check that the project is **Active**, not Paused, in the dashboard. Collect:
   - `DATABASE_URL`: Connect → **Session pooler** (port 5432). Don't use the transaction pooler (6543) or the IPv6-only direct host.
   - `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SECRET_KEY` (Project settings → API keys). The API uses them to store uploads and call recordings in a private `unisona-files` bucket, which it creates itself.
3. **Clerk:** you can launch with the development keys (`pk_test_…`/`sk_test_…`); they work on `*.vercel.app` but show a "Development mode" badge. For real customers, create a Clerk **production** instance. It needs your own domain (DNS records shown in Clerk); then swap in the `pk_live_…`/`sk_live_…` keys.
4. **Cloudflare TURN** (for browser voice calls; phone calls don't need it): Cloudflare dashboard → Realtime → TURN Server → Create. Copy the **Turn Token ID** (`CLOUDFLARE_TURN_KEY_ID`) and **API Token** (`CLOUDFLARE_TURN_API_TOKEN`).
5. `UNISONA_MASTER_KEY`: use the **same value as your local `.env`**. Provider keys that workspaces saved are encrypted with it; a different key makes them unreadable.

## 2. Deploy the API on Render

1. Render dashboard → **New → Blueprint** → connect the GitHub repo → it reads `render.yaml`.
2. Fill the values marked `sync: false`. At minimum:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | Supabase session pooler URL |
   | `UNISONA_MASTER_KEY` | the same value as local `.env` |
   | `GROQ_API_KEY` | your Groq key |
   | `CLERK_SECRET_KEY` | your Clerk secret key |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | your Clerk publishable key |
   | `NEXT_PUBLIC_SUPABASE_URL` | your Supabase project URL |
   | `SUPABASE_SECRET_KEY` | your Supabase secret key |
   | `CLOUDFLARE_TURN_KEY_ID` | from step 1.4 |
   | `CLOUDFLARE_TURN_API_TOKEN` | from step 1.4 |
   | `API_URL` and `PUBLIC_WEBHOOK_URL` | `https://<service-name>.onrender.com`; Render shows the URL after the first deploy, so you can fill these afterwards |
   | `APP_URL` | your Vercel URL from step 3; fill it in afterwards |

   Leave the rest empty unless you use them.
3. Deploy. The build takes about 5–8 minutes:
   - It installs dependencies with `uv`.
   - It upgrades `edge-tts` to the newest release.
   - It downloads the ML models into the build, so restarts don't download them again.

   Every start runs `alembic upgrade head` first.
4. Check:
   - `https://<api>.onrender.com/health` returns `{"ok":true,...}`
   - `https://<api>.onrender.com/health/ready` returns `{"ok":true,"db":"ok"}`
   - The Logs tab shows `Database connected`, `Embedding model warmed up` and `API ready`.

## 3. Deploy the web app on Vercel

1. Vercel → **Add New → Project** → import the same repo.
2. **Root Directory: `apps/web`**. Vercel detects Next.js and pnpm. `vercel.json` sets the install and build commands: it builds the widget, copies it to `/widget/widget.js`, then builds Next.js. Keep "Include files outside the root directory" enabled (the default).
3. Environment variables (Production):

   | Variable | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_URL` | `https://<api>.onrender.com` (no trailing slash) |
   | `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | same as Render |
   | `CLERK_SECRET_KEY` | same as Render |
   | `NEXT_PUBLIC_CLERK_SIGN_IN_URL` | `/sign-in` |
   | `NEXT_PUBLIC_CLERK_SIGN_UP_URL` | `/sign-up` |

   Do **not** set `DEV_MODE`, `DEV_TOKEN` or `NEXT_PUBLIC_DEV_MODE` on Vercel. Dev mode is local-only and is disabled in production builds anyway.
4. Deploy, then copy the URL (e.g. `https://unisona.vercel.app`).
5. Back in Render, set `APP_URL` to that URL (used for links in emails and booking pages, and for the widget redirect). Saving the variable redeploys the API.

## 4. Connect webhooks (only for the channels you use)

| Provider | URL |
| --- | --- |
| Meta, WhatsApp Cloud | `https://<api>.onrender.com/webhooks/whatsapp`, verify token = `META_WEBHOOK_VERIFY_TOKEN` |
| Meta, Instagram + Messenger | `https://<api>.onrender.com/webhooks/meta`, same verify token |
| Twilio / Plivo / Telnyx / Exotel | numbers are connected in the app; they call `PUBLIC_WEBHOOK_URL/...` automatically |
| Dodo Payments (your SaaS billing) | `https://<api>.onrender.com/webhooks/dodo` + `DODO_WEBHOOK_SECRET` |
| Razorpay / Stripe (customers' payment links) | shown per workspace on the Payments page (`/webhooks/payments/{provider}/{workspace}`) |
| Google Calendar OAuth | redirect URI `https://<api>.onrender.com/integrations/google/callback` |

## 5. When something breaks: logs, restarts, alerts

- **Logs:** Render → service → Logs. Production logs are one line per record (`timestamp LEVEL [subsystem] message`) with full tracebacks. Useful searches:
  - `request_id=`: every unhandled error is logged once with method, path, request id and traceback. The browser receives the same `request_id` in the JSON error and in the `x-request-id` header, so a user report maps to one log entry.
  - `DATABASE UNREACHABLE`: logged once when the database drops, plus `Database reachable again` when it returns. Meanwhile API calls answer 503 with a clear message.
  - `FATAL`: the process exited on purpose, after running out of memory or after the event loop was stuck for 90 s. Render restarts it.
  - `Background task 'worker' crashed`: the job worker or scheduler crashed. It restarts itself with backoff; the traceback is in the line.
  - `Edge TTS is rejecting requests`: Microsoft rotated the free-voice token. Redeploy, and the build installs the latest `edge-tts`.
- **Restarts:**
  - Render restarts the service when the process exits or `/health` stops answering. The API exits by itself on fatal errors, so it always comes back clean.
  - A database outage does *not* trigger a restart loop: `/health` stays green, `/health/ready` reports the outage.
- **Rollback:** Render → Events → pick the previous deploy → "Rollback".
- **Alerts:** Render → Notifications (email or Slack on failed deploys and failing health checks). In the app, set `SLACK_ALERT_WEBHOOK_URL` or `RESEND_API_KEY` + `ALERT_FROM_EMAIL` for handoff/escalation alerts.
- **Uptime monitor (optional):** point a free UptimeRobot or cron-job.org check at `/health/ready` every 5 minutes to get an email when the database or API is down.

## 6. What carries over between deploys

Render's disk is wiped on every deploy and restart. That's fine:

| Data | Where it lives | After a redeploy |
| --- | --- | --- |
| Everything business-critical (agents, contacts, conversations, knowledge chunks, jobs) | Postgres | unchanged |
| Search indexes (Chroma + BM25) | local disk | rebuilt from the Postgres chunks on startup (`[heal]` log lines; about 20 s for a few thousand chunks) |
| Spreadsheet tables (DuckDB) | local disk | rebuilt by re-ingesting the stored upload |
| Uploaded files, call recordings | Supabase Storage | unchanged |

## 7. Known limits of this setup

- **Single instance:** the job worker, the scheduler and the Telegram pollers run inside the API process, so don't scale Render to 2+ instances. Polling would duplicate. Scale up the instance size instead.
- **Region latency:** Render Singapore ↔ Supabase Tokyo is about 70 ms per query. Moving Supabase to Mumbai (`ap-south-1`) cuts this for Indian users; that means creating a new project and migrating.
- **Optional local engines:** Kokoro TTS and local Whisper (`uv sync --extra local-voice`) are not installed on Render. Agents set to them fall back to Edge voices and Groq Whisper automatically.
