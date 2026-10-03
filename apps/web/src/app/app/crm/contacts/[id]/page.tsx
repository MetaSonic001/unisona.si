"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Brain, Calendar, CheckSquare, KanbanSquare, Plus, StickyNote, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { ChannelBadge, LoadingBlock, Section, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { duration, initials, money, timeAgo } from "@/lib/format";

export default function ContactPage() {
  const { id } = useParams<{ id: string }>();
  const api = useApi();
  const qc = useQueryClient();
  const router = useRouter();
  const { data, isLoading } = useQuery({ queryKey: ["contact", id], queryFn: () => api.get(`/crm/contacts/${id}`) });
  const [note, setNote] = useState("");
  const [fact, setFact] = useState("");
  const [tag, setTag] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["contact", id] });
  const update = useMutation({ mutationFn: (b: any) => api.patch(`/crm/contacts/${id}`, b), onSuccess: refresh });
  const addNote = useMutation({ mutationFn: () => api.post("/crm/notes", { contact_id: id, body: note }), onSuccess: () => { setNote(""); refresh(); } });
  const addTask = useMutation({ mutationFn: (title: string) => api.post("/crm/tasks", { contact_id: id, title }), onSuccess: refresh });
  const addFact = useMutation({ mutationFn: () => api.post(`/crm/contacts/${id}/facts`, { fact }), onSuccess: () => { setFact(""); refresh(); } });
  const forget = useMutation({ mutationFn: (fid: string) => api.del(`/crm/contacts/${id}/facts/${fid}`), onSuccess: refresh });
  const erase = useMutation({ mutationFn: () => api.del(`/crm/contacts/${id}`), onSuccess: () => { toast.success("Contact and all their data erased"); router.push("/app/crm/contacts"); } });
  if (isLoading || !data) return <LoadingBlock />;
  const c = data.contact;

  return (
    <div className="grid gap-6 p-6 xl:grid-cols-[320px_1fr_320px]">
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm"><Link href="/app/crm/contacts"><ArrowLeft className="size-4" /> Contacts</Link></Button>
        <Card className="items-center gap-2 p-5 text-center">
          <span className="grid size-16 place-items-center rounded-full bg-gradient-to-br from-brand to-[oklch(0.7_0.15_220)] text-xl font-semibold text-white">{initials(c.name || c.phone)}</span>
          <Input className="text-center font-semibold" defaultValue={c.name || ""} onBlur={(e) => e.target.value !== c.name && update.mutate({ name: e.target.value })} />
          <p className="text-xs text-muted-foreground">{c.phone} {c.email && `· ${c.email}`}</p>
          <div className="flex flex-wrap justify-center gap-1">{data.channels.map((ch: string) => <ChannelBadge key={ch} channel={ch} />)}</div>
        </Card>
        <Card className="gap-3 p-4">
          <div className="grid grid-cols-2 gap-2">
            <div><p className="text-xs text-muted-foreground">Stage</p>
              <Select value={c.lifecycle} onValueChange={(v) => update.mutate({ lifecycle: v })}>
                <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                <SelectContent>{["lead", "qualified", "customer", "churned"].map((s) => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div><p className="text-xs text-muted-foreground">Lead score</p><p className="text-2xl font-semibold tabular-nums">{c.score}</p></div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">Tags</p>
            <div className="flex flex-wrap gap-1">
              {c.tags.map((t: string) => <Badge key={t} variant="secondary" className="cursor-pointer" onClick={() => update.mutate({ tags: c.tags.filter((x: string) => x !== t) })}>{t} ×</Badge>)}
              <Input className="h-6 w-24 text-xs" placeholder="+ tag" value={tag} onChange={(e) => setTag(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && tag) { update.mutate({ tags: [...c.tags, tag] }); setTag(""); } }} />
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">Identities (linked across channels)</p>
            {data.identities.map((i: any) => <p key={i.id} className="font-mono text-[11px]">{i.type}: {i.value} {i.verified && "✓"}</p>)}
          </div>
          {Object.keys(c.fields || {}).length > 0 && (
            <div><p className="mb-1 text-xs text-muted-foreground">Fields</p>
              {Object.entries(c.fields).map(([k, v]: any) => <p key={k} className="text-xs"><span className="text-muted-foreground">{k}:</span> {String(v)}</p>)}
            </div>
          )}
          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => confirm("Erase this contact and all their conversations? (DPDP/GDPR right to erasure)") && erase.mutate()}><Trash2 className="size-3.5" /> Erase all data</Button>
        </Card>
      </div>

      <div className="space-y-4">
        {c.summary && <Card className="gap-1 bg-brand-soft/30 p-4"><p className="text-xs font-semibold text-brand">AI summary</p><p className="text-sm">{c.summary}</p></Card>}
        <Card className="gap-3 p-4">
          <Textarea rows={2} placeholder="Add a note… (@mention teammates)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <Button size="sm" disabled={!note} onClick={() => addNote.mutate()}><StickyNote className="size-3.5" /> Add note</Button>
            <Button size="sm" variant="outline" onClick={() => { const t = prompt("Task title"); if (t) addTask.mutate(t); }}><CheckSquare className="size-3.5" /> Add task</Button>
          </div>
        </Card>
        <Section title="Timeline" description="Every conversation, call, AI action and note, across all channels.">
          <div className="relative space-y-3 before:absolute before:bottom-2 before:left-[15px] before:top-2 before:w-px before:bg-border">
            {data.timeline.map((t: any) => (
              <div key={t.type + t.id} className="relative flex gap-3">
                <span className="relative z-10 mt-1 grid size-8 shrink-0 place-items-center rounded-full border bg-background text-[10px]">
                  {t.type === "conversation" ? "💬" : t.type === "note" ? "📝" : t.kind?.includes("appointment") ? "📅" : t.kind?.includes("lead") ? "⭐" : "⚡"}
                </span>
                <Card className="flex-1 gap-1 p-3">
                  {t.type === "conversation" ? (
                    <Link href={`/app/inbox?c=${t.id}`} className="block">
                      <div className="flex items-center gap-2"><ChannelBadge channel={t.channel} /><StatusBadge status={t.status} />{t.outcome && <Badge variant="outline" className="text-[10px]">{t.outcome.replaceAll("_", " ")}</Badge>}{t.call && <span className="text-[11px] text-muted-foreground">📞 {duration(t.call.duration_s)}</span>}<span className="ml-auto text-[11px] text-muted-foreground">{timeAgo(t.at)}</span></div>
                      <p className="mt-1 text-sm">{t.summary || `${t.messages} messages`}</p>
                    </Link>
                  ) : (
                    <>
                      <div className="flex items-center justify-between"><p className="text-sm">{t.title}</p><span className="text-[11px] text-muted-foreground">{timeAgo(t.at)}</span></div>
                      <p className="text-[11px] text-muted-foreground">{t.actor}</p>
                    </>
                  )}
                </Card>
              </div>
            ))}
          </div>
        </Section>
      </div>

      <div className="space-y-4">
        <Card className="gap-2 p-4">
          <p className="flex items-center gap-1.5 text-sm font-semibold"><Brain className="size-4 text-brand" /> Memory</p>
          <p className="text-xs text-muted-foreground">Facts the agent uses on every channel. Corrected facts close the old ones.</p>
          {data.facts.map((f: any) => (
            <div key={f.id} className={`flex items-start gap-2 rounded-md bg-muted/40 px-2 py-1.5 text-xs ${f.valid_to ? "line-through opacity-50" : ""}`}>
              <span className="flex-1">{f.fact}<span className="ml-1 text-muted-foreground">· {f.source_channel}</span></span>
              <button onClick={() => forget.mutate(f.id)} className="text-muted-foreground hover:text-destructive"><Trash2 className="size-3" /></button>
            </div>
          ))}
          <div className="flex gap-1.5"><Input className="h-8 text-xs" placeholder="Add a fact" value={fact} onChange={(e) => setFact(e.target.value)} /><Button size="sm" className="h-8" disabled={!fact} onClick={() => addFact.mutate()}><Plus className="size-3.5" /></Button></div>
        </Card>
        <Card className="gap-2 p-4">
          <p className="flex items-center gap-1.5 text-sm font-semibold"><KanbanSquare className="size-4" /> Deals</p>
          {data.deals.length === 0 && <p className="text-xs text-muted-foreground">No deals.</p>}
          {data.deals.map((d: any) => <div key={d.id} className="rounded-md border p-2 text-xs"><p className="font-medium">{d.title}</p><p className="text-muted-foreground">{d.stage} · {money(d.value, d.currency)}</p></div>)}
        </Card>
        <Card className="gap-2 p-4">
          <p className="flex items-center gap-1.5 text-sm font-semibold"><CheckSquare className="size-4" /> Tasks</p>
          {data.tasks.map((t: any) => <p key={t.id} className={`text-xs ${t.status === "done" ? "line-through text-muted-foreground" : ""}`}>• {t.title} {t.created_by === "ai" && <Badge variant="secondary" className="h-4 text-[9px]">AI</Badge>}</p>)}
        </Card>
        <Card className="gap-2 p-4">
          <p className="flex items-center gap-1.5 text-sm font-semibold"><Calendar className="size-4" /> Appointments</p>
          {data.appointments.map((a: any) => <p key={a.id} className="text-xs">{new Date(a.start_at).toLocaleString()} · {a.status}</p>)}
          {data.appointments.length === 0 && <p className="text-xs text-muted-foreground">None.</p>}
        </Card>
      </div>
    </div>
  );
}
