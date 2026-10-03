"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ear, GitBranch, Hand, MessageSquareWarning, PhoneForwarded, PhoneOff, Radio, Volume2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ChannelBadge, ChannelDot, EmptyState, PageHeader, StatusBadge } from "@/components/common";
import { VoiceOrb } from "@/components/orb";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";
import { duration, timeAgo } from "@/lib/format";
import { useRealtime } from "@/lib/workspace";

export default function LivePage() {
  const api = useApi();
  const qc = useQueryClient();
  const [transcripts, setTranscripts] = useState<Record<string, { role: string; text: string }[]>>({});
  const [emotions, setEmotions] = useState<Record<string, { label: string; intensity: number }>>({});
  const [capacity, setCapacity] = useState<any>(null);
  const { data: live } = useQuery({ queryKey: ["live"], queryFn: () => api.get("/calls/live"), refetchInterval: 5000 });
  const { data: waiting } = useQuery({ queryKey: ["conversations", "live-waiting"], queryFn: () => api.get("/conversations?status=handoff_pending&limit=20"), refetchInterval: 15000 });
  const { data: active } = useQuery({ queryKey: ["conversations", "live-active"], queryFn: () => api.get("/conversations?status=open&limit=30"), refetchInterval: 15000 });
  useRealtime((ev) => {
    if (ev.type === "call.transcript") setTranscripts((t) => ({ ...t, [ev.call_id]: [...(t[ev.call_id] || []), { role: ev.role, text: ev.text }].slice(-40) }));
    if (ev.type === "call.started" || ev.type === "call.ended" || ev.type === "call.transferred" || ev.type === "call.agent_switched") qc.invalidateQueries({ queryKey: ["live"] });
    if (ev.type === "call.emotion") setEmotions((e) => ({ ...e, [ev.call_id]: { label: ev.label, intensity: ev.intensity } }));
    if (ev.type === "call.transferred") toast.success(`Call transferred to ${ev.to}`);
  });
  const calls = live?.items || [];
  const { data: cap } = useQuery({ queryKey: ["capacity"], queryFn: () => api.get("/calls/capacity"), refetchInterval: 10000 });
  const recentChats = (active?.items || []).filter((c: any) => Date.now() - new Date(c.last_message_at).getTime() < 15 * 60 * 1000 && !["voice", "phone"].includes(c.channel));

  return (
    <div>
      <PageHeader icon={Radio} title="Live" description="Every live call and chat right now. Listen in, coach the AI silently, or take over." />
      <div className="grid gap-6 p-6 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <p className="text-sm font-semibold">Live calls ({calls.length}{cap ? ` of ${cap.limit} lines` : ""})</p>
          {calls.length === 0 && <EmptyState icon={Radio} title="No calls right now" description="Browser and phone calls appear here the moment they start." />}
          <div className="grid gap-4 lg:grid-cols-2">
            {calls.map((c: any) => <CallCard key={c.call_id} call={c} emotion={emotions[c.call_id] || c.emotion} lines={transcripts[c.call_id] || c.transcript || []} />)}
          </div>
          <p className="pt-2 text-sm font-semibold">Active chats (last 15 min)</p>
          {recentChats.length === 0 && <p className="text-sm text-muted-foreground">No active chats.</p>}
          <div className="grid gap-2 lg:grid-cols-2">
            {recentChats.map((c: any) => (
              <Link key={c.id} href={`/app/inbox?c=${c.id}`} className="flex items-center gap-3 rounded-lg border bg-card p-3 hover:bg-muted/40">
                <ChannelDot channel={c.channel} />
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{c.contact?.name || "Visitor"} · {c.agent_name}</p><p className="truncate text-xs text-muted-foreground">{c.last_message?.content}</p></div>
                <StatusBadge status={c.status} />
              </Link>
            ))}
          </div>
        </div>
        <Card className="h-fit gap-3 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold"><MessageSquareWarning className="size-4 text-warning" /> Waiting for a human ({waiting?.items?.length || 0})</p>
          {(waiting?.items || []).map((c: any) => (
            <Link key={c.id} href={`/app/inbox?c=${c.id}`} className="block rounded-lg border p-3 hover:bg-muted/40">
              <div className="flex items-center justify-between"><ChannelBadge channel={c.channel} /><span className="text-xs text-muted-foreground">{timeAgo(c.last_message_at)}</span></div>
              <p className="mt-1 text-sm font-medium">{c.contact?.name || c.contact?.phone || "Visitor"}</p>
              <p className="line-clamp-2 text-xs text-muted-foreground">{c.last_message?.content}</p>
            </Link>
          ))}
          {(waiting?.items || []).length === 0 && <p className="text-sm text-muted-foreground">Nobody is waiting.</p>}
        </Card>
      </div>
    </div>
  );
}

