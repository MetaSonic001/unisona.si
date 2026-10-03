"use client";

import {
  ArrowRight, BadgeCheck, Bot, Brain, Calendar, Check, CircleDollarSign, FlaskConical, Globe, Headphones, KeyRound, Languages,
  LineChart, MessageCircle, Mic, Phone, PlugZap, Radar, Send, ShieldCheck, Sparkles, UserRoundCheck, Users, Workflow, X,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { Logo } from "@/components/brand";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const fade = { initial: { opacity: 0, y: 16 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-80px" }, transition: { duration: 0.5 } };

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand">{children}</p>;
}

export function LanguageStrip() {
  const langs = ["English", "हिन्दी", "Hinglish", "தமிழ்", "తెలుగు", "বাংলা", "मराठी", "ગુજરાતી", "ಕನ್ನಡ", "മലയാളം", "اردو", "Español", "Français", "Deutsch", "العربية", "Português", "日本語", "中文", "Bahasa", "Türkçe"];
  return (
    <section className="border-y bg-muted/30 py-5">
      <div className="relative mx-auto max-w-6xl overflow-hidden px-5 [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
        <motion.div className="flex w-max gap-10 text-sm text-muted-foreground" animate={{ x: ["0%", "-50%"] }} transition={{ duration: 40, repeat: Infinity, ease: "linear" }}>
          {[...langs, ...langs].map((l, i) => (
            <span key={i} className="whitespace-nowrap">
              <Languages className="mr-2 inline size-3.5 text-brand/70" />
              {l}
            </span>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

const CHANNEL_CARDS = [
  { icon: Phone, name: "Phone calls", note: "Twilio · Exotel · Plivo", c: "text-ch-phone" },
  { icon: MessageCircle, name: "WhatsApp", note: "Buttons, lists, templates", c: "text-ch-whatsapp" },
  { icon: Send, name: "Telegram", note: "Bots in 10 seconds", c: "text-ch-telegram" },
  { icon: Globe, name: "Web chat", note: "Hosted page + citations", c: "text-ch-web" },
  { icon: Sparkles, name: "Website widget", note: "Chat + voice, one script", c: "text-ch-voice" },
  { icon: Mic, name: "Browser calls", note: "WebRTC, no phone needed", c: "text-ch-voice" },
];

export function OneBrain() {
  return (
    <section id="product" className="mx-auto max-w-6xl px-5 py-24">
      <motion.div {...fade} className="mx-auto max-w-2xl text-center">
        <Eyebrow>One brain, many voices</Eyebrow>
        <h2 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">Configure once. Deploy everywhere in 10 seconds.</h2>
        <p className="mt-4 text-muted-foreground">
          Every channel shares the same knowledge, personality, tools and memory. Turning on a channel is a toggle, not a rebuild. The
          answer adapts to the channel: spoken naturally on calls, buttons on WhatsApp, rich text with sources on the web.
        </p>
      </motion.div>
      <div className="relative mt-14 grid items-center gap-8 lg:grid-cols-[1fr_auto_1fr]">
        <div className="grid gap-3">
          {CHANNEL_CARDS.slice(0, 3).map((c, i) => (
            <ChannelCard key={c.name} {...c} delay={i * 0.06} />
          ))}
        </div>
        <motion.div {...fade} className="glow-border mx-auto w-[280px] rounded-3xl border bg-card p-6 text-center shadow-xl">
          <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-soft text-brand">
            <Brain className="size-7" />
          </span>
          <p className="mt-4 font-semibold">Your agent&apos;s brain</p>
          <ul className="mt-3 space-y-1.5 text-left text-sm text-muted-foreground">
            {["Knowledge from docs, sites & sheets", "Persona, tone & languages", "Tools: CRM, calendar, payments, APIs", "Memory per person, not per channel", "Handoff rules & guardrails"].map((t) => (
              <li key={t} className="flex gap-2">
                <Check className="mt-0.5 size-4 shrink-0 text-brand" /> {t}
              </li>
            ))}
          </ul>
        </motion.div>
        <div className="grid gap-3">
          {CHANNEL_CARDS.slice(3).map((c, i) => (
            <ChannelCard key={c.name} {...c} delay={0.2 + i * 0.06} />
          ))}
        </div>
      </div>
    </section>
  );
}

function ChannelCard({ icon: Icon, name, note, c, delay }: { icon: any; name: string; note: string; c: string; delay: number }) {
  return (
    <motion.div {...fade} transition={{ duration: 0.5, delay }} className="flex items-center gap-3 rounded-2xl border bg-card p-4 shadow-sm">
      <span className={cn("grid size-10 place-items-center rounded-xl bg-muted", c)}>
        <Icon className="size-5" />
      </span>
      <div className="flex-1">
        <p className="text-sm font-medium">{name}</p>
        <p className="text-xs text-muted-foreground">{note}</p>
      </div>
      <span className="relative inline-flex h-5 w-9 items-center rounded-full bg-brand px-0.5">
        <span className="ml-auto size-4 rounded-full bg-white shadow" />
      </span>
    </motion.div>
  );
}

const STORY = [
  { time: "2:04 PM", channel: "Website chat", icon: Globe, c: "text-ch-web", who: "Rahul", text: "Do you do root canals? How much?", ai: "Yes. Root canals are ₹6,000 to ₹9,000 depending on the tooth, done by Dr. Vikram Shetty. Want to book?" },
  { time: "4:11 PM", channel: "Phone call", icon: Phone, c: "text-ch-phone", who: "Rahul", text: "Hi, I was asking about a root canal earlier…", ai: "Welcome back, Rahul! Dr. Vikram has a slot Thursday at 11. Shall I book it and send the details to your WhatsApp?" },
  { time: "4:12 PM", channel: "WhatsApp", icon: MessageCircle, c: "text-ch-whatsapp", who: "Agent", text: "", ai: "✅ Booked: Thu 11:00 AM with Dr. Vikram Shetty. Reply RESCHEDULE anytime." },
];

export function MemoryStory() {
  return (
    <section id="memory" className="border-y bg-muted/20 py-24">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 lg:grid-cols-2">
        <motion.div {...fade}>
          <Eyebrow>Cross-channel memory</Eyebrow>
          <h2 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">It remembers people, not channels.</h2>
          <p className="mt-4 text-muted-foreground">
            A phone number, WhatsApp ID, email and website visit all resolve to one person. The agent recalls what they asked on any
            channel, what was promised, and what&apos;s still open, then acts across channels. It can call you and text you the link.
          </p>
          <ul className="mt-6 space-y-3 text-sm">
            {[
              [UserRoundCheck, "Identity resolution across phone, WhatsApp, Telegram, email and web sessions (with safe merging)"],
              [Brain, "Durable facts with validity windows, so a corrected fact replaces the old one instead of piling up"],
              [Users, "Every conversation, call and recording on one CRM timeline"],
            ].map(([Icon, t]: any) => (
              <li key={t} className="flex gap-3">
                <Icon className="mt-0.5 size-4 shrink-0 text-brand" /> <span className="text-muted-foreground">{t}</span>
              </li>
            ))}
          </ul>
        </motion.div>
        <div className="relative space-y-4">
          <div className="absolute left-[22px] top-6 bottom-6 w-px bg-gradient-to-b from-brand/50 via-border to-transparent" />
          {STORY.map((s, i) => (
            <motion.div key={s.time} {...fade} transition={{ duration: 0.5, delay: i * 0.15 }} className="relative flex gap-4">
              <span className={cn("relative z-10 grid size-11 shrink-0 place-items-center rounded-full border bg-background shadow-sm", s.c)}>
                <s.icon className="size-5" />
              </span>
              <div className="flex-1 rounded-2xl border bg-card p-4 shadow-sm">
                <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{s.channel}</span>
                  <span>{s.time}</span>
                </div>
                {s.text && <p className="mb-2 text-sm text-muted-foreground">“{s.text}”</p>}
                <p className="rounded-xl bg-brand-soft/70 px-3 py-2 text-sm">{s.ai}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function GlassBox() {
  const chunks = [
    { t: "Patient info › Treatments and prices", s: 0.71, b: 8.4, p: "×1.0" },
    { t: "Patient info › Doctors", s: 0.58, b: 5.1, p: "×1.0" },
    { t: "Old price list (2023)", s: 0.55, b: 4.9, p: "×0.05 restrict" },
  ];
  return (
    <section id="glass-box" className="mx-auto max-w-6xl px-5 py-24">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <motion.div {...fade} className="order-2 rounded-2xl border bg-card p-5 shadow-xl lg:order-1">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">Why did the agent say that?</p>
            <Badge variant="secondary" className="bg-success/15 text-success">confidence 0.71</Badge>
          </div>
          <p className="mt-3 rounded-lg bg-muted px-3 py-2 text-sm">“How much is a root canal?”</p>
          <div className="mt-4 space-y-2">
            {chunks.map((c) => (
              <div key={c.t} className={cn("rounded-lg border p-3", c.p.includes("restrict") && "opacity-50")}>
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-medium">{c.t}</span>
                  <span className={cn("font-mono", c.p.includes("restrict") ? "text-destructive" : "text-muted-foreground")}>{c.p}</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-[11px] text-muted-foreground">
                  <span>dense {c.s.toFixed(2)}</span>
                  <span>bm25 {c.b.toFixed(1)}</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${c.s * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-1.5 text-[11px]">
            {["safety", "business", "persona", "language", "channel: voice", "memory", "knowledge", "escalation"].map((s) => (
              <span key={s} className="rounded-md border px-2 py-0.5 font-mono text-muted-foreground">{s}</span>
            ))}
          </div>
        </motion.div>
        <motion.div {...fade} className="order-1 lg:order-2">
          <Eyebrow>Glass-box RAG</Eyebrow>
          <h2 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">No black boxes. See exactly why it answered.</h2>
          <p className="mt-4 text-muted-foreground">
            Every reply carries its sources, retrieval scores, policy multipliers, prompt sections, tool calls, latency and cost. Hybrid
            semantic + keyword search, multilingual reranking, approved answers and spreadsheet-to-SQL make answers accurate. When it
            isn&apos;t sure, it says so and offers a human.
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
            {[["Citations", "on every web answer"], ["Policy rules", "restrict / require / allow"], ["Sheets → SQL", "orders, prices, stock"], ["Red-team evals", "injection-tested"]].map(([a, b]) => (
              <div key={a} className="rounded-xl border p-3">
                <p className="font-medium">{a}</p>
                <p className="text-xs text-muted-foreground">{b}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}

const BENTO = [
  { icon: Mic, title: "Natural, interruptible voice", text: "Smart turn detection, barge-in, 320+ neural voices in 25+ languages that switch automatically with the caller's language.", span: "lg:col-span-2" },
  { icon: Headphones, title: "Human handoff that feels smooth", text: "AI-written briefs, instant alerts, live takeover from the browser, AI copilot replies." },
  { icon: Users, title: "A CRM that fills itself", text: "Contacts, deals, tasks and bookings updated from every conversation, with an undoable AI trail." },
  { icon: Workflow, title: "Automations & campaigns", text: "Trigger → steps workflows, batch calls with calling windows, DND and retries, WhatsApp broadcasts.", span: "lg:col-span-2" },
  { icon: FlaskConical, title: "Evals before you ship", text: "Faithfulness, relevancy and context scores, AI caller simulations and red-team suites per agent." },
  { icon: KeyRound, title: "Bring your own keys", text: "Groq, Gemini, OpenAI, Claude, OpenRouter, Deepgram, Cartesia and more. We never mark up tokens." },
  { icon: PlugZap, title: "MCP in & out", text: "Give agents any MCP tool, and let Claude or Cursor operate your workspace." },
  { icon: Radar, title: "Live monitor", text: "Listen to transcripts live, whisper instructions to the AI, or take over the call." },
  { icon: ShieldCheck, title: "Secure by design", text: "Encrypted keys, prompt-injection guard, PII redaction, tenant isolation, audit log." },
];

export function Bento() {
  return (
    <section className="border-y bg-muted/20 py-24">
      <div className="mx-auto max-w-6xl px-5">
        <motion.div {...fade} className="max-w-2xl">
          <Eyebrow>Everything in one place</Eyebrow>
          <h2 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">Voice AI, chat AI and CRM. Finally one product.</h2>
        </motion.div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {BENTO.map((b, i) => (
            <motion.div key={b.title} {...fade} transition={{ duration: 0.5, delay: (i % 4) * 0.05 }} className={cn("rounded-2xl border bg-card p-5 shadow-sm transition hover:shadow-md", b.span)}>
              <b.icon className="size-5 text-brand" />
              <p className="mt-4 font-medium">{b.title}</p>
              <p className="mt-1.5 text-sm text-muted-foreground">{b.text}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

const ROWS: [string, (boolean | string)[]][] = [
  ["Voice calls (phone + browser)", [true, true, true, true, "add-on"]],
  ["WhatsApp + Telegram + web chat + widget", [true, false, false, "partial", true]],
  ["One agent across all channels", [true, false, false, false, "partial"]],
  ["Cross-channel memory per person", [true, false, false, false, false]],
  ["Glass-box answer diagnostics", [true, false, false, false, false]],
  ["Built-in CRM, calendar & automations", [true, false, false, false, true]],
  ["Indian languages & Hinglish", [true, "partial", "partial", true, "partial"]],
  ["Bring your own keys, no token markup", [true, true, false, "partial", false]],
  ["Evals + red-team before deploy", [true, "partial", "partial", false, false]],
  ["Free plan", [true, "credits", "credits", "trial", false]],
];

export function Compare() {
  const cols = ["Unisona", "Vapi", "Retell", "Bolna", "GoHighLevel"];
  return (
    <section id="compare" className="mx-auto max-w-6xl px-5 py-24">
      <motion.div {...fade} className="mx-auto max-w-2xl text-center">
        <Eyebrow>How we compare</Eyebrow>
        <h2 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">Built to replace the stack, not join it.</h2>
      </motion.div>
      <motion.div {...fade} className="mt-10 overflow-x-auto rounded-2xl border bg-card">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Capability</th>
              {cols.map((c, i) => (
                <th key={c} className={cn("px-4 py-3 font-semibold", i === 0 && "bg-brand-soft/60 text-brand")}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([label, vals]) => (
              <tr key={label} className="border-b last:border-0">
                <td className="px-4 py-3">{label}</td>
                {vals.map((v, i) => (
                  <td key={i} className={cn("px-4 py-3 text-center", i === 0 && "bg-brand-soft/40")}>
                    {v === true ? <Check className="mx-auto size-4 text-success" /> : v === false ? <X className="mx-auto size-4 text-muted-foreground/50" /> : <span className="text-xs text-muted-foreground">{v}</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </motion.div>
      <p className="mt-3 text-center text-xs text-muted-foreground">Based on public product pages, October 2026.</p>
    </section>
  );
}

const PLANS = [
  { id: "free", name: "Free", inr: 0, usd: 0, desc: "Try it on your own site.", feats: ["1 agent", "Web chat, widget & browser voice", "60 voice min / mo", "Glass-box RAG"], cta: "Start free" },
  { id: "starter", name: "Starter", inr: 1499, usd: 19, desc: "For small businesses.", feats: ["3 agents", "All channels incl. WhatsApp & phone", "1,000 voice min", "Cross-channel memory & CRM"], cta: "Start trial" },
  { id: "growth", name: "Growth", inr: 4999, usd: 59, desc: "For growing teams.", feats: ["10 agents", "5,000 voice min", "Campaigns & automations", "Evals, live monitor, no branding"], cta: "Start trial", popular: true },
  { id: "scale", name: "Scale", inr: 14999, usd: 179, desc: "High volume & agencies.", feats: ["Unlimited agents", "20,000 voice min", "Client sub-accounts", "Priority support"], cta: "Start trial" },
];

export function Pricing() {
  const [cur, setCur] = useState<"inr" | "usd">("inr");
  return (
    <section id="pricing" className="border-y bg-muted/20 py-24">
      <div className="mx-auto max-w-6xl px-5">
        <motion.div {...fade} className="mx-auto max-w-2xl text-center">
          <Eyebrow>Pricing</Eyebrow>
          <h2 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">Unlimited channels on every plan.</h2>
          <p className="mt-4 text-muted-foreground">
            You bring your own AI keys and pay providers directly at cost. We charge for the platform, and overage is just ₹0.80 ($0.012) per voice minute.
          </p>
          <div className="mt-6 inline-flex rounded-full border bg-background p-1 text-sm">
            {(["inr", "usd"] as const).map((c) => (
              <button key={c} onClick={() => setCur(c)} className={cn("rounded-full px-4 py-1.5 transition", cur === c ? "bg-foreground text-background" : "text-muted-foreground")}>
                {c === "inr" ? "₹ INR" : "$ USD"}
              </button>
            ))}
          </div>
        </motion.div>
        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((p) => (
            <motion.div key={p.id} {...fade} className={cn("relative flex flex-col rounded-2xl border bg-card p-6 shadow-sm", p.popular && "glow-border shadow-xl")}>
              {p.popular && <Badge className="absolute -top-2.5 left-6 bg-brand text-brand-foreground">Most popular</Badge>}
              <p className="font-semibold">{p.name}</p>
              <p className="text-xs text-muted-foreground">{p.desc}</p>
              <p className="mt-5 text-4xl font-semibold tracking-tight">
                {cur === "inr" ? `₹${p.inr.toLocaleString("en-IN")}` : `$${p.usd}`}
                <span className="text-sm font-normal text-muted-foreground">/mo</span>
              </p>
              <ul className="mt-5 flex-1 space-y-2 text-sm">
                {p.feats.map((f) => (
                  <li key={f} className="flex gap-2">
                    <Check className="mt-0.5 size-4 shrink-0 text-brand" /> {f}
                  </li>
                ))}
              </ul>
              <Button asChild className={cn("mt-6", p.popular ? "bg-brand text-brand-foreground hover:bg-brand/90" : "")} variant={p.popular ? "default" : "outline"}>
                <Link href="/sign-up">{p.cta}</Link>
              </Button>
            </motion.div>
          ))}
        </div>
        <div className="mt-6 flex flex-col items-center justify-between gap-3 rounded-2xl border bg-card p-5 text-sm sm:flex-row">
          <p>
            <span className="font-medium">Agency ₹24,999 · $297/mo</span> <span className="text-muted-foreground">: white-label, unlimited client workspaces, rebilling.</span>{" "}
            <span className="font-medium">Enterprise</span> <span className="text-muted-foreground">: SSO, on-prem, data residency, SLA.</span>
          </p>
          <Button asChild variant="outline" size="sm">
            <a href="mailto:hello@unisona.si">Talk to us</a>
          </Button>
        </div>
      </div>
    </section>
  );
}

const USE_CASES = [
  [Headphones, "Customer support"], [Phone, "AI receptionist"], [CircleDollarSign, "Lead qualification"], [LineChart, "Outbound sales"],
  [Calendar, "Appointment reminders"], [BadgeCheck, "COD confirmation"], [Bot, "Order status"], [Sparkles, "Customer onboarding"],
  [ShieldCheck, "Payment reminders"], [Users, "Recruitment screening"], [Globe, "Real estate"], [Mic, "Surveys & NPS"],
] as const;

export function UseCases() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-24">
      <motion.div {...fade} className="mx-auto max-w-2xl text-center">
        <Eyebrow>Templates for any job</Eyebrow>
        <h2 className="mt-3 font-display text-4xl tracking-tight sm:text-5xl">From a clinic front desk to a 10,000-call campaign.</h2>
      </motion.div>
      <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {USE_CASES.map(([Icon, label]) => (
          <motion.div key={label} {...fade} className="flex items-center gap-3 rounded-xl border bg-card p-4 text-sm font-medium">
            <Icon className="size-4 text-brand" /> {label}
          </motion.div>
        ))}
      </div>
    </section>
  );
}

const FAQ = [
  ["Do I need to bring my own API keys?", "You can start with our free trial credits. For production you add your own keys (e.g. a free Groq key) in Settings → Providers. We validate them instantly and never mark up provider costs."],
  ["Which languages are supported?", "25+ languages with natural neural voices, including Hindi, Hinglish, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam and Urdu. The agent replies in the customer's language and switches voice automatically."],
  ["Can a human take over?", "Yes. The agent hands off on request, on frustration, or when it isn't confident. Your team gets an instant alert with an AI-written brief and can reply from the unified inbox or take over a live call."],
  ["Is my data safe?", "Workspace data is isolated, API keys are envelope-encrypted, every input passes a prompt-injection guard, and PII redaction is one switch. Enterprise plans support on-prem and data residency."],
  ["Can I use it with my existing tools?", "Yes. Use webhooks, Zapier, Make or n8n, connect any HTTP API or MCP server as an agent tool, or use our REST API and MCP server."],
];

export function Faq() {
  return (
    <section className="mx-auto max-w-3xl px-5 py-24">
      <h2 className="text-center font-display text-4xl tracking-tight">Questions, answered.</h2>
      <div className="mt-10 divide-y rounded-2xl border bg-card">
        {FAQ.map(([q, a]) => (
          <details key={q} className="group p-5">
            <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
              {q}
              <ArrowRight className="size-4 text-muted-foreground transition group-open:rotate-90" />
            </summary>
            <p className="mt-3 text-sm text-muted-foreground">{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

export function CtaFooter() {
  return (
    <>
      <section className="px-5 pb-24">
        <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl border bg-foreground px-8 py-16 text-center text-background">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--brand)_45%,transparent),transparent_60%)]" />
          <div className="relative">
            <h2 className="font-display text-4xl tracking-tight sm:text-5xl">Your agent can be live in 20 minutes.</h2>
            <p className="mx-auto mt-4 max-w-xl text-background/70">Paste your website. We read it, draft your agent, and you can be talking to it before your coffee gets cold.</p>
            <Button asChild size="lg" className="mt-8 h-11 bg-brand px-7 text-brand-foreground hover:bg-brand/90">
              <Link href="/sign-up">
                Build your agent <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>
      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 py-8 text-sm text-muted-foreground sm:flex-row">
          <Logo />
          <p>© {new Date().getFullYear()} Unisona. One brain, many voices.</p>
          <div className="flex gap-4">
            <a href="#pricing" className="hover:text-foreground">Pricing</a>
            <a href="#compare" className="hover:text-foreground">Compare</a>
            <Link href="/sign-in" className="hover:text-foreground">Sign in</Link>
          </div>
        </div>
      </footer>
    </>
  );
}
