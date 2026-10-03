"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Brain, CheckCheck, FileText, Hand, Inbox, Loader2, MessageSquareReply, Search, Send, Sparkles, User, UserRound, Wand2, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { TraceById } from "@/components/agent/diagnostics";
import { ChannelBadge, ChannelDot, EmptyState, LoadingBlock, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { duration, initials, timeAgo } from "@/lib/format";
import { useRealtime } from "@/lib/workspace";
import { cn } from "@/lib/utils";

const FILTERS = [
  ["open", "Open"], ["handoff_pending", "Needs human"], ["human", "With team"], ["ai", "AI handling"], ["closed", "Closed"], ["", "All"],
];

function InboxInner() {
  const api = useApi();
  const qc = useQueryClient();
  const router = useRouter();
  const params = useSearchParams();
  const [status, setStatus] = useState(params.get("status") ?? "open");
  const [channel, setChannel] = useState("");
  const [q, setQ] = useState("");
  const selected = params.get("c");
  const { data, isLoading } = useQuery({
    queryKey: ["conversations", "inbox", status, channel, q],
    queryFn: () => api.get(`/conversations?limit=150${status ? `&status=${status}` : ""}${channel ? `&channel=${channel}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
    refetchInterval: 20000,
  });
  useRealtime((ev) => {
    if (ev.type === "message.created" || ev.type === "handoff.requested" || ev.type === "conversation.updated") {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (ev.conversation_id === selected) qc.invalidateQueries({ queryKey: ["conversation", selected] });
    }
  });
  const select = (id: string) => router.replace(`/app/inbox?c=${id}${status ? `&status=${status}` : ""}`, { scroll: false });
  const counts = data?.counts || {};

  return (
    <div className="grid h-[calc(100vh-3.5rem)] grid-cols-1 md:grid-cols-[340px_1fr] xl:grid-cols-[340px_1fr_340px]">
      <aside className="flex min-h-0 flex-col border-r">
        <div className="space-y-2 border-b p-3">
          <div className="flex items-center justify-between">
            <h1 className="flex items-center gap-2 font-semibold"><Inbox className="size-4 text-brand" /> Inbox</h1>
            <select className="rounded-md border bg-background px-2 py-1 text-xs" value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="">All channels</option>
              {["web", "widget", "voice", "phone", "whatsapp", "telegram", "email"].map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
            <Input className="h-8 pl-8 text-sm" placeholder="Search name, phone, subject" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-1">
            {FILTERS.map(([v, l]) => (
              <button key={v} onClick={() => setStatus(v)} className={cn("rounded-full px-2.5 py-1 text-xs transition", status === v ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted")}>
                {l}
                {v === "handoff_pending" && counts.handoff_pending ? <span className="ml-1 rounded-full bg-warning px-1.5 text-[10px] text-white">{counts.handoff_pending}</span> : null}
              </button>
            ))}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isLoading && <LoadingBlock />}
          {!isLoading && (data?.items || []).length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">No conversations here.</p>}
          {(data?.items || []).map((c: any) => (
            <button key={c.id} onClick={() => select(c.id)} className={cn("flex w-full gap-3 border-b px-3 py-3 text-left transition hover:bg-muted/50", selected === c.id && "bg-brand-soft/50")}>
              <div className="relative">
                <span className="grid size-9 place-items-center rounded-full bg-muted text-xs font-semibold">{initials(c.contact?.name || c.contact?.phone || "V")}</span>
                <span className="absolute -bottom-1 -right-1 scale-75"><ChannelDot channel={c.channel} /></span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium">{c.contact?.name || c.contact?.phone || "Website visitor"}</p>
                  <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(c.last_message_at).replace(" ago", "")}</span>
                </div>
                <p className="truncate text-xs text-muted-foreground">{c.last_message?.role === "assistant" ? "AI: " : c.last_message?.role === "human" ? "You: " : ""}{c.last_message?.content || c.subject}</p>
                <div className="mt-1 flex items-center gap-1.5">
                  <StatusBadge status={c.status} className="h-4 px-1.5 text-[10px]" />
                  <span className="truncate text-[10px] text-muted-foreground">{c.agent_name}</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </aside>
      {selected ? <Thread id={selected} /> : (
        <div className="hidden items-center justify-center md:flex xl:col-span-2">
          <EmptyState icon={MessageSquareReply} title="Pick a conversation" description="Every channel lands here: web, widget, voice calls, phone, WhatsApp, Telegram. Take over anytime." className="border-0" />
        </div>
      )}
    </div>
  );
}

function Thread({ id }: { id: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [trace, setTrace] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const { data, isLoading } = useQuery({ queryKey: ["conversation", id], queryFn: () => api.get(`/conversations/${id}`) });
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [data?.messages?.length]);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["conversation", id] });
    qc.invalidateQueries({ queryKey: ["conversations"] });
  };
  const act = useMutation({ mutationFn: (a: string) => api.post(`/conversations/${id}/${a}`), onSuccess: (_, a) => { refresh(); toast.success({ accept: "You're now handling this conversation", release: "Handed back to the AI", close: "Conversation closed", analyze: "Analysis updated" }[a] || "Done"); } });
  const send = useMutation({
    mutationFn: () => api.post(`/conversations/${id}/messages`, { text }),
    onSuccess: (r) => {
      setText("");
      refresh();
      if (!r.delivered) toast.warning(`Saved but not delivered: ${r.detail}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const suggest = useMutation({ mutationFn: () => api.post(`/conversations/${id}/suggest`), onSuccess: (r) => setText(r.suggestion), onError: (e: Error) => toast.error(e.message) });
  if (isLoading || !data) return <LoadingBlock />;
  const c = data.conversation;
  const contact = data.contact;
  const pendingHandoff = data.handoffs?.find((h: any) => h.status === "pending");

  return (
    <>
      <section className="flex min-h-0 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{contact?.name || contact?.phone || "Website visitor"}</p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <ChannelBadge channel={c.channel} /> <span>{data.agent?.name}</span> <StatusBadge status={c.status} />
            </div>
          </div>
          {c.status !== "human" && c.status !== "closed" && (
            <Button size="sm" onClick={() => act.mutate("accept")} className="bg-brand text-brand-foreground hover:bg-brand/90"><Hand className="size-3.5" /> Take over</Button>
          )}
          {c.status === "human" && <Button size="sm" variant="outline" onClick={() => act.mutate("release")}><Bot className="size-3.5" /> Hand back to AI</Button>}
          {c.status !== "closed" && <Button size="sm" variant="ghost" onClick={() => act.mutate("close")}><CheckCheck className="size-3.5" /> Close</Button>}
        </div>
        {pendingHandoff && (
          <div className="border-b bg-warning/10 px-4 py-3 text-sm">
            <p className="font-medium text-warning">Needs a human · {pendingHandoff.reason.replaceAll("_", " ")} · {pendingHandoff.urgency} urgency</p>
            {pendingHandoff.brief && <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">{pendingHandoff.brief}</p>}
          </div>
        )}
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-muted/20 p-4">
          {data.messages.map((m: any) => (
            <div key={m.id} className={cn("flex gap-2", m.role === "user" ? "" : "flex-row-reverse")}>
              <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full text-[10px]", m.role === "user" ? "bg-muted" : m.role === "human" ? "bg-ch-web/15 text-ch-web" : "bg-brand-soft text-brand")}>
                {m.role === "user" ? <UserRound className="size-3.5" /> : m.role === "human" ? <User className="size-3.5" /> : <Sparkles className="size-3.5" />}
              </span>
              <div className={cn("max-w-[75%] space-y-1", m.role !== "user" && "items-end text-right")}>
                <div
                  onClick={() => m.trace_id && setTrace(m.trace_id)}
                  className={cn("inline-block rounded-2xl px-3.5 py-2 text-left text-sm", m.role === "user" ? "border bg-background" : m.role === "human" ? "bg-ch-web text-white" : "bg-foreground text-background", m.trace_id && "cursor-pointer", m.flagged && "ring-2 ring-destructive/40")}
                >
                  <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  {m.role === "assistant" ? "AI" : m.role === "human" ? m.ir?.author || "Team" : "Customer"} · {new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  {m.latency_ms ? ` · ${(m.latency_ms / 1000).toFixed(1)}s` : ""}
                  {m.flagged ? ` · ⚑ ${m.flag_reason?.replaceAll("_", " ")}` : ""}
                  {m.trace_id && <button className="ml-1 text-brand underline" onClick={() => setTrace(m.trace_id)}>why?</button>}
                </p>
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>
        {c.status !== "closed" && (
          <div className="border-t p-3">
            <div className="flex items-end gap-2">
              <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder={c.status === "human" ? `Reply on ${c.channel}…` : "Type to take over and reply…"} onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim()) send.mutate(); }} />
              <div className="flex flex-col gap-1.5">
                <Button size="sm" variant="outline" onClick={() => suggest.mutate()} disabled={suggest.isPending} title="AI drafts a reply from your knowledge">
                  {suggest.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Wand2 className="size-3.5" />} Suggest
                </Button>
                <Button size="sm" disabled={!text.trim() || send.isPending} onClick={() => send.mutate()}><Send className="size-3.5" /> Send</Button>
              </div>
            </div>
            <p className="mt-1.5 text-[11px] text-muted-foreground">Ctrl+Enter to send. Replies go out on {c.channel === "voice" ? "the live call (spoken)" : c.channel}.</p>
          </div>
        )}
      </section>
      <aside className="hidden min-h-0 overflow-y-auto border-l xl:block">
        <div className="space-y-4 p-4">
          {contact ? (
            <>
              <div className="flex items-center gap-3">
                <span className="grid size-11 place-items-center rounded-full bg-brand-soft font-semibold text-brand">{initials(contact.name || contact.phone)}</span>
                <div className="min-w-0">
                  <p className="truncate font-medium">{contact.name || "Unknown"}</p>
                  <p className="text-xs capitalize text-muted-foreground">{contact.lifecycle} · score {contact.score}</p>
                </div>
              </div>
              <Button asChild size="sm" variant="outline" className="w-full"><Link href={`/app/crm/contacts/${contact.id}`}>Open in CRM</Link></Button>
              <div>
                <p className="mb-1.5 text-xs font-semibold">Known as</p>
                <div className="flex flex-wrap gap-1">
                  {data.identities.map((i: any) => <Badge key={i.id} variant="outline" className="font-mono text-[10px]">{i.type}: {i.value}</Badge>)}
                </div>
              </div>
              {contact.tags?.length > 0 && <div className="flex flex-wrap gap-1">{contact.tags.map((t: string) => <Badge key={t} variant="secondary">{t}</Badge>)}</div>}
              <div>
                <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold"><Brain className="size-3.5 text-brand" /> What the agent remembers</p>
                {data.facts.length === 0 ? <p className="text-xs text-muted-foreground">No facts yet. They&apos;re extracted after conversations.</p> : (
                  <ul className="space-y-1">{data.facts.map((f: any) => <li key={f.id} className="rounded-md bg-muted/50 px-2 py-1 text-xs">{f.fact}</li>)}</ul>
                )}
              </div>
              <div>
                <p className="mb-1.5 text-xs font-semibold">Other channels</p>
                {data.other_conversations.length === 0 && <p className="text-xs text-muted-foreground">First conversation with this person.</p>}
                {data.other_conversations.map((o: any) => (
                  <Link key={o.id} href={`/app/inbox?c=${o.id}`} className="mb-1.5 block rounded-md border p-2 text-xs hover:bg-muted/50">
                    <div className="flex items-center justify-between"><ChannelBadge channel={o.channel} /><span className="text-muted-foreground">{timeAgo(o.last_message_at)}</span></div>
                    <p className="mt-1 line-clamp-2 text-muted-foreground">{o.summary || "(in progress)"}</p>
                  </Link>
                ))}
              </div>
            </>
          ) : <p className="text-sm text-muted-foreground">Anonymous visitor. Identity links automatically when they share a phone or email.</p>}
          {c.summary && (
            <div>
              <p className="mb-1 text-xs font-semibold">AI summary</p>
              <p className="text-xs text-muted-foreground">{c.summary}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {c.outcome && <Badge variant="outline">{c.outcome.replaceAll("_", " ")}</Badge>}
                {c.sentiment && <Badge variant="outline">{c.sentiment}</Badge>}
                {c.csat && <Badge variant="outline">CSAT {c.csat}/5</Badge>}
              </div>
              {c.analysis?.fields && <pre className="mt-2 whitespace-pre-wrap rounded bg-muted/50 p-2 text-[11px]">{JSON.stringify(c.analysis.fields, null, 2)}</pre>}
            </div>
          )}
          {data.call && (
            <div>
              <p className="mb-1 text-xs font-semibold">Call</p>
              <p className="text-xs text-muted-foreground">{duration(data.call.duration_s)} · avg latency {data.call.metrics?.avg_latency_ms ?? "—"}ms · {data.call.metrics?.stt} / {data.call.metrics?.llm} / {data.call.metrics?.tts}</p>
              {data.call.recording_path && <Recording callId={data.call.id} />}
            </div>
          )}
          <Button size="sm" variant="ghost" className="w-full" onClick={() => act.mutate("analyze")}><FileText className="size-3.5" /> Re-run analysis</Button>
        </div>
      </aside>
      <Sheet open={!!trace} onOpenChange={(o) => !o && setTrace(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader><SheetTitle>Why the AI said this</SheetTitle></SheetHeader>
          <div className="px-4 pb-6"><TraceById traceId={trace} /></div>
        </SheetContent>
      </Sheet>
    </>
  );
}

function Recording({ callId }: { callId: string }) {
  const api = useApi();
  const [src, setSrc] = useState<string | null>(null);
  return src ? <audio controls src={src} className="mt-2 w-full" /> : (
    <Button size="sm" variant="outline" className="mt-2 w-full" onClick={async () => setSrc(URL.createObjectURL(await api.get<Blob>(`/calls/${callId}/recording`)))}>Load recording</Button>
  );
}

export default function InboxPage() {
  return (
    <Suspense>
      <InboxInner />
    </Suspense>
  );
}
