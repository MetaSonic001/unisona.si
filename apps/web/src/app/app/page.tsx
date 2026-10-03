"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Bot, CheckCircle2, Circle, Clock, Handshake, KeyRound, MessagesSquare, PhoneCall, Smile, Sparkles, Users } from "lucide-react";
import Link from "next/link";
import { ChannelDot, EmptyState, StatCard, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/lib/api";
import { pct, timeAgo } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

export default function HomePage() {
  const api = useApi();
  const { me } = useWorkspace();
  const { data: ov } = useQuery({ queryKey: ["analytics", 7], queryFn: () => api.get("/analytics/overview?days=7") });
  const { data: pending } = useQuery({ queryKey: ["conversations", "handoff_pending"], queryFn: () => api.get("/conversations?status=handoff_pending&limit=6") });
  const { data: recent } = useQuery({ queryKey: ["conversations", "recent"], queryFn: () => api.get("/conversations?limit=8") });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const k = ov?.kpis;
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const firstName = (me?.user.name || "").split(" ")[0];

  const checklist = [
    { done: !!me?.ai_ready, label: "Connect an AI provider (free Groq key works)", href: "/app/settings?tab=providers" },
    { done: (me?.counts.agents || 0) > 0, label: "Create your first agent", href: "/app/onboarding" },
    { done: (me?.counts.sources || 0) > 0, label: "Add knowledge: website, PDFs, sheets", href: "/app/knowledge" },
    { done: (agents?.items || []).some((a: any) => a.channels?.some((c: any) => ["whatsapp", "telegram", "phone"].includes(c.type))), label: "Connect WhatsApp, Telegram or a phone number", href: (agents?.items?.[0] ? `/app/agents/${agents.items[0].id}?tab=channels` : "/app/agents") },
    { done: (me?.counts.conversations || 0) > 0, label: "Have your first conversation", href: agents?.items?.[0] ? `/app/agents/${agents.items[0].id}?tab=playground` : "/app/agents" },
  ];

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm text-muted-foreground">{me?.workspace.name}</p>
          <h1 className="font-display text-4xl tracking-tight">
            {greet}
            {firstName ? `, ${firstName}` : ""}.
          </h1>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href="/app/inbox">
              <MessagesSquare className="size-4" /> Open inbox
            </Link>
          </Button>
          <Button asChild className="bg-brand text-brand-foreground hover:bg-brand/90">
            <Link href="/app/agents?new=1">
              <Sparkles className="size-4" /> New agent
            </Link>
          </Button>
        </div>
      </div>

      {me && !me.ai_ready && (
        <Card className="flex-row items-center gap-4 border-warning/40 bg-warning/5 p-4">
          <KeyRound className="size-5 text-warning" />
          <div className="flex-1 text-sm">
            <p className="font-medium">Your agents need an AI key to talk.</p>
            <p className="text-muted-foreground">Add a free Groq key (or Gemini, OpenAI, Claude…). It takes 30 seconds and is validated instantly.</p>
          </div>
          <Button asChild size="sm">
            <Link href="/app/settings?tab=providers">Add key</Link>
          </Button>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard label="Conversations (7d)" value={k?.conversations ?? "—"} icon={MessagesSquare} hint={k ? `${k.ai_messages} AI replies` : undefined} />
        <StatCard label="Resolved by AI" value={pct(k?.containment_rate)} icon={Bot} hint="containment rate" />
        <StatCard label="Handed to humans" value={k?.handoffs ?? "—"} icon={Handshake} hint={k ? `${pct(k.handoff_rate)} of conversations` : undefined} />
        <StatCard label="Call minutes" value={k?.call_minutes ?? "—"} icon={PhoneCall} hint={k ? `${k.calls} calls` : undefined} />
        <StatCard label="Avg reply" value={k?.avg_response_ms ? `${(k.avg_response_ms / 1000).toFixed(1)}s` : "—"} icon={Clock} hint={k?.csat ? `CSAT ${k.csat}/5` : "CSAT after analysis"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-sm">
              <AlertTriangle className="size-4 text-warning" /> Waiting for a human
            </CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link href="/app/inbox?status=handoff_pending">
                View all <ArrowRight className="size-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {(pending?.items || []).length === 0 ? (
              <p className="flex items-center gap-2 rounded-lg bg-success/10 px-3 py-3 text-sm text-success">
                <Smile className="size-4" /> No one is waiting. Your agents have it handled.
              </p>
            ) : (
              pending.items.map((c: any) => (
                <Link key={c.id} href={`/app/inbox?c=${c.id}`} className="flex items-center gap-3 rounded-lg border p-3 transition hover:bg-muted/50">
                  <ChannelDot channel={c.channel} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{c.contact?.name || c.contact?.phone || "Visitor"} · {c.subject}</p>
                    <p className="truncate text-xs text-muted-foreground">{c.last_message?.content}</p>
                  </div>
                  <span className="text-xs text-muted-foreground">{timeAgo(c.last_message_at)}</span>
                </Link>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Get set up</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {checklist.map((c) => (
              <Link key={c.label} href={c.href} className="flex items-center gap-2.5 rounded-lg px-2 py-2 text-sm transition hover:bg-muted/60">
                {c.done ? <CheckCircle2 className="size-4 text-success" /> : <Circle className="size-4 text-muted-foreground" />}
                <span className={c.done ? "text-muted-foreground line-through" : ""}>{c.label}</span>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm">Recent conversations</CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link href="/app/inbox">
                Inbox <ArrowRight className="size-3.5" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {(recent?.items || []).length === 0 ? (
              <EmptyState icon={MessagesSquare} title="No conversations yet" description="Talk to an agent in its Playground, embed the widget, or connect a channel." />
            ) : (
              <div className="divide-y">
                {recent.items.map((c: any) => (
                  <Link key={c.id} href={`/app/inbox?c=${c.id}`} className="flex items-center gap-3 py-2.5 transition hover:bg-muted/30">
                    <ChannelDot channel={c.channel} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">
                        <span className="font-medium">{c.contact?.name || c.contact?.phone || "Visitor"}</span>
                        <span className="text-muted-foreground"> · {c.agent_name}</span>
                      </p>
                      <p className="truncate text-xs text-muted-foreground">{c.summary || c.last_message?.content}</p>
                    </div>
                    <StatusBadge status={c.status} />
                    <span className="w-20 text-right text-xs text-muted-foreground">{timeAgo(c.last_message_at)}</span>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm">Your agents</CardTitle>
            <Users className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-2">
            {(agents?.items || []).slice(0, 6).map((a: any) => (
              <Link key={a.id} href={`/app/agents/${a.id}`} className="flex items-center gap-3 rounded-lg border p-2.5 transition hover:bg-muted/50">
                <span className="grid size-8 place-items-center rounded-lg bg-brand-soft text-sm font-semibold text-brand">{a.name[0]}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{a.name}</p>
                  <p className="text-xs text-muted-foreground">{a.conversations} conversations</p>
                </div>
                <StatusBadge status={a.status} />
              </Link>
            ))}
            {(agents?.items || []).length === 0 && <p className="text-sm text-muted-foreground">No agents yet.</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
