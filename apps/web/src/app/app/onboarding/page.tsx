"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, FileUp, Globe, KeyRound, Link2, Loader2, Mic, PhoneOff, Play, Rocket, Send, Sparkles, Upload, Wand2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Logo } from "@/components/brand";
import { StatusBadge } from "@/components/common";
import { VoiceOrb } from "@/components/orb";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { API_URL } from "@/lib/env";
import { useVoiceCall } from "@/lib/voice";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/utils";

const STEPS = ["Your business", "Knowledge", "Voice & personality", "Go live"];
const PROGRESS_LINES = ["Reading your homepage…", "Finding pricing, FAQs and contact pages…", "Understanding what you offer…", "Drafting your agent's personality…", "Writing starter answers from your content…"];

export default function OnboardingPage() {
  const api = useApi();
  const qc = useQueryClient();
  const router = useRouter();
  const { me, refetch } = useWorkspace();
  const [step, setStep] = useState(0);
  const [url, setUrl] = useState("");
  const [profile, setProfile] = useState<any>(null);
  const [template, setTemplate] = useState<string>("customer-support");
  const [progressLine, setProgressLine] = useState(0);
  const [created, setCreated] = useState<{ agent_id: string; kb_id: string; public_key: string } | null>(null);
  const [groqKey, setGroqKey] = useState("");

  const { data: templates } = useQuery({ queryKey: ["templates"], queryFn: () => api.get("/templates") });
  const analyze = useMutation({
    mutationFn: () => api.post("/onboarding/analyze", { url }),
    onSuccess: (p) => {
      setProfile(p);
      if (p.templates?.[0]) setTemplate(p.templates[0]);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  useEffect(() => {
    if (!analyze.isPending) return;
    setProgressLine(0);
    const t = setInterval(() => setProgressLine((l) => Math.min(l + 1, PROGRESS_LINES.length - 1)), 4500);
    return () => clearInterval(t);
  }, [analyze.isPending]);

  const saveKey = useMutation({
    mutationFn: () => api.put("/providers/groq", { api_key: groqKey }),
    onSuccess: (r) => {
      if (r.status === "valid") {
        toast.success("Groq key works");
        refetch();
      } else toast.error(r.error || "That key didn't work");
    },
  });

  const apply = useMutation({
    mutationFn: (overrides: any) =>
      api.post("/onboarding/apply", {
        profile: profile || { business: { name: me?.workspace.name, website: url }, agent: {} },
        template_id: template,
        url,
        ...overrides,
      }),
    onSuccess: (r) => {
      setCreated(r);
      qc.invalidateQueries({ queryKey: ["agents"] });
      refetch();
      setStep(1);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const skip = async () => {
    await api.patch("/workspace", { onboarding: { skipped: true } });
    await refetch();
    router.push("/app/agents?new=1");
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-soft/40 via-background to-background">
      <header className="flex items-center justify-between px-6 py-4">
        <Logo />
        <div className="hidden items-center gap-2 md:flex">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <span className={cn("grid size-6 place-items-center rounded-full text-[11px] font-semibold", i < step ? "bg-success text-white" : i === step ? "bg-brand text-brand-foreground" : "bg-muted text-muted-foreground")}>
                {i < step ? <Check className="size-3.5" /> : i + 1}
              </span>
              <span className={cn("text-sm", i === step ? "font-medium" : "text-muted-foreground")}>{s}</span>
              {i < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-border" />}
            </div>
          ))}
        </div>
        <Button variant="ghost" size="sm" onClick={skip}>Skip setup</Button>
      </header>

      <main className="mx-auto max-w-3xl px-5 pb-20 pt-6">
        <AnimatePresence mode="wait">
          {step === 0 && (
            <motion.div key="s0" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} className="space-y-6">
              <div className="text-center">
                <h1 className="font-display text-4xl tracking-tight sm:text-5xl">What does your business do?</h1>
                <p className="mt-3 text-muted-foreground">Paste your website. We&apos;ll read it and draft an agent that already knows your business.</p>
              </div>
              {me && !me.ai_ready && (
                <Card className="gap-3 border-warning/40 bg-warning/5 p-4">
                  <p className="flex items-center gap-2 text-sm font-medium"><KeyRound className="size-4 text-warning" /> First, connect an AI provider (free)</p>
                  <p className="text-xs text-muted-foreground">Get a free key at <a className="text-brand underline" href="https://console.groq.com/keys" target="_blank" rel="noreferrer">console.groq.com/keys</a>. You can add Gemini, OpenAI or Claude later.</p>
                  <div className="flex gap-2">
                    <Input placeholder="gsk_…" value={groqKey} onChange={(e) => setGroqKey(e.target.value)} />
                    <Button onClick={() => saveKey.mutate()} disabled={!groqKey || saveKey.isPending}>{saveKey.isPending ? <Loader2 className="size-4 animate-spin" /> : "Validate"}</Button>
                  </div>
                </Card>
              )}
              <Card className="gap-4 p-5">
                <form
                  className="flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (url) analyze.mutate();
                  }}
                >
                  <div className="relative flex-1">
                    <Globe className="absolute left-3 top-3 size-4 text-muted-foreground" />
                    <Input className="h-10 pl-9" placeholder="yourbusiness.com" value={url} onChange={(e) => setUrl(e.target.value)} />
                  </div>
                  <Button type="submit" className="h-10 bg-brand text-brand-foreground hover:bg-brand/90" disabled={!url || analyze.isPending}>
                    {analyze.isPending ? <Loader2 className="size-4 animate-spin" /> : <Wand2 className="size-4" />} Build my agent
                  </Button>
                </form>
                {analyze.isPending && (
                  <div className="flex items-center gap-4 rounded-xl border bg-muted/30 p-4">
                    <VoiceOrb state="thinking" size={64} />
                    <div>
                      <p className="text-sm font-medium">{PROGRESS_LINES[progressLine]}</p>
                      <p className="text-xs text-muted-foreground">This usually takes 20–60 seconds.</p>
                    </div>
                  </div>
                )}
              </Card>

              {profile && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
                  <Card className="gap-4 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium uppercase tracking-wide text-brand">We read {profile.pages?.length || 0} pages</p>
                        <Input className="mt-2 h-10 text-lg font-semibold" value={profile.business?.name || ""} onChange={(e) => setProfile({ ...profile, business: { ...profile.business, name: e.target.value } })} />
                      </div>
                      <Badge variant="secondary">{profile.business?.industry}</Badge>
                    </div>
                    <Textarea rows={2} value={profile.business?.description || ""} onChange={(e) => setProfile({ ...profile, business: { ...profile.business, description: e.target.value } })} />
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label className="text-xs">Agent name</Label>
                        <Input value={profile.agent?.name || ""} onChange={(e) => setProfile({ ...profile, agent: { ...profile.agent, name: e.target.value } })} />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">Greeting</Label>
                        <Input value={profile.agent?.greeting || ""} onChange={(e) => setProfile({ ...profile, agent: { ...profile.agent, greeting: e.target.value } })} />
                      </div>
                    </div>
                    {profile.faqs?.length > 0 && (
                      <div className="rounded-lg border bg-muted/20 p-3">
                        <p className="text-xs font-medium">{profile.faqs.length} starter answers found</p>
                        <ul className="mt-1.5 space-y-1 text-xs text-muted-foreground">
                          {profile.faqs.slice(0, 4).map((f: any) => <li key={f.question}>• {f.question}</li>)}
                        </ul>
                      </div>
                    )}
                  </Card>
                  <TemplatePicker templates={templates?.items || []} suggested={profile.templates || []} value={template} onChange={setTemplate} />
                  <div className="flex justify-end">
                    <Button size="lg" className="bg-brand text-brand-foreground hover:bg-brand/90" disabled={apply.isPending} onClick={() => apply.mutate({})}>
                      {apply.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />} Create my agent
                    </Button>
                  </div>
                </motion.div>
              )}
              {!profile && !analyze.isPending && (
                <div className="space-y-3">
                  <p className="text-center text-xs text-muted-foreground">No website? Pick what the agent is for and continue.</p>
                  <TemplatePicker templates={templates?.items || []} suggested={[]} value={template} onChange={setTemplate} />
                  <div className="flex justify-end">
                    <Button variant="outline" disabled={apply.isPending} onClick={() => apply.mutate({ profile: { business: { name: me?.workspace.name }, agent: {} } })}>
                      Continue without a website <ArrowRight className="size-4" />
                    </Button>
                  </div>
                </div>
              )}
            </motion.div>
          )}

          {step === 1 && created && <KnowledgeStep key="s1" kbId={created.kb_id} onNext={() => setStep(2)} onBack={() => setStep(0)} />}
          {step === 2 && created && <VoiceStep key="s2" agentId={created.agent_id} onNext={() => setStep(3)} onBack={() => setStep(1)} />}
          {step === 3 && created && <GoLiveStep key="s3" agentId={created.agent_id} publicKey={created.public_key} onBack={() => setStep(2)} />}
        </AnimatePresence>
      </main>
    </div>
  );
}

