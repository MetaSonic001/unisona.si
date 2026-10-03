# AI Workflow Rules

## Approach

Build end to end first, then harden. The context files define what exists and how it fits together. The product plan in
`docs/PRODUCT_PLAN.md` is the long-form spec. Implement against these and keep them in sync. Verify each unit by
actually running it (API call, browser check, eval run) rather than only type-checking.

## Scoping Rules

- Work on one feature unit at a time (e.g. "campaign engine", "booking page").
- Prefer small, verifiable increments over large speculative changes.
- Keep channel adapters thin; shared behaviour belongs in `brain/`.

## When to Split Work

Split an implementation step if it combines:

- Database schema changes and UI changes.
- Voice pipeline changes and text pipeline changes.
- Behaviour not yet described in the context files or the product plan.

If a change cannot be verified end to end quickly, the scope is too broad, so split it.

## Handling Missing Requirements

- Do not invent product behaviour that contradicts the plan. Choose the conventional default and note it in `progress-tracker.md`.
- Constraints that always apply: free tools only, BYOK for paid ones, no Docker, local-first, Groq as the default LLM.

## Protected Files

Do not modify the following unless explicitly instructed:

- `apps/web/src/components/ui/*`: generated shadcn components (regenerate with the CLI instead).
- `.env`: the user's secrets. Change `.env.example` instead and tell the user.
- Applied Alembic migrations in `services/api/alembic/versions/`. Add a new revision instead.

## Keeping Docs in Sync

Update the relevant context file whenever the implementation changes:

- System architecture or boundaries
- Storage model decisions
- Code conventions or standards
- Feature scope

## Before Moving to the Next Unit

1. The current unit works end to end within its scope (API + UI where relevant).
2. No invariant in `architecture.md` is violated.
3. `progress-tracker.md` reflects the completed work.
4. `pnpm --filter web typecheck` and `pnpm test:api` pass.
