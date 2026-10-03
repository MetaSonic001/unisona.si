"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FlaskConical, MessageCircle, Phone, PlayCircle, RotateCcw, Send, Sparkles, Timer } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/agent/fields";
import { ChannelBadge, PageHeader, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";

export default function DevPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { me, refetch } = useWorkspace();
  const { data: status, refetch: refetchStatus } = useQuery({ queryKey: ["dev-status"], queryFn: () => api.get("/dev/status"), refetchInterval: 5000, enabled: !!me?.dev_mode });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const [sim, setSim] = useState({ agent_id: "", channel: "whatsapp", from: "+919876500001", name: "Rahul Verma", text: "" });
  const [log, setLog] = useState<{ channel: string; text: string; reply: string; conv: string }[]>([]);
  const seed = useMutation({ mutationFn: () => api.post("/dev/seed-demo"), onSuccess: (r) => { toast.success(r.created ? "Demo agents created. Knowledge is indexing." : "Demo already exists"); qc.invalidateQueries({ queryKey: ["agents"] }); refetch(); } });
  const reset = useMutation({ mutationFn: () => api.post("/dev/reset-onboarding"), onSuccess: () => { refetch(); toast.success("Onboarding reset. Open /app/onboarding."); } });
  const tick = useMutation({ mutationFn: () => api.post("/dev/tick"), onSuccess: (r) => toast.success(`Scheduler tick: ${r.campaign_targets_moved} campaign targets moved, improve loop queued`) });
  const evals = useMutation({ mutationFn: (agent_id: string) => api.post("/dev/run-evals", { agent_id }), onSuccess: (r) => toast.success(`${r.runs.length} evaluation runs queued. See Evaluations.`) });
  const send = useMutation({
    mutationFn: () => api.post("/dev/simulate", { ...sim, agent_id: sim.agent_id || agents?.items?.[0]?.id }),
    onSuccess: (r) => { setLog((l) => [...l, { channel: sim.channel, text: sim.text, reply: r.text, conv: r.conversation_id }]); setSim({ ...sim, text: "" }); },
    onError: (e: Error) => toast.error(e.message),
  });
  if (me && !me.dev_mode) return <p className="p-10 text-center text-muted-foreground">Dev mode is disabled. Set DEV_MODE=true in .env (local only).</p>;

  return (
    <div>
      <PageHeader icon={FlaskConical} title="Dev mode" description="Local-only tools to exercise every feature without real WhatsApp, Telegram or phone accounts." />
      <div className="grid gap-6 p-6 xl:grid-cols-[1fr_420px]">
        <div className="space-y-6">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Card className="gap-2 p-4"><Sparkles className="size-4 text-brand" /><p className="text-sm font-medium">Seed demo data</p><p className="text-xs text-muted-foreground">Dental clinic + e-commerce agents, docs, orders table, eval suites.</p><Button size="sm" onClick={() => seed.mutate()} disabled={seed.isPending}>Seed</Button></Card>
            <Card className="gap-2 p-4"><RotateCcw className="size-4 text-brand" /><p className="text-sm font-medium">Replay onboarding</p><p className="text-xs text-muted-foreground">Reset the wizard state for this workspace.</p><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => reset.mutate()}>Reset</Button><Button size="sm" variant="ghost" asChild><Link href="/app/onboarding">Open</Link></Button></div></Card>
            <Card className="gap-2 p-4"><Timer className="size-4 text-brand" /><p className="text-sm font-medium">Run scheduler now</p><p className="text-xs text-muted-foreground">Campaign tick + nightly improve loop immediately.</p><Button size="sm" variant="outline" onClick={() => tick.mutate()}>Tick</Button></Card>
            <Card className="gap-2 p-4"><PlayCircle className="size-4 text-brand" /><p className="text-sm font-medium">Run all evals</p><p className="text-xs text-muted-foreground">QA + red-team + simulations for an agent.</p>
              <Select onValueChange={(v) => evals.mutate(v)}><SelectTrigger className="h-8"><SelectValue placeholder="Pick agent" /></SelectTrigger><SelectContent>{(agents?.items || []).map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent></Select>
            </Card>
          </div>

          <Card className="gap-4 p-5">
            <div>
              <p className="font-semibold">Channel simulator</p>
              <p className="text-xs text-muted-foreground">Message an agent as a customer on any channel. Use the same phone number across channels to watch cross-channel memory kick in (then check the Inbox and the contact&apos;s timeline).</p>
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <Field label="Agent"><Select value={sim.agent_id || agents?.items?.[0]?.id || ""} onValueChange={(v) => setSim({ ...sim, agent_id: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(agents?.items || []).map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent></Select></Field>
              <Field label="Channel"><Select value={sim.channel} onValueChange={(v) => setSim({ ...sim, channel: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["whatsapp", "telegram", "phone", "web", "email"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></Field>
              <Field label="From (phone / id / email)"><Input value={sim.from} onChange={(e) => setSim({ ...sim, from: e.target.value })} /></Field>
              <Field label="Name"><Input value={sim.name} onChange={(e) => setSim({ ...sim, name: e.target.value })} /></Field>
            </div>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (sim.text) send.mutate(); }}>
              <Input placeholder="Customer message…" value={sim.text} onChange={(e) => setSim({ ...sim, text: e.target.value })} />
              <Button type="submit" disabled={send.isPending || !sim.text}><Send className="size-4" /> Send</Button>
            </form>
            <div className="space-y-2">
              {log.map((l, i) => (
                <div key={i} className="rounded-lg border p-3 text-sm">
                  <div className="mb-1 flex items-center gap-2"><ChannelBadge channel={l.channel === "phone" ? "voice" : l.channel} /><Link href={`/app/inbox?c=${l.conv}`} className="text-xs text-brand hover:underline">open in inbox</Link></div>
                  <p><b>Customer:</b> {l.text}</p>
                  <p className="mt-1 text-muted-foreground"><b className="text-foreground">Agent:</b> {l.reply}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="gap-2 p-4">
            <div className="flex items-center justify-between"><p className="flex items-center gap-2 text-sm font-semibold"><Database className="size-4" /> System</p><Button size="sm" variant="ghost" onClick={() => refetchStatus()}>Refresh</Button></div>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-md bg-muted/50 p-2"><p className="text-lg font-semibold">{status?.active_calls ?? 0}</p>live calls</div>
              <div className="rounded-md bg-muted/50 p-2"><p className="text-lg font-semibold">{status?.telegram_pollers ?? 0}</p>TG bots</div>
              <div className="rounded-md bg-muted/50 p-2"><p className="text-lg font-semibold">{status?.realtime_listeners ?? 0}</p>sockets</div>
            </div>
            <p className="text-xs text-muted-foreground">Jobs: {Object.entries(status?.jobs || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
          </Card>
          <Card className="gap-1.5 p-4">
            <p className="mb-1 text-sm font-semibold">Features (from .env)</p>
            {(status?.features || []).map((f: any) => (
              <div key={f.name} className="flex items-center justify-between gap-2 text-xs">
                <span className={f.enabled ? "" : "text-muted-foreground"}>{f.name}</span>
                {f.enabled ? <Badge className="bg-success/15 text-success">on</Badge> : <Badge variant="outline" title={f.env}>off · {f.env.split(" ")[0]}</Badge>}
              </div>
            ))}
          </Card>
          <Card className="gap-1.5 p-4">
            <p className="mb-1 text-sm font-semibold">Recent jobs</p>
            {(status?.recent_jobs || []).map((j: any) => (
              <div key={j.id} className="flex items-center gap-2 text-xs">
                <span className="flex-1 truncate font-mono">{j.type}</span><StatusBadge status={j.status} /><span className="w-16 text-right text-muted-foreground">{timeAgo(j.created_at).replace(" ago", "")}</span>
              </div>
            ))}
          </Card>
          <Card className="gap-1 p-4 text-xs text-muted-foreground">
            <p className="flex items-center gap-1.5 font-semibold text-foreground"><Phone className="size-3.5" /> Testing phone calls locally</p>
            <p>Run <code>ngrok http 8000</code>, set PUBLIC_WEBHOOK_URL, connect a Twilio/Exotel number on an agent&apos;s Channels tab and point the number&apos;s voice webhook at the URL shown there.</p>
            <p className="mt-2 flex items-center gap-1.5 font-semibold text-foreground"><MessageCircle className="size-3.5" /> Telegram works locally</p>
            <p>Paste a BotFather token on an agent&apos;s Channels tab. It long-polls, so no public URL is needed.</p>
          </Card>
        </div>
      </div>
    </div>
  );
}