function TemplatePicker({ templates, suggested, value, onChange }: { templates: any[]; suggested: string[]; value: string; onChange: (v: string) => void }) {
  const ordered = [...templates].sort((a, b) => (suggested.includes(b.id) ? 1 : 0) - (suggested.includes(a.id) ? 1 : 0));
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {ordered.slice(0, 9).map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)} className={cn("rounded-xl border bg-card p-3 text-left transition", value === t.id ? "border-brand ring-2 ring-brand/20" : "hover:bg-muted/50")}>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">{t.name}</p>
            {suggested.includes(t.id) && <Badge className="bg-brand-soft text-[10px] text-brand">suggested</Badge>}
          </div>
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{t.description}</p>
        </button>
      ))}
    </div>
  );
}

function KnowledgeStep({ kbId, onNext, onBack }: { kbId: string; onNext: () => void; onBack: () => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [link, setLink] = useState("");
  const [text, setText] = useState("");
  const [drag, setDrag] = useState(false);
  const { data } = useQuery({ queryKey: ["sources", kbId], queryFn: () => api.get(`/knowledge/sources?kb_id=${kbId}`), refetchInterval: 2500 });
  const items = data?.items || [];
  const chunks = items.reduce((a: number, s: any) => a + (s.chunks || 0), 0);
  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    fd.append("kb_id", kbId);
    try {
      await api.upload("/knowledge/sources/upload", fd);
      qc.invalidateQueries({ queryKey: ["sources", kbId] });
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const add = async (body: any) => {
    try {
      await api.post("/knowledge/sources", { kb_id: kbId, ...body });
      qc.invalidateQueries({ queryKey: ["sources", kbId] });
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} className="space-y-5">
      <div className="text-center">
        <h1 className="font-display text-4xl tracking-tight">Teach it everything else.</h1>
        <p className="mt-3 text-muted-foreground">PDFs, Word, PowerPoint, Excel/CSV (price lists, orders), links or plain text. Spreadsheets become queryable tables.</p>
      </div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          upload(e.dataTransfer.files);
        }}
        onClick={() => fileRef.current?.click()}
        className={cn("flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed bg-card p-10 text-center transition", drag ? "border-brand bg-brand-soft/40" : "hover:border-brand/50")}
      >
        <FileUp className="size-8 text-brand" />
        <p className="font-medium">Drop files here or click to upload</p>
        <p className="text-xs text-muted-foreground">PDF, DOCX, PPTX, XLSX, CSV, TXT, MD · up to 25 MB each</p>
        <input ref={fileRef} type="file" multiple hidden onChange={(e) => upload(e.target.files)} accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,.md,.html" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="gap-2 p-4">
          <Label className="flex items-center gap-1.5 text-xs"><Link2 className="size-3.5" /> Add a page or a whole site</Label>
          <div className="flex gap-2">
            <Input placeholder="https://…" value={link} onChange={(e) => setLink(e.target.value)} />
            <Button variant="outline" disabled={!link} onClick={() => { add({ type: "url", uri: link }); setLink(""); }}>Page</Button>
            <Button variant="outline" disabled={!link} onClick={() => { add({ type: "website", uri: link, max_pages: 25 }); setLink(""); }}>Site</Button>
          </div>
        </Card>
        <Card className="gap-2 p-4">
          <Label className="text-xs">Paste text (policies, scripts, FAQs)</Label>
          <div className="flex gap-2">
            <Textarea rows={1} value={text} onChange={(e) => setText(e.target.value)} placeholder="Our refund policy is…" />
            <Button variant="outline" disabled={text.length < 5} onClick={() => { add({ type: "text", text, title: text.slice(0, 50) }); setText(""); }}>Add</Button>
          </div>
        </Card>
      </div>
      <Card className="gap-0 p-0">
        <div className="flex items-center justify-between border-b px-4 py-2.5">
          <p className="text-sm font-medium">{items.length} sources · {chunks} chunks indexed</p>
          {items.some((s: any) => ["pending", "processing"].includes(s.status)) && <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Loader2 className="size-3 animate-spin" /> indexing…</span>}
        </div>
        {items.length === 0 && <p className="p-4 text-sm text-muted-foreground">Nothing added yet. Your website is being read in the background if you entered one.</p>}
        {items.map((s: any) => (
          <div key={s.id} className="flex items-center gap-3 border-b px-4 py-2.5 text-sm last:border-0">
            {s.type === "website" || s.type === "url" ? <Globe className="size-4 text-muted-foreground" /> : <Upload className="size-4 text-muted-foreground" />}
            <span className="flex-1 truncate">{s.title}</span>
            <span className="text-xs text-muted-foreground">{s.chunks ? `${s.chunks} chunks` : s.meta?.progress || ""}</span>
            <StatusBadge status={s.status} />
          </div>
        ))}
      </Card>
      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}><ArrowLeft className="size-4" /> Back</Button>
        <Button className="bg-brand text-brand-foreground hover:bg-brand/90" onClick={onNext}>Continue <ArrowRight className="size-4" /></Button>
      </div>
    </motion.div>
  );
}

