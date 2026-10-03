"use client";

import { FileText, Mic, PhoneOff, Send } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LogoMark } from "@/components/brand";
import { VoiceOrb } from "@/components/orb";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { readSSE } from "@/lib/api";
import { API_URL } from "@/lib/env";
import { useVoiceCall } from "@/lib/voice";
import { cn } from "@/lib/utils";

type Msg = { role: "user" | "assistant" | "human" | "system"; text: string; citations?: any[]; options?: string[] };

function sessionId(key: string) {
  const k = `unisona_session_${key}`;
  let s = localStorage.getItem(k);
  if (!s) {
    s = crypto.randomUUID();
    localStorage.setItem(k, s);
  }
  return s;
}

export default function HostedChat() {
  const { key } = useParams<{ key: string }>();
  const [cfg, setCfg] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [conv, setConv] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const call = useVoiceCall();

  useEffect(() => {
    fetch(`${API_URL}/public/agents/${key}`).then(async (r) => {
      if (!r.ok) return setError("This assistant isn't available.");
      const c = await r.json();
      setCfg(c);
      setMsgs([{ role: "assistant", text: c.greeting }]);
      const saved = localStorage.getItem(`unisona_conv_${key}`);
      if (saved) setConv(saved);
    });
  }, [key]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  useEffect(() => {
    if (!conv) return;
    const es = new EventSource(`${API_URL}/public/conversations/${conv}/events?session_id=${sessionId(key)}`);
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      if (ev.type === "human.message") setMsgs((x) => [...x, { role: "human", text: ev.text }]);
      if (ev.type === "agent.joined") setMsgs((x) => [...x, { role: "system", text: ev.text }]);
    };
    return () => es.close();
  }, [conv, key]);

  const send = async (override?: string) => {
    const content = (override ?? text).trim();
    if (!content || busy) return;
    setText("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text: content }, { role: "assistant", text: "" }]);
    const upd = (fn: (l: Msg) => Msg) => setMsgs((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
    try {
      const res = await fetch(`${API_URL}/public/chat/${key}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: content, session_id: sessionId(key), conversation_id: conv, channel: "web" }) });
      if (!res.ok || !res.body) throw new Error((await res.json().catch(() => ({}))).detail || "Something went wrong");
      await readSSE(res.body, (ev) => {
        if (ev.type === "meta") { setConv(ev.conversation_id); localStorage.setItem(`unisona_conv_${key}`, ev.conversation_id); }
        if (ev.type === "token") upd((l) => ({ ...l, text: l.text + ev.text }));
        if (ev.type === "reset") upd((l) => ({ ...l, text: "" }));
        if (ev.type === "final") {
          const r = ev.reply;
          if (r.awaiting_human) setMsgs((m) => m.slice(0, -1));
          else upd(() => ({ role: "assistant", text: r.text, citations: r.citations, options: r.options }));
        }
      });
    } catch (e: any) {
      upd(() => ({ role: "assistant", text: `⚠️ ${e.message}` }));
    } finally {
      setBusy(false);
    }
  };

  if (error) return <div className="grid min-h-screen place-items-center text-muted-foreground">{error}</div>;
  const color = cfg?.widget?.color || "#6D5EF8";

  return (
    <div className="flex h-dvh flex-col bg-gradient-to-b from-muted/40 to-background">
      <header className="flex items-center gap-3 border-b bg-background/80 px-4 py-3 backdrop-blur">
        <span className="grid size-9 place-items-center rounded-full text-white" style={{ background: color }}>{cfg?.name?.[0] || "A"}</span>
        <div className="flex-1">
          <p className="font-semibold leading-tight">{cfg?.widget?.title || cfg?.business || "Assistant"}</p>
          <p className="text-xs text-muted-foreground">{cfg?.name} · {cfg?.widget?.subtitle}</p>
        </div>
        {cfg?.voice_enabled && (call.active
          ? <Button size="sm" variant="destructive" onClick={call.stop}><PhoneOff className="size-4" /> End call</Button>
          : <Button size="sm" style={{ background: color }} className="text-white" onClick={() => call.start({ endpoint: `${API_URL}/public/voice/${key}/offer`, requestData: { session_id: sessionId(key) } })}><Mic className="size-4" /> Talk</Button>)}
      </header>
      {(call.active || call.state === "error") && (
        <div className="flex flex-col items-center gap-2 border-b bg-background py-6">
          <VoiceOrb level={call.level} state={call.active ? (call.state as any) : "idle"} size={140} />
          <p className="text-sm capitalize text-muted-foreground">{call.error || call.state}</p>
        </div>
      )}
      <main className="mx-auto w-full max-w-2xl flex-1 space-y-3 overflow-y-auto p-4">
        {msgs.map((m, i) =>
          m.role === "system" ? <p key={i} className="text-center text-xs text-muted-foreground">{m.text}</p> : (
            <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div className="max-w-[85%] space-y-1.5">
                <div className={cn("rounded-2xl px-4 py-2.5 text-sm shadow-sm", m.role === "user" ? "text-white" : "border bg-background")} style={m.role === "user" ? { background: color } : undefined}>
                  {m.role === "human" && <p className="mb-0.5 text-[10px] font-semibold uppercase text-muted-foreground">Team member</p>}
                  {m.text ? <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown></div> : <span className="flex gap-1">{[0, 1, 2].map((d) => <span key={d} className="size-1.5 animate-bounce rounded-full bg-muted-foreground/50" style={{ animationDelay: `${d * 0.12}s` }} />)}</span>}
                </div>
                {m.citations && m.citations.length > 0 && <div className="flex flex-wrap gap-1">{m.citations.map((c: any) => <a key={c.source_id} href={c.url || undefined} target="_blank" rel="noreferrer" title={c.snippet} className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-0.5 text-[11px] text-muted-foreground"><FileText className="size-3" />{c.title}</a>)}</div>}
                {m.options && m.options.length > 0 && <div className="flex flex-wrap gap-1.5">{m.options.map((o) => <button key={o} onClick={() => send(o)} className="rounded-full border bg-background px-3 py-1 text-xs hover:bg-muted">{o}</button>)}</div>}
              </div>
            </div>
          ),
        )}
        {msgs.length <= 1 && (cfg?.widget?.starters || []).length > 0 && (
          <div className="flex flex-wrap gap-2 pt-2">{cfg.widget.starters.map((s: string) => <button key={s} onClick={() => send(s)} className="rounded-full border bg-background px-3 py-1.5 text-xs hover:bg-muted">{s}</button>)}</div>
        )}
        <div ref={bottom} />
      </main>
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="mx-auto flex w-full max-w-2xl gap-2 p-4">
        <Input className="h-11 bg-background" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your message… (any language)" />
        <Button type="submit" className="h-11 text-white" style={{ background: color }} disabled={busy || !text.trim()}><Send className="size-4" /></Button>
      </form>
      <p className="pb-3 text-center text-[11px] text-muted-foreground"><LogoMark className="mr-1 inline-flex size-4 align-middle" /> Powered by Unisona</p>
    </div>
  );
}
