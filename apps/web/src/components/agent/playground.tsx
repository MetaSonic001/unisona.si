"use client";

import { Bot, FileText, Mic, MicOff, PhoneOff, RotateCcw, Send, ThumbsDown, ThumbsUp, User, Wrench } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { TraceById } from "@/components/agent/diagnostics";
import { ChannelBadge } from "@/components/common";
import { VoiceOrb } from "@/components/orb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api";
import { API_URL } from "@/lib/env";
import { useVoiceCall } from "@/lib/voice";
import { useRealtime } from "@/lib/workspace";
import { cn } from "@/lib/utils";

type Msg = { id?: string; role: "user" | "assistant" | "system"; text: string; citations?: any[]; options?: string[]; trace_id?: string; tools?: string[]; pending?: boolean; via?: string; latency?: number };

const CHANNELS = [
  { v: "playground", label: "Web chat" },
  { v: "whatsapp", label: "WhatsApp (simulated)" },
  { v: "telegram", label: "Telegram (simulated)" },
  { v: "voice", label: "Voice wording (text)" },
];

export function Playground({ agentId, greeting, dirty }: { agentId: string; greeting?: string; dirty: boolean }) {
  const api = useApi();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [channel, setChannel] = useState("playground");
  const [identity, setIdentity] = useState("");
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [tool, setTool] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const call = useVoiceCall();
  const [callConv, setCallConv] = useState<string | null>(null);

  useEffect(() => {
    setMsgs(greeting ? [{ role: "assistant", text: greeting }] : []);
  }, [greeting]);
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [msgs, tool]);

  useRealtime((ev) => {
    if (ev.type === "call.started" && call.active && ev.call?.agent_id === agentId) setCallConv(ev.call.conversation_id);
    if (ev.type === "call.transcript" && call.active) {
      setMsgs((m) => [...m, { role: ev.role === "user" ? "user" : "assistant", text: ev.text, via: "voice", latency: ev.latency_ms }]);
    }
    if (ev.type === "call.tool" && call.active) setMsgs((m) => [...m, { role: "system", text: `Used tool ${ev.tool}` }]);
    if (ev.type === "human.message" || (ev.type === "message.created" && ev.message?.role === "human" && ev.conversation_id === conversationId)) {
      setMsgs((m) => [...m, { role: "assistant", text: ev.message?.content || ev.text, via: "human" }]);
    }
  });

  const identifiersFor = () => {
    if (!identity.trim()) return undefined;
    const v = identity.trim();
    if (v.includes("@")) return { email: v };
    if (channel === "whatsapp") return { wa_id: v };
    if (channel === "telegram") return { telegram_id: v };
    return { phone: v };
  };

  const send = async (override?: string) => {
    const content = (override ?? text).trim();
    if (!content || busy) return;
    setText("");
    setBusy(true);
    setTool(null);
    setMsgs((m) => [...m, { role: "user", text: content }, { role: "assistant", text: "", pending: true }]);
    const update = (fn: (last: Msg) => Msg) => setMsgs((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
    try {
      await api.stream(
        `/chat/${agentId}`,
        { text: content, conversation_id: conversationId, channel, identifiers: identifiersFor(), use_draft: true, channel_ref: identity ? `pg:${channel}:${identity}` : undefined },
        (ev) => {
          if (ev.type === "meta") setConversationId(ev.conversation_id);
          if (ev.type === "token") update((l) => ({ ...l, text: l.text + ev.text }));
          if (ev.type === "reset") update((l) => ({ ...l, text: "" }));
          if (ev.type === "tool") setTool(ev.name);
          if (ev.type === "error") toast.error(ev.message);
          if (ev.type === "final") {
            const r = ev.reply;
            setTool(null);
            update(() => ({ role: "assistant", id: r.message_id, text: r.text || (r.awaiting_human ? "(waiting for a human teammate…)" : ""), citations: r.citations, options: r.options, trace_id: r.trace_id, tools: r.tools_used, latency: r.latency_ms }));
            if (r.trace_id) setSelectedTrace(r.trace_id);
            if (r.handoff) toast.info("Handed off to a human", { description: "This conversation now shows in the Inbox as needing a human." });
          }
        },
      );
    } catch (e: any) {
      update(() => ({ role: "assistant", text: `⚠️ ${e.message}` }));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setConversationId(null);
    setMsgs(greeting ? [{ role: "assistant", text: greeting }] : []);
    setSelectedTrace(null);
  };

  const startCall = async () => {
    reset();
    const token = await api.token();
    await call.start({
      endpoint: `${API_URL}/voice/offer`,
      headers: { Authorization: `Bearer ${token}` },
      requestData: { agent_id: agentId, use_draft: true, identifiers: identifiersFor() || undefined },
    });
  };

  const feedback = async (id: string, value: number) => {
    await api.post(`/messages/${id}/feedback`, { value });
    toast.success(value > 0 ? "Thanks for the feedback" : "Flagged for the improve loop", { description: value > 0 ? undefined : "It'll show in Review with a suggested correction." });
  };

  return (
    <div className="grid h-[calc(100vh-11.5rem)] min-h-[520px] gap-4 lg:grid-cols-[1fr_420px]">
      <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-card">
        <div className="flex flex-wrap items-center gap-2 border-b p-2.5">
          <Select value={channel} onValueChange={setChannel}>
            <SelectTrigger className="h-8 w-[200px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CHANNELS.map((c) => (
                <SelectItem key={c.v} value={c.v}>{c.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input className="h-8 max-w-[230px]" placeholder="Customer phone/email (tests memory)" value={identity} onChange={(e) => setIdentity(e.target.value)} />
          <div className="ml-auto flex items-center gap-1.5">
            {dirty && <span className="text-[11px] text-warning">Testing unsaved draft? Save first.</span>}
            <Button size="sm" variant="ghost" onClick={reset}>
              <RotateCcw className="size-3.5" /> New chat
            </Button>
          </div>
        </div>

        {call.active || call.state === "ended" || call.state === "error" ? (
          <div className="flex flex-col items-center gap-3 border-b bg-gradient-to-b from-brand-soft/50 to-transparent py-5">
            <VoiceOrb level={call.level} state={call.active ? (call.state as any) : "idle"} size={150} />
            <p className="text-sm font-medium capitalize">{call.state === "error" ? call.error : call.state === "ended" ? "Call ended" : call.state}</p>
            <div className="flex gap-2">
              {call.active ? (
                <>
                  <Button size="sm" variant="outline" onClick={call.toggleMute}>
                    {call.muted ? <MicOff className="size-4" /> : <Mic className="size-4" />} {call.muted ? "Unmute" : "Mute"}
                  </Button>
                  <Button size="sm" variant="destructive" onClick={call.stop}>
                    <PhoneOff className="size-4" /> End call
                  </Button>
                </>
              ) : (
                <Button size="sm" onClick={startCall}>
                  <Mic className="size-4" /> Call again
                </Button>
              )}
            </div>
            {callConv && <p className="text-[11px] text-muted-foreground">Transcript appears below and in the Inbox.</p>}
          </div>
        ) : null}

        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-4 p-4">
            {msgs.map((m, i) =>
              m.role === "system" ? (
                <p key={i} className="text-center text-[11px] text-muted-foreground">
                  <Wrench className="mr-1 inline size-3" /> {m.text}
                </p>
              ) : (
                <div key={i} className={cn("flex gap-2.5", m.role === "user" && "flex-row-reverse")}>
                  <span className={cn("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full", m.role === "user" ? "bg-muted" : "bg-brand-soft text-brand")}>
                    {m.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
                  </span>
                  <div className={cn("max-w-[80%] space-y-1.5", m.role === "user" && "items-end text-right")}>
                    <div
                      onClick={() => m.trace_id && setSelectedTrace(m.trace_id)}
                      className={cn(
                        "inline-block rounded-2xl px-3.5 py-2 text-left text-sm",
                        m.role === "user" ? "bg-foreground text-background" : "border bg-background",
                        m.trace_id && "cursor-pointer hover:border-brand/50",
                        m.trace_id && selectedTrace === m.trace_id && "ring-2 ring-brand/40",
                      )}
                    >
                      {m.pending && !m.text ? (
                        <span className="flex items-center gap-1.5 text-muted-foreground">
                          <span className="flex gap-1">
                            {[0, 1, 2].map((d) => (
                              <span key={d} className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60" style={{ animationDelay: `${d * 0.12}s` }} />
                            ))}
                          </span>
                          {tool ? `using ${tool.replaceAll("_", " ")}…` : ""}
                        </span>
                      ) : (
                        <div className="md">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                        </div>
                      )}
                    </div>
                    {m.via && <ChannelBadge channel={m.via === "voice" ? "voice" : "web"} className="ml-1" />}
                    {m.options && m.options.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {m.options.map((o) => (
                          <Button key={o} size="sm" variant="outline" className="h-7 rounded-full text-xs" onClick={() => send(o)}>{o}</Button>
                        ))}
                      </div>
                    )}
                    {m.citations && m.citations.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {m.citations.map((c: any) => (
                          <span key={c.source_id} title={c.snippet} className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground">
                            <FileText className="size-3" /> {c.title}
                          </span>
                        ))}
                      </div>
                    )}
                    {m.id && m.role === "assistant" && (
                      <div className="flex items-center gap-1 text-muted-foreground">
                        <button className="rounded p-1 hover:bg-muted hover:text-success" onClick={() => feedback(m.id!, 1)} aria-label="Good answer"><ThumbsUp className="size-3.5" /></button>
                        <button className="rounded p-1 hover:bg-muted hover:text-destructive" onClick={() => feedback(m.id!, -1)} aria-label="Bad answer"><ThumbsDown className="size-3.5" /></button>
                        {m.latency && <span className="ml-1 text-[11px]">{(m.latency / 1000).toFixed(1)}s</span>}
                        {m.tools && m.tools.length > 0 && <span className="ml-1 text-[11px]">· {m.tools.join(", ")}</span>}
                      </div>
                    )}
                  </div>
                </div>
              ),
            )}
          </div>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
          className="flex items-center gap-2 border-t p-2.5"
        >
          <Button type="button" size="icon" variant={call.active ? "destructive" : "outline"} onClick={call.active ? call.stop : startCall} aria-label="Voice call" title="Talk to the agent (browser call)">
            {call.active ? <PhoneOff className="size-4" /> : <Mic className="size-4" />}
          </Button>
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask anything a customer would… (any language)" disabled={busy} />
          <Button type="submit" size="icon" disabled={busy || !text.trim()} className="bg-brand text-brand-foreground hover:bg-brand/90" aria-label="Send">
            <Send className="size-4" />
          </Button>
        </form>
      </div>

      <div className="min-h-0 overflow-hidden rounded-xl border bg-card">
        <div className="border-b px-4 py-3">
          <p className="text-sm font-semibold">Why it answered that</p>
          <p className="text-xs text-muted-foreground">Click any AI reply to inspect retrieval, memory, tools, prompt and cost.</p>
        </div>
        <div className="h-[calc(100%-3.75rem)] overflow-y-auto p-3">
          <TraceById traceId={selectedTrace} />
        </div>
      </div>
    </div>
  );
}