function VoiceStep({ agentId, onNext, onBack }: { agentId: string; onNext: () => void; onBack: () => void }) {
  const api = useApi();
  const { data: agent, refetch } = useQuery({ queryKey: ["agent", agentId], queryFn: () => api.get(`/agents/${agentId}`) });
  const { data: langs } = useQuery({ queryKey: ["languages"], queryFn: () => api.get("/languages") });
  const [lang, setLang] = useState("en-IN");
  const [tone, setTone] = useState(60);
  const [voice, setVoice] = useState<string>("edge:en-IN-NeerjaExpressiveNeural");
  const [supported, setSupported] = useState<string[]>(["en-IN", "hi-IN"]);
  const audio = useRef<HTMLAudioElement | null>(null);
  const call = useVoiceCall();
  const { data: voices } = useQuery({ queryKey: ["voices", lang, "edge"], queryFn: () => api.get(`/voices?locale=${lang}&engine=edge`) });
  useEffect(() => {
    if (agent) {
      setTone(agent.config.persona.tone ?? 60);
      setVoice(agent.config.voice.voice_id);
      setSupported(agent.config.languages.supported || ["en-IN"]);
    }
  }, [agent]);
  const save = async () => {
    const perLang: Record<string, string> = {};
    for (const l of supported) {
      const lg = (langs?.items || []).find((x: any) => x.code === l);
      if (lg && l !== supported[0]) perLang[l] = lg.female;
    }
    await api.patch(`/agents/${agentId}`, { config: { persona: { tone }, voice: { voice_id: voice, per_language: perLang }, languages: { primary: supported[0] || "en-IN", supported } } });
    await api.post(`/agents/${agentId}/publish`, { notes: "Onboarding" });
    refetch();
  };
  const talk = async () => {
    await save();
    const token = await api.token();
    call.start({ endpoint: `${API_URL}/voice/offer`, headers: { Authorization: `Bearer ${token}` }, requestData: { agent_id: agentId, use_draft: true } });
  };
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} className="space-y-5">
      <div className="text-center">
        <h1 className="font-display text-4xl tracking-tight">How should it sound?</h1>
        <p className="mt-3 text-muted-foreground">Natural neural voices that switch automatically with the customer&apos;s language.</p>
      </div>
      <Card className="gap-4 p-5">
        <div className="space-y-2">
          <Label className="text-xs">Languages your customers speak</Label>
          <div className="flex flex-wrap gap-1.5">
            {(langs?.items || []).slice(0, 16).map((l: any) => {
              const on = supported.includes(l.code);
              return (
                <button key={l.code} onClick={() => { setSupported(on ? supported.filter((x) => x !== l.code) : [...supported, l.code]); setLang(l.code); }}
                  className={cn("rounded-full border px-3 py-1 text-xs transition", on ? "border-brand bg-brand-soft text-brand" : "text-muted-foreground hover:bg-muted")}>
                  {l.native}
                </button>
              );
            })}
          </div>
        </div>
        <div className="space-y-2">
          <Label className="text-xs">Main voice ({lang})</Label>
          <div className="grid gap-2 sm:grid-cols-3">
            {(voices?.items || []).slice(0, 9).map((v: any) => (
              <button key={v.id} onClick={() => setVoice(v.id)} className={cn("flex items-center gap-2 rounded-lg border p-2.5 text-left text-sm", voice === v.id && "border-brand bg-brand-soft/40")}>
                <span
                  role="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    audio.current?.pause();
                    audio.current = new Audio(`${API_URL}/voices/preview?voice_id=${encodeURIComponent(v.id)}&locale=${lang}`);
                    audio.current.play();
                  }}
                  className="grid size-7 place-items-center rounded-full bg-muted hover:bg-brand-soft"
                >
                  <Play className="size-3" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-medium">{v.name}</span>
                  <span className="block text-[11px] text-muted-foreground">{v.gender}{v.multilingual ? " · multilingual" : ""}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <Label className="text-xs">Personality</Label>
          <Slider value={[tone]} onValueChange={([v]) => setTone(v)} />
          <div className="flex justify-between text-[11px] text-muted-foreground"><span>Professional</span><span>Friendly</span></div>
        </div>
      </Card>
      <Card className="flex-row items-center gap-5 p-5">
        <VoiceOrb level={call.level} state={call.active ? (call.state as any) : "idle"} size={110} />
        <div className="flex-1">
          <p className="font-medium">{call.active ? `Talking… (${call.state})` : "Talk to your agent now"}</p>
          <p className="text-sm text-muted-foreground">{call.error || "A real voice call in your browser. Ask about your business in any language."}</p>
        </div>
        {call.active ? (
          <Button variant="destructive" onClick={call.stop}><PhoneOff className="size-4" /> End</Button>
        ) : (
          <Button onClick={talk}><Mic className="size-4" /> Start call</Button>
        )}
      </Card>
      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}><ArrowLeft className="size-4" /> Back</Button>
        <Button className="bg-brand text-brand-foreground hover:bg-brand/90" onClick={async () => { call.stop(); await save(); onNext(); }}>Continue <ArrowRight className="size-4" /></Button>
      </div>
    </motion.div>
  );
}