const EMO: Record<string, string> = { angry: "😠 angry", frustrated: "😣 frustrated", confused: "🤔 confused", happy: "😊 happy", neutral: "😐 calm" };

function CallCard({ call, lines, emotion }: { call: any; lines: { role: string; text: string }[]; emotion?: { label: string; intensity: number } | null }) {
  const api = useApi();
  const [msg, setMsg] = useState("");
  const transfer = useMutation({
    mutationFn: () => {
      const to = prompt("Transfer to which number? (e.g. +9198…)");
      if (!to) throw new Error("cancelled");
      return api.post(`/calls/live/${call.call_id}/transfer`, { to, mode: "warm" });
    },
    onSuccess: (r) => toast.success(r.result === "transferred" ? "Transferring with an AI brief…" : "Team alerted to take over"),
    onError: (e: Error) => e.message !== "cancelled" && toast.error(e.message),
  });
  const act = useMutation({
    mutationFn: ({ action, text }: { action: string; text?: string }) => api.post(`/calls/${call.call_id}/${action}`, { text }),
    onSuccess: (_, v) => { setMsg(""); toast.success({ whisper: "Instruction sent to the AI (caller can't hear it)", takeover: "You're on the call. Type to speak.", say: "Spoken to caller", release: "AI is back in control", end: "Call ending" }[v.action] || "Done"); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Card className="gap-3 p-4">
      <div className="flex items-center gap-3">
        <VoiceOrb state="speaking" level={0.3} size={44} />
        <div className="flex-1">
          <p className="text-sm font-medium">{call.channel === "phone" ? "Phone call" : "Browser call"} · {duration(call.duration_s)}</p>
          <p className="text-xs text-muted-foreground">{call.meta?.llm} · {call.meta?.tts} · lang {call.language} · {call.avg_latency_ms ? `${call.avg_latency_ms}ms avg` : "measuring…"}</p>
        </div>
        {call.human_mode && <Badge className="bg-ch-web/15 text-ch-web">human on call</Badge>}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {emotion && emotion.label !== "neutral" && <Badge variant="outline" className={emotion.label === "angry" || emotion.label === "frustrated" ? "border-destructive/40 text-destructive" : ""}>{EMO[emotion.label] || emotion.label} {Math.round(emotion.intensity * 100)}%</Badge>}
        {call.flow_step && <Badge variant="outline"><GitBranch className="size-3" /> step: {call.flow_step}</Badge>}
        {call.meta?.engine && <Badge variant="outline">{call.meta.engine}</Badge>}
        {call.transferred && <Badge className="bg-success/15 text-success">transferred</Badge>}
      </div>
      <div className="h-48 space-y-1.5 overflow-y-auto rounded-lg bg-muted/40 p-2.5 text-xs">
        {lines.map((l, i) => <p key={i}><span className={l.role === "user" ? "font-medium" : "font-medium text-brand"}>{l.role === "user" ? "Caller" : "Agent"}:</span> {l.text}</p>)}
        {lines.length === 0 && <p className="text-muted-foreground"><Ear className="mr-1 inline size-3" />Listening for transcript…</p>}
      </div>
      <div className="flex gap-2">
        <Input className="h-8 text-xs" placeholder={call.human_mode ? "Type what to say to the caller…" : "Whisper an instruction to the AI…"} value={msg} onChange={(e) => setMsg(e.target.value)} />
        <Button size="sm" className="h-8" disabled={!msg} onClick={() => act.mutate({ action: call.human_mode ? "say" : "whisper", text: msg })}>{call.human_mode ? <Volume2 className="size-3.5" /> : "Whisper"}</Button>
      </div>
      <div className="flex gap-2">
        {call.human_mode
          ? <Button size="sm" variant="outline" onClick={() => act.mutate({ action: "release" })}>Hand back to AI</Button>
          : <Button size="sm" variant="outline" onClick={() => act.mutate({ action: "takeover" })}><Hand className="size-3.5" /> Take over</Button>}
        <Button size="sm" variant="outline" onClick={() => transfer.mutate()}><PhoneForwarded className="size-3.5" /> Transfer</Button>
        <Button size="sm" variant="destructive" onClick={() => act.mutate({ action: "end" })}><PhoneOff className="size-3.5" /> End</Button>
        <Button size="sm" variant="ghost" asChild><Link href={`/app/inbox?c=${call.conversation_id}`}>Open</Link></Button>
      </div>
    </Card>
  );
}
