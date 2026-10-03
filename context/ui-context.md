# UI Context

## Theme

Light-first with full dark mode (next-themes, `class` strategy). The style is calm, premium SaaS: neutral surfaces, one violet
brand accent, and channel colours used only for channel badges. Inspirations: shadcn, 21st.dev, Aceternity, HeroUI.
Marketing pages use subtle motion (motion/react), an animated voice orb and gradient text. The dashboard stays quiet.

## Colors

Tokens live in `apps/web/src/app/globals.css` (oklch). Use the Tailwind classes generated from them and never use raw hex
in components. The only exception is user-chosen widget colours.

| Role            | Token / class                    | Value (light)              |
| --------------- | -------------------------------- | -------------------------- |
| Page background | `--background` / `bg-background` | `oklch(1 0 0)`             |
| Surface         | `--card` / `bg-card`             | white, subtle border       |
| Muted surface   | `--muted` / `bg-muted`           | neutral 97%                |
| Primary text    | `--foreground`                   | neutral 14.5%              |
| Muted text      | `--muted-foreground`             | neutral 55%                |
| Brand accent    | `--brand` / `bg-brand`           | `oklch(0.585 0.215 285)`   |
| Brand soft      | `--brand-soft` / `bg-brand-soft` | violet tint                |
| Success         | `--success`                      | green                      |
| Warning         | `--warning`                      | amber                      |
| Error           | `--destructive`                  | red                        |
| Channels        | `--ch-voice/whatsapp/telegram/web/email/sms` | per-channel hues |

## Typography

| Role      | Font             | Variable         |
| --------- | ---------------- | ---------------- |
| UI text   | Geist Sans       | `--font-sans`    |
| Display   | Instrument Serif | `--font-display` (`font-display` class, headings on landing/booking) |
| Code/mono | Geist Mono       | `--font-mono`    |

## Border Radius

| Context           | Class        |
| ----------------- | ------------ |
| Inline / small UI | `rounded-md` |
| Cards / panels    | `rounded-xl` |
| Modals / overlays | `rounded-2xl`|
| Chips / bubbles   | `rounded-full` / `rounded-2xl` |

## Component Library

shadcn/ui (radix-nova style) in `apps/web/src/components/ui/`. Add components with the shadcn CLI. Shared app pieces:
`components/common.tsx` (PageHeader, EmptyState, StatusBadge, ChannelBadge, StatCard), `components/orb.tsx` (VoiceOrb),
`components/brand.tsx` (Logo) and `components/agent/*` (agent builder forms, playground, diagnostics).

## Layout Patterns

- App shell: collapsible left sidebar (`components/app/sidebar.tsx`), top bar with ⌘K search, workspace switcher and notifications.
- Pages: a `PageHeader` (icon + title + description + actions), then content padded `p-6`.
- Agent builder: tabs (Overview, Persona, Knowledge, Voice, Tools, Channels, Guardrails, Analytics). The Playground uses a split view with a diagnostics panel.
- Inbox: three columns (list, thread, contact panel).
- Modals: shadcn Dialog/Sheet with backdrop blur.

## Icons

Lucide React. Use `size-4` inline and in buttons, and `size-5` in headers.
