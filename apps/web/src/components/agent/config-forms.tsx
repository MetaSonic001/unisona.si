"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pause, Play, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { AreaField, ChipToggle, Field, ListField, SliderField, SwitchRow, TextField } from "@/components/agent/fields";
import { getPath } from "@/components/agent/use-agent";
import { Section, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api";
import { API_URL } from "@/lib/env";
import { cn } from "@/lib/utils";

type FormProps = { cfg: any; set: (path: string, v: any) => void };

export function PersonaForm({ cfg, set, name, setName }: FormProps & { name: string; setName: (v: string) => void }) {
  const api = useApi();
  const { data: catalog } = useQuery({ queryKey: ["providers-catalog"], queryFn: () => api.get("/providers/catalog") });
  const { data: langs } = useQuery({ queryKey: ["languages"], queryFn: () => api.get("/languages") });
  const llmProviders = (catalog?.providers || []).filter((p: any) => p.categories.includes("llm"));
  const provider = cfg.llm?.provider || "";
  const models = llmProviders.find((p: any) => p.id === provider)?.llm_models || [];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-4 p-5">
        <Section title="Identity" description="Who the agent is and how it greets people.">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Agent display name (internal)" value={name} onChange={setName} />
            <TextField label="Persona name (what it calls itself)" value={cfg.persona.name} onChange={(v) => set("persona.name", v)} />
          </div>
          <TextField label="Role" value={cfg.persona.role} onChange={(v) => set("persona.role", v)} placeholder="e.g. front-desk assistant" />
          <AreaField label="Greeting" rows={2} value={cfg.persona.greeting} onChange={(v) => set("persona.greeting", v)} hint="Supports {{agent_name}}, {{business_name}} and your own {{variables}}." />
          <SliderField label="Tone" value={cfg.persona.tone ?? 60} onChange={(v) => set("persona.tone", v)} left="Formal" right="Warm & casual" />
          <SliderField label="Answer length" value={cfg.persona.verbosity ?? 35} onChange={(v) => set("persona.verbosity", v)} left="Concise" right="Detailed" />
        </Section>
      </Card>
      <Card className="gap-4 p-5">
        <Section title="Goals & instructions" description="What the agent should achieve, in plain language.">
          <ListField label="Goals" values={cfg.persona.goals || []} onChange={(v) => set("persona.goals", v)} placeholder="e.g. Book a site visit for qualified buyers" />
          <AreaField label="Extra instructions" rows={6} value={cfg.persona.prompt} onChange={(v) => set("persona.prompt", v)} placeholder="Anything specific: policies to follow, what to ask, what never to say…" />
        </Section>
      </Card>
      <Card className="gap-4 p-5">
        <Section title="Business" description="Facts the agent always knows (no retrieval needed).">
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Business name" value={cfg.business.name} onChange={(v) => set("business.name", v)} />
            <TextField label="Website" value={cfg.business.website} onChange={(v) => set("business.website", v)} />
            <TextField label="Hours" value={cfg.business.hours} onChange={(v) => set("business.hours", v)} />
            <TextField label="Phone" value={cfg.business.phone} onChange={(v) => set("business.phone", v)} />
            <TextField label="Email" value={cfg.business.email} onChange={(v) => set("business.email", v)} />
            <TextField label="Address" value={cfg.business.address} onChange={(v) => set("business.address", v)} />
          </div>
          <AreaField label="About" rows={2} value={cfg.business.description} onChange={(v) => set("business.description", v)} />
        </Section>
      </Card>
      <Card className="gap-4 p-5">
        <Section title="Languages & model" description="The agent mirrors the customer's language automatically.">
          <Field label="Supported languages">
            <ChipToggle
              options={(langs?.items || []).map((l: any) => ({ value: l.code, label: `${l.native} · ${l.name}` }))}
              value={cfg.languages.supported || []}
              onChange={(v) => set("languages.supported", v)}
            />
          </Field>
          <SwitchRow label="Reply in the customer's language" hint="Including Hinglish and code-mixed speech." checked={cfg.languages.mirror_user} onChange={(v) => set("languages.mirror_user", v)} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="LLM provider" hint="Uses your workspace key (BYOK). Auto picks the first provider with a key.">
              <Select value={provider || "auto"} onValueChange={(v) => { set("llm.provider", v === "auto" ? null : v); set("llm.model", null); }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto (recommended)</SelectItem>
                  {llmProviders.map((p: any) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Model">
              <Select value={cfg.llm?.model || "default"} onValueChange={(v) => set("llm.model", v === "default" ? null : v)} disabled={!provider}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">Provider default</SelectItem>
                  {models.map((m: string) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <SliderField label="Creativity" value={Math.round((cfg.llm?.temperature ?? 0.3) * 100)} onChange={(v) => set("llm.temperature", v / 100)} left="Precise" right="Creative" format={(v) => (v / 100).toFixed(2)} />
        </Section>
      </Card>
    </div>
  );
}

export function VoiceForm({ cfg, set }: FormProps) {
  const api = useApi();
  const [locale, setLocale] = useState(cfg.languages?.primary || "en-IN");
  const [engine, setEngine] = useState("all");
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const { data: langs } = useQuery({ queryKey: ["languages"], queryFn: () => api.get("/languages") });
  const { data } = useQuery({ queryKey: ["voices", locale, engine], queryFn: () => api.get(`/voices?locale=${locale}${engine !== "all" ? `&engine=${engine}` : ""}`) });
  const play = (id: string, loc: string) => {
    if (playing === id) {
      audio.current?.pause();
      setPlaying(null);
      return;
    }
    audio.current?.pause();
    const a = new Audio(`${API_URL}/voices/preview?voice_id=${encodeURIComponent(id)}&locale=${loc}`);
    audio.current = a;
    setPlaying(id);
    a.onended = () => setPlaying(null);
    a.onerror = () => {
      setPlaying(null);
      toast.error("Preview failed for this voice");
    };
    a.play();
  };
  const voiceId = cfg.voice.voice_id;
  const perLang = cfg.voice.per_language || {};
  return (
    <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
      <Card className="gap-4 p-5">
        <Section title="Voice library" description="Free neural voices in 25+ languages, local offline voices, or your own provider.">
          <div className="flex flex-wrap gap-2">
            <Select value={locale} onValueChange={setLocale}>
              <SelectTrigger className="w-[220px]"><SelectValue /></SelectTrigger>
              <SelectContent>{(langs?.items || []).map((l: any) => <SelectItem key={l.code} value={l.code}>{l.native} · {l.name}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={engine} onValueChange={setEngine}>
              <SelectTrigger className="w-[170px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All engines</SelectItem>
                <SelectItem value="edge">Edge neural (free)</SelectItem>
                <SelectItem value="kokoro">Kokoro (local)</SelectItem>
                <SelectItem value="groq">Groq Orpheus (BYOK)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid max-h-[420px] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
            {(data?.items || []).slice(0, 60).map((v: any) => {
              const selected = voiceId === v.id;
              const forLocale = perLang[locale] === v.id;
              return (
                <div key={v.id} className={cn("flex items-center gap-2 rounded-lg border p-2.5 transition", selected && "border-brand bg-brand-soft/40")}>
                  <button onClick={() => play(v.id, locale)} className="grid size-8 shrink-0 place-items-center rounded-full bg-muted hover:bg-brand-soft hover:text-brand" aria-label="Preview">
                    {playing === v.id ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{v.name}</p>
                    <p className="truncate text-[11px] text-muted-foreground">
                      {v.locale} · {v.gender} · {v.engine}
                      {v.multilingual && " · multilingual"}
                    </p>
                  </div>
                  <div className="flex flex-col gap-1">
                    <Button size="sm" variant={selected ? "default" : "outline"} className="h-6 px-2 text-[11px]" onClick={() => set("voice.voice_id", v.id)}>
                      {selected ? <Check className="size-3" /> : "Main"}
                    </Button>
                    {locale !== (cfg.languages?.primary || "en-IN") && (
                      <Button size="sm" variant={forLocale ? "default" : "ghost"} className="h-6 px-2 text-[11px]" onClick={() => set(`voice.per_language`, { ...perLang, [locale]: v.id })}>
                        {forLocale ? <Check className="size-3" /> : `For ${locale}`}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      </Card>
      <div className="space-y-6">
        <Card className="gap-4 p-5">
          <Section title="Selected voices">
            <p className="text-sm">
              Main voice: <span className="font-mono text-xs">{voiceId}</span>
            </p>
            <div className="space-y-1.5">
              {Object.entries(perLang).map(([loc, vid]: any) => (
                <div key={loc} className="flex items-center justify-between rounded-md border px-2.5 py-1.5 text-xs">
                  <span>{loc} → <span className="font-mono">{vid}</span></span>
                  <button className="text-muted-foreground hover:text-destructive" onClick={() => { const n = { ...perLang }; delete n[loc]; set("voice.per_language", n); }}>
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">When a caller switches language, the agent automatically switches to the matching voice.</p>
            <SliderField label="Speaking speed" value={Math.round((cfg.voice.speed ?? 1) * 100)} min={70} max={130} onChange={(v) => set("voice.speed", v / 100)} format={(v) => `${(v / 100).toFixed(2)}×`} />
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="Voice engine" description="Cascade gives full control and free voices; speech-to-speech gives the most natural, Gemini-Live-style turn-taking (BYOK).">
            <Field label="Engine">
              <Select value={cfg.voice.engine || "cascade"} onValueChange={(v) => set("voice.engine", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cascade">Cascade: STT → LLM → TTS (free, any voice)</SelectItem>
                  <SelectItem value="gemini_live">Gemini Live speech-to-speech (Gemini key)</SelectItem>
                  <SelectItem value="openai_realtime">OpenAI Realtime speech-to-speech (OpenAI key)</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            {cfg.voice.engine === "gemini_live" && (
              <Field label="Gemini voice" hint="Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr…">
                <Input value={cfg.voice.s2s_voice || "Aoede"} onChange={(e) => set("voice.s2s_voice", e.target.value)} />
              </Field>
            )}
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="Premium & cloned voices (BYOK)" description="Use a voice from your Cartesia, ElevenLabs, Sarvam (Bulbul), Deepgram or OpenAI account, including voices you've cloned there.">
            <div className="grid grid-cols-[150px_1fr] gap-2">
              <Select value={(voiceId || "edge:").split(":")[0]} onValueChange={(eng) => set("voice.voice_id", `${eng}:${eng === "sarvam" ? "anushka" : eng === "deepgram" ? "aura-2-thalia-en" : eng === "openai" ? "marin" : ""}`)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["edge", "kokoro", "cartesia", "elevenlabs", "sarvam", "deepgram", "openai", "groq"].map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
                </SelectContent>
              </Select>
              <Input placeholder="voice id (paste from your provider)" value={(voiceId || "").split(":").slice(1).join(":")} onChange={(e) => set("voice.voice_id", `${(voiceId || "edge:").split(":")[0]}:${e.target.value}`)} />
            </div>
            <p className="text-[11px] text-muted-foreground">Add the provider key in Settings → AI providers. If the key is missing, calls fall back to a free Edge voice and the API logs which key to add.</p>
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="Conversation timing">
            <SwitchRow label="Allow interruptions (barge-in)" hint="The agent stops talking the moment the caller speaks." checked={cfg.voice.interruptions} onChange={(v) => set("voice.interruptions", v)} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="End of turn">
                <Select value={cfg.voice.end_of_turn || "smart"} onValueChange={(v) => set("voice.end_of_turn", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="smart">Smart (understands pauses)</SelectItem>
                    <SelectItem value="vad">Fixed silence (fastest)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <TextField label="Patience (s)" type="number" value={String(cfg.voice.turn_patience_s ?? 1.2)} onChange={(v) => set("voice.turn_patience_s", Number(v))} hint="Max wait when the caller pauses mid-thought" />
            </div>
            <TextField label="Words needed to interrupt" type="number" value={String(cfg.voice.interruption_min_words ?? 0)} onChange={(v) => set("voice.interruption_min_words", Number(v))} hint="0 = any speech interrupts. 2+ ignores coughs and 'hmm' on noisy lines." />
            <SwitchRow label="Instant fillers" hint="Plays a pre-recorded 'One moment…' while a tool runs, so there is never dead air." checked={cfg.voice.filler_words !== false} onChange={(v) => set("voice.filler_words", v)} />
            <SwitchRow label="Background noise suppression" hint="RNNoise on phone audio (markets, traffic, fans)." checked={cfg.voice.noise_filter !== false} onChange={(v) => set("voice.noise_filter", v)} />
            <Field label="Who speaks first">
              <Select value={cfg.voice.first_speaker} onValueChange={(v) => set("voice.first_speaker", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="agent">Agent greets first</SelectItem>
                  <SelectItem value="user">Wait for the caller</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Speech-to-text">
              <Select value={cfg.voice.stt_provider} onValueChange={(v) => set("voice.stt_provider", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto (Groq Whisper → local)</SelectItem>
                  <SelectItem value="groq">Groq Whisper large-v3-turbo</SelectItem>
                  <SelectItem value="deepgram">Deepgram Nova-3 multilingual (BYOK)</SelectItem>
                  <SelectItem value="deepgram_flux">Deepgram Flux: streaming + predictive end-of-turn (BYOK)</SelectItem>
                  <SelectItem value="sarvam">Sarvam Saaras: 22 Indian languages, code-mixed (BYOK)</SelectItem>
                  <SelectItem value="openai">OpenAI (BYOK)</SelectItem>
                  <SelectItem value="whisper_local">Local Whisper (offline)</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <TextField label="Silence timeout (s)" type="number" value={String(cfg.voice.silence_timeout_s ?? 25)} onChange={(v) => set("voice.silence_timeout_s", Number(v))} />
              <TextField label="Max call (min)" type="number" value={String(cfg.voice.max_call_minutes ?? 15)} onChange={(v) => set("voice.max_call_minutes", Number(v))} />
            </div>
            <ListField label="Keywords to recognise" hint="Brand names, products, doctor names: improves transcription accuracy." values={cfg.voice.keywords || []} onChange={(v) => set("voice.keywords", v)} placeholder="e.g. BrightSmile" />
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="Outbound calling" description="Voicemail and phone-menu behaviour for calls the agent places.">
            <SwitchRow label="Detect voicemail" hint="Carrier answering-machine detection + spoken cues ('leave a message after the beep', 'abhi vyast hai')." checked={cfg.voice.voicemail?.detect !== false} onChange={(v) => set("voice.voicemail", { ...(cfg.voice.voicemail || {}), detect: v })} />
            <Field label="When voicemail answers">
              <Select value={cfg.voice.voicemail?.action || "leave_message"} onValueChange={(v) => set("voice.voicemail", { ...(cfg.voice.voicemail || {}), action: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="leave_message">Leave a message, then hang up</SelectItem>
                  <SelectItem value="hangup">Hang up silently (retry later)</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            {(cfg.voice.voicemail?.action || "leave_message") === "leave_message" && (
              <AreaField label="Voicemail message" rows={3} value={cfg.voice.voicemail?.message} onChange={(v) => set("voice.voicemail", { ...(cfg.voice.voicemail || {}), message: v })} />
            )}
            <SwitchRow label="Navigate phone menus (IVR)" hint="Lets the agent press keypad keys when it reaches an automated menu." checked={!!cfg.voice.ivr_navigation} onChange={(v) => set("voice.ivr_navigation", v)} />
          </Section>
        </Card>
      </div>
    </div>
  );
}

export function KnowledgeForm({ cfg, set, agentId, kbIds, setKbIds }: FormProps & { agentId: string; kbIds: string[]; setKbIds: (v: string[]) => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const { data: kbs } = useQuery({ queryKey: ["kbs"], queryFn: () => api.get("/knowledge/bases") });
  const { data: answers } = useQuery({ queryKey: ["answers", agentId], queryFn: () => api.get(`/agents/${agentId}/answers`) });
  const [q, setQ] = useState("");
  const [a, setA] = useState("");
  const addAnswer = useMutation({
    mutationFn: () => api.post(`/agents/${agentId}/answers`, { question: q, answer: a }),
    onSuccess: () => {
      setQ("");
      setA("");
      qc.invalidateQueries({ queryKey: ["answers", agentId] });
      toast.success("Approved answer added");
    },
  });
  const delAnswer = useMutation({ mutationFn: (id: string) => api.del(`/agents/${agentId}/answers/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["answers", agentId] }) });
  const policies: any[] = cfg.knowledge.policies || [];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-4 p-5">
        <Section title="Knowledge bases" description="Shared across agents. Manage documents on the Knowledge page." actions={<Button asChild size="sm" variant="outline"><Link href="/app/knowledge">Manage</Link></Button>}>
          <div className="space-y-2">
            {(kbs?.items || []).map((kb: any) => (
              <label key={kb.id} className="flex items-center gap-3 rounded-lg border p-3">
                <Checkbox checked={kbIds.includes(kb.id)} onCheckedChange={(c) => setKbIds(c ? [...kbIds, kb.id] : kbIds.filter((x) => x !== kb.id))} />
                <div className="flex-1">
                  <p className="text-sm font-medium">{kb.name}</p>
                  <p className="text-xs text-muted-foreground">{kb.sources} sources · {kb.chunks} chunks</p>
                </div>
              </label>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Retrieval mode">
              <Select value={cfg.knowledge.mode} onValueChange={(v) => set("knowledge.mode", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto (fast for voice, deep for chat)</SelectItem>
                  <SelectItem value="fast">Fast hybrid</SelectItem>
                  <SelectItem value="deep">Deep + rerank</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <TextField label="Chunks per answer" type="number" value={String(cfg.knowledge.k)} onChange={(v) => set("knowledge.k", Number(v))} />
          </div>
          <SliderField label="Minimum confidence" value={Math.round((cfg.knowledge.min_confidence ?? 0.32) * 100)} onChange={(v) => set("knowledge.min_confidence", v / 100)} format={(v) => (v / 100).toFixed(2)} left="Answer more" right="Only when sure" />
          <SwitchRow label="Cite sources" hint="Shows which document an answer came from." checked={cfg.knowledge.cite_sources} onChange={(v) => set("knowledge.cite_sources", v)} />
        </Section>
      </Card>
      <Card className="gap-4 p-5">
        <Section title="Retrieval policies" description="Boost or suppress content: restrict ×0.05, require ×2, allow ×1.">
          {policies.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              <Select value={p.action} onValueChange={(v) => set("knowledge.policies", policies.map((x, j) => (j === i ? { ...x, action: v } : x)))}>
                <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="restrict">Restrict</SelectItem>
                  <SelectItem value="require">Prefer</SelectItem>
                  <SelectItem value="allow">Allow</SelectItem>
                </SelectContent>
              </Select>
              <Select value={p.match} onValueChange={(v) => set("knowledge.policies", policies.map((x, j) => (j === i ? { ...x, match: v } : x)))}>
                <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="topic">Topic</SelectItem>
                  <SelectItem value="source">Source</SelectItem>
                </SelectContent>
              </Select>
              <Input value={p.target} onChange={(e) => set("knowledge.policies", policies.map((x, j) => (j === i ? { ...x, target: e.target.value } : x)))} placeholder="e.g. 2023 price list" />
              <Button size="icon" variant="ghost" onClick={() => set("knowledge.policies", policies.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
            </div>
          ))}
          <Button size="sm" variant="outline" onClick={() => set("knowledge.policies", [...policies, { action: "restrict", match: "topic", target: "" }])}>
            <Plus className="size-4" /> Add rule
          </Button>
        </Section>
        <Section title="Approved answers" description="Exact answers the agent should give. The improve loop adds to these too.">
          <div className="space-y-2">
            <Input placeholder="Question" value={q} onChange={(e) => setQ(e.target.value)} />
            <Input placeholder="Approved answer" value={a} onChange={(e) => setA(e.target.value)} />
            <Button size="sm" disabled={!q || !a || addAnswer.isPending} onClick={() => addAnswer.mutate()}>Add answer</Button>
          </div>
          <div className="max-h-64 space-y-1.5 overflow-y-auto">
            {(answers?.items || []).map((g: any) => (
              <div key={g.id} className="rounded-md border p-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{g.question}</p>
                  <div className="flex items-center gap-1">
                    <Badge variant="outline" className="text-[10px]">{g.source}</Badge>
                    <button onClick={() => delAnswer.mutate(g.id)} className="text-muted-foreground hover:text-destructive"><Trash2 className="size-3.5" /></button>
                  </div>
                </div>
                <p className="mt-1 text-muted-foreground">{g.answer}</p>
              </div>
            ))}
          </div>
        </Section>
      </Card>
    </div>
  );
}

const BUILTIN_TOOLS = [
  ["search_knowledge", "Search knowledge", "Look up more information mid-conversation"],
  ["query_table", "Query spreadsheets", "SQL over uploaded CSV/Excel (orders, prices, stock)"],
  ["capture_lead", "Capture lead", "Save name, phone, email and interest to the CRM"],
  ["create_task", "Create task", "Follow-ups for your team"],
  ["check_availability", "Check availability", "Free slots on your booking calendar"],
  ["book_appointment", "Book appointment", "Book directly into your calendar"],
  ["send_message", "Send on another channel", "e.g. send a link on WhatsApp during a call"],
  ["handoff_to_human", "Hand off to human", "Transfer to your team with a brief"],
  ["end_conversation", "End conversation", "Hang up / close politely"],
  ["get_datetime", "Date & time", "Current time in your timezone"],
  ["send_payment_link", "Collect payments", "Razorpay / Stripe payment link via WhatsApp, SMS or email"],
];

export function ToolsForm({ cfg, set }: FormProps) {
  const api = useApi();
  const { data: tools } = useQuery({ queryKey: ["tools"], queryFn: () => api.get("/tools") });
  const enabled: string[] = cfg.tools.builtin || [];
  const custom: string[] = cfg.tools.custom_tool_ids || [];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-3 p-5">
        <Section title="Built-in tools" description="Work on every channel, including voice calls.">
          {BUILTIN_TOOLS.map(([id, label, hint]) => (
            <SwitchRow key={id} label={label} hint={hint} checked={enabled.includes(id)} onChange={(on) => set("tools.builtin", on ? [...enabled, id] : enabled.filter((t) => t !== id))} />
          ))}
        </Section>
      </Card>
      <Card className="gap-3 p-5">
        <Section title="Your tools" description="HTTP APIs and MCP servers from Integrations." actions={<Button asChild size="sm" variant="outline"><Link href="/app/integrations">Add tool</Link></Button>}>
          {(tools?.items || []).length === 0 && <p className="text-sm text-muted-foreground">No custom tools yet. Connect any REST API or MCP server in Integrations.</p>}
          {(tools?.items || []).map((t: any) => (
            <SwitchRow key={t.id} label={`${t.name} (${t.type})`} hint={t.description} checked={custom.includes(t.id)} onChange={(on) => set("tools.custom_tool_ids", on ? [...custom, t.id] : custom.filter((x) => x !== t.id))} />
          ))}
        </Section>
      </Card>
    </div>
  );
}

export function HandoffForm({ cfg, set }: FormProps) {
  const h = cfg.handoff;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-3 p-5">
        <Section title="Human handoff" description="When the agent should bring in your team.">
          <SwitchRow label="Enable handoff" checked={h.enabled} onChange={(v) => set("handoff.enabled", v)} />
          <SwitchRow label="When the customer asks for a person" hint="Detected in English, Hindi and Hinglish." checked={h.explicit_request} onChange={(v) => set("handoff.explicit_request", v)} />
          <SwitchRow label="When the customer is frustrated" checked={h.frustration} onChange={(v) => set("handoff.frustration", v)} />
          <div className="grid grid-cols-2 gap-3">
            <TextField label="After N unsure answers in a row" type="number" value={String(h.low_confidence_turns)} onChange={(v) => set("handoff.low_confidence_turns", Number(v))} />
            <TextField label="After the same question N times" type="number" value={String(h.repeat_question)} onChange={(v) => set("handoff.repeat_question", Number(v))} />
          </div>
          <ListField label="Always hand off for these topics" values={h.topics || []} onChange={(v) => set("handoff.topics", v)} placeholder="e.g. refund over ₹10,000" />
          <AreaField label="Message while connecting" rows={2} value={h.message} onChange={(v) => set("handoff.message", v)} />
          <TextField label="Team to route to" value={h.team} onChange={(v) => set("handoff.team", v)} />
        </Section>
      </Card>
      <div className="space-y-6">
        <Card className="gap-3 p-5">
          <Section title="Memory" description="Remember people across every channel.">
            <SwitchRow label="Cross-channel memory" hint="Use past conversations on any channel for context." checked={cfg.memory.cross_channel} onChange={(v) => set("memory.cross_channel", v)} />
            <SwitchRow label="Remember facts" hint="Extract durable facts (preferences, commitments, details) after conversations." checked={cfg.memory.remember_facts} onChange={(v) => set("memory.remember_facts", v)} />
          </Section>
        </Card>
        <Card className="gap-3 p-5">
          <Section title="Guardrails & privacy">
            <ListField label="Never discuss" values={cfg.guardrails.blocked_topics || []} onChange={(v) => set("guardrails.blocked_topics", v)} placeholder="e.g. competitors' pricing" />
            <SwitchRow label="Redact PII in stored transcripts" hint="Cards, Aadhaar, PAN, phone numbers and emails are masked." checked={cfg.guardrails.pii_redaction} onChange={(v) => set("guardrails.pii_redaction", v)} />
            <SliderField label="Prompt-injection sensitivity" value={Math.round((1 - (cfg.guardrails.injection_threshold ?? 0.85)) * 100)} min={2} max={40} onChange={(v) => set("guardrails.injection_threshold", 1 - v / 100)} left="Lenient" right="Strict" />
          </Section>
        </Card>
      </div>
    </div>
  );
}

export function AnalysisForm({ cfg, set }: FormProps) {
  const fields: any[] = cfg.analysis.extraction || [];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-3 p-5">
        <Section title="Data to extract after each conversation" description="Fills CRM fields automatically and goes to your webhooks.">
          {fields.map((f, i) => (
            <div key={i} className="grid grid-cols-[1fr_110px_1.6fr_auto] gap-2">
              <Input value={f.name} placeholder="field_name" onChange={(e) => set("analysis.extraction", fields.map((x, j) => (j === i ? { ...x, name: e.target.value.replace(/\s+/g, "_") } : x)))} />
              <Select value={f.type} onValueChange={(v) => set("analysis.extraction", fields.map((x, j) => (j === i ? { ...x, type: v } : x)))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="string">Text</SelectItem>
                  <SelectItem value="number">Number</SelectItem>
                  <SelectItem value="boolean">Yes/No</SelectItem>
                </SelectContent>
              </Select>
              <Input value={f.description} placeholder="What to capture" onChange={(e) => set("analysis.extraction", fields.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} />
              <Button size="icon" variant="ghost" onClick={() => set("analysis.extraction", fields.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
            </div>
          ))}
          <Button size="sm" variant="outline" onClick={() => set("analysis.extraction", [...fields, { name: "", type: "string", description: "" }])}>
            <Plus className="size-4" /> Add field
          </Button>
        </Section>
      </Card>
      <Card className="gap-3 p-5">
        <Section title="Outcomes (dispositions)" description="The analysis picks one per conversation.">
          <ListField label="Dispositions" values={cfg.analysis.dispositions || []} onChange={(v) => set("analysis.dispositions", v)} placeholder="e.g. appointment_booked" />
          <SwitchRow label="Auto-update CRM" hint="Write extracted fields, tags, lead score, deals and follow-up tasks to the contact." checked={cfg.analysis.auto_crm} onChange={(v) => set("analysis.auto_crm", v)} />
          <SwitchRow label="Conversation summary" checked={cfg.analysis.summary} onChange={(v) => set("analysis.summary", v)} />
        </Section>
      </Card>
    </div>
  );
}

export function VersionsPanel({ agentId, onRestore }: { agentId: string; onRestore: () => void }) {
  const api = useApi();
  const { data } = useQuery({ queryKey: ["versions", agentId], queryFn: () => api.get(`/agents/${agentId}/versions`) });
  const restore = useMutation({
    mutationFn: (v: number) => api.post(`/agents/${agentId}/versions/${v}/restore`),
    onSuccess: () => {
      toast.success("Version restored into the draft", { description: "Publish to make it live." });
      onRestore();
    },
  });
  return (
    <Card className="gap-0 p-0">
      {(data?.items || []).length === 0 && <p className="p-6 text-sm text-muted-foreground">No published versions yet.</p>}
      {(data?.items || []).map((v: any, i: number) => (
        <div key={v.id} className="flex items-center gap-3 border-b px-5 py-3 last:border-0">
          <span className="grid size-8 place-items-center rounded-full bg-muted font-mono text-xs">v{v.version}</span>
          <div className="flex-1">
            <p className="text-sm">{v.notes || "Published"}</p>
            <p className="text-xs text-muted-foreground">{new Date(v.created_at).toLocaleString()} · {v.created_by}</p>
          </div>
          {i === 0 && <StatusBadge status="live" />}
          <Button size="sm" variant="outline" onClick={() => restore.mutate(v.version)}>Restore to draft</Button>
        </div>
      ))}
    </Card>
  );
}

export { getPath };
