# Code Standards

## General

- Build end to end first; keep modules single-purpose and readable.
- Fix root causes. Optional integrations degrade gracefully through `feature_unavailable` instead of raising.
- Log with intent: `get_logger("area")`, an INFO line per meaningful event, WARNING for skipped features, never secrets.

## Python (services/api)

- Python 3.12, async everywhere (SQLAlchemy async sessions, httpx). Blocking libraries (Chroma, fastembed, DuckDB, PyAV) go through `asyncio.to_thread`.
- Settings only through `unisona.config.settings`. Never read `os.environ` elsewhere.
- IDs are prefixed strings from `new_id("ag")`, `new_id("cv")`, …
- Schema changes require an Alembic migration (`uv run alembic revision --autogenerate -m "..."`).
- LLM calls go through `providers.llm.get_llm(db, ws, feature=...)`, which resolves BYOK keys and meters usage.

## TypeScript (apps/web, apps/widget)

- Strict mode. `any` is tolerated only for API payloads that are not yet typed. Prefer narrow types for new code.
- Data fetching: TanStack Query + `useApi()` from `lib/api.ts` (attaches the Clerk or dev token).
- Realtime: `useRealtime()` from `lib/workspace.tsx` (one WebSocket per tab).

## Next.js

- Next 16: route protection lives in `src/proxy.ts`. Dynamic `params` are Promises, so client pages use `useParams()`.
- Dashboard pages are client components (`"use client"`). Marketing pages can be server components.
- `useEffect` callbacks must not return values. Wrap expression bodies in braces, because `scrollIntoView` now returns a Promise in Chrome.

## Styling

- Use only Tailwind classes on theme tokens (see ui-context.md) and avoid hardcoded hex.
- Use the `.md` class for rendered markdown; there is no typography plugin.

## API Routes

- Validate input (Pydantic models or explicit checks) before any work.
- Scope with `require_auth` + `get_scoped` / `crud_router`. Use `require_role("admin")` for settings.
- List responses are `{items, total}`; errors are `HTTPException(status, detail)`.
- Long work is `enqueue(...)` and returns immediately.

## Data and Storage

- Metadata and text in Postgres; vectors, indexes, tables, files and recordings under `DATA_DIR`.
- Secrets only through `security.crypto` (envelope encryption).

## File Organization

- `apps/web/src/app/` — routes. `app/app/*` is the dashboard; `chat/[key]`, `book/[slug]` and `widget-demo` are public.
- `apps/web/src/components/` — `ui/` (shadcn), `app/` (shell), `agent/` (builder), `landing/`.
- `apps/web/src/lib/` — api client, env, workspace/realtime, voice hook and formatters.
- `services/api/unisona/` — see architecture.md for the module boundaries.
- `services/api/tests/` — pytest unit tests (`test_*.py`) and `e2e_voice.py`.
- `scripts/` — `setup.mjs`, `dev.mjs`, `sync-env.mjs`.