function GoLiveStep({ agentId, publicKey, onBack }: { agentId: string; publicKey: string; onBack: () => void }) {
  const api = useApi();
  const router = useRouter();
  const { refetch } = useWorkspace();
  const [tg, setTg] = useState("");
  const [toggles, setToggles] = useState({ web: true, widget: true, voice: true });
  const embed = `<script src="${API_URL}/widget/widget.js" data-agent="${publicKey}" data-api="${API_URL}" async></script>`;
  const finish = async () => {
    for (const [type, enabled] of Object.entries(toggles)) await api.post(`/agents/${agentId}/channels`, { type, enabled });
    await api.patch("/workspace", { onboarding: { completed: true } });
    await refetch();
    router.push(`/app/agents/${agentId}?tab=overview`);
  };
  const connectTg = async () => {
    try {
      await api.post(`/agents/${agentId}/channels`, { type: "telegram", enabled: true, secret: { bot_token: tg } });
      toast.success("Telegram bot connected. Message it now!");
      setTg("");
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} className="space-y-5">
      <div className="text-center">
        <h1 className="font-display text-4xl tracking-tight">Where should it work?</h1>
        <p className="mt-3 text-muted-foreground">Same brain everywhere. Turn channels on now or anytime later.</p>
      </div>
      <Card className="gap-3 p-5">
        {([["web", "Web chat page", "A shareable link with chat + voice"], ["widget", "Website widget", "One script tag on your site"], ["voice", "Browser voice calls", "Talk from the widget or chat page"]] as const).map(([k, t, d]) => (
          <div key={k} className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <p className="text-sm font-medium">{t}</p>
              <p className="text-xs text-muted-foreground">{d}</p>
            </div>
            <Switch checked={toggles[k]} onCheckedChange={(v) => setToggles({ ...toggles, [k]: v })} />
          </div>
        ))}
        <div className="rounded-lg border p-3">
          <p className="flex items-center gap-1.5 text-sm font-medium"><Send className="size-4 text-ch-telegram" /> Telegram (optional)</p>
          <div className="mt-2 flex gap-2">
            <Input placeholder="Bot token from @BotFather" value={tg} onChange={(e) => setTg(e.target.value)} />
            <Button variant="outline" disabled={!tg} onClick={connectTg}>Connect</Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">WhatsApp and phone numbers can be connected from the agent&apos;s Channels tab.</p>
      </Card>
      <Card className="gap-3 p-5">
        <p className="flex items-center gap-2 text-sm font-medium"><CheckCircle2 className="size-4 text-success" /> Your agent is live</p>
        <code className="block break-all rounded-lg bg-muted p-3 font-mono text-[11px]">{embed}</code>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(embed); toast.success("Copied"); }}>Copy embed code</Button>
          <Button variant="outline" size="sm" asChild><Link href={`/chat/${publicKey}`} target="_blank">Open chat page</Link></Button>
        </div>
      </Card>
      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}><ArrowLeft className="size-4" /> Back</Button>
        <Button size="lg" className="bg-brand text-brand-foreground hover:bg-brand/90" onClick={finish}><Rocket className="size-4" /> Go to my agent</Button>
      </div>
    </motion.div>
  );
}
