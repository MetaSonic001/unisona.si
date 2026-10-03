"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ExternalLink, LayoutTemplate, Loader2, Plus, Save, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AreaField, Field, TextField } from "@/components/agent/fields";
import { EmptyState, LoadingBlock, PageHeader, Section } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const BLOCKS: Record<string, any> = {
  hero: { eyebrow: "", title: "Headline that sells", subtitle: "One line on why you're the best choice.", cta: "Book now" },
  features: { title: "Why choose us", items: [{ title: "Benefit", text: "Explain it." }] },
  text: { title: "About us", body: "" },
  testimonials: { title: "What customers say", items: [{ quote: "", name: "" }] },
  faq: { title: "FAQ", items: [{ q: "", a: "" }] },
  cta: { title: "Ready to get started?", subtitle: "", button: "Talk to us" },
  form: { title: "Get in touch", form_id: "" },
  booking: { title: "Book an appointment", slug: "" },
  chat: { public_key: "" },
};

function ItemsEditor({ items, keys, onChange }: { items: any[]; keys: string[]; onChange: (v: any[]) => void }) {
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="flex gap-2">
          {keys.map((k) => (
            <Input key={k} className={k === "text" || k === "a" || k === "quote" ? "flex-[2]" : "flex-1"} placeholder={k} value={it[k] || ""}
              onChange={(e) => onChange(items.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} />
          ))}
          <Button size="icon" variant="ghost" onClick={() => onChange(items.filter((_, j) => j !== i))}><Trash2 className="size-3.5" /></Button>
        </div>
      ))}
      <Button size="sm" variant="ghost" onClick={() => onChange([...items, Object.fromEntries(keys.map((k) => [k, ""]))])}><Plus className="size-3" /> item</Button>
    </div>
  );
}

function BlockEditor({ block, onChange, forms, calendars, agents }: { block: any; onChange: (b: any) => void; forms: any[]; calendars: any[]; agents: any[] }) {
  const p = block.props || {};
  const set = (k: string, v: any) => onChange({ ...block, props: { ...p, [k]: v } });
  switch (block.type) {
    case "features": return <><TextField label="Title" value={p.title} onChange={(v) => set("title", v)} /><ItemsEditor items={p.items || []} keys={["title", "text"]} onChange={(v) => set("items", v)} /></>;
    case "testimonials": return <><TextField label="Title" value={p.title} onChange={(v) => set("title", v)} /><ItemsEditor items={p.items || []} keys={["quote", "name"]} onChange={(v) => set("items", v)} /></>;
    case "faq": return <><TextField label="Title" value={p.title} onChange={(v) => set("title", v)} /><ItemsEditor items={p.items || []} keys={["q", "a"]} onChange={(v) => set("items", v)} /></>;
    case "text": return <><TextField label="Title" value={p.title} onChange={(v) => set("title", v)} /><AreaField label="Body" value={p.body} onChange={(v) => set("body", v)} /></>;
    case "form": return <><TextField label="Title" value={p.title} onChange={(v) => set("title", v)} /><Field label="Form"><Select value={p.form_id || ""} onValueChange={(v) => set("form_id", v)}><SelectTrigger><SelectValue placeholder="Choose form" /></SelectTrigger><SelectContent>{forms.map((f) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}</SelectContent></Select></Field></>;
    case "booking": return <><TextField label="Title" value={p.title} onChange={(v) => set("title", v)} /><Field label="Calendar"><Select value={p.slug || ""} onValueChange={(v) => set("slug", v)}><SelectTrigger><SelectValue placeholder="Choose calendar" /></SelectTrigger><SelectContent>{calendars.map((c) => <SelectItem key={c.id} value={c.slug}>{c.name}</SelectItem>)}</SelectContent></Select></Field></>;
    case "chat": return <Field label="AI agent (chat + voice bubble)"><Select value={p.public_key || ""} onValueChange={(v) => set("public_key", v)}><SelectTrigger><SelectValue placeholder="Choose agent" /></SelectTrigger><SelectContent>{agents.map((a) => <SelectItem key={a.id} value={a.public_key}>{a.name}</SelectItem>)}</SelectContent></Select></Field>;
    default:
      return <>{Object.keys(BLOCKS[block.type] || {}).map((k) => (k === "subtitle" || k === "body"
        ? <AreaField key={k} label={k} rows={2} value={p[k]} onChange={(v) => set(k, v)} />
        : <TextField key={k} label={k} value={p[k]} onChange={(v) => set(k, v)} />))}</>;
  }
}

function GenerateDialog({ onDone }: { onDone: (p: any) => void }) {
  const api = useApi();
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const { data: forms } = useQuery({ queryKey: ["forms"], queryFn: () => api.get("/forms") });
  const { data: cals } = useQuery({ queryKey: ["calendars"], queryFn: () => api.get("/crm/calendars") });
  const [v, setV] = useState({ agent_id: "", form_id: "", calendar_slug: "", brief: "", goal: "get enquiries and bookings" });
  const [open, setOpen] = useState(false);
  const gen = useMutation({ mutationFn: () => api.post("/pages/generate", { ...v, form_id: v.form_id || undefined, calendar_slug: v.calendar_slug || undefined }), onSuccess: (p) => { setOpen(false); onDone(p); toast.success("Page drafted. Review and publish."); }, onError: (e: Error) => toast.error(e.message) });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" className="bg-brand text-brand-foreground hover:bg-brand/90"><Sparkles className="size-3.5" /> Generate with AI</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Generate a landing page</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Field label="Business (from agent)"><Select value={v.agent_id} onValueChange={(x) => setV({ ...v, agent_id: x })}><SelectTrigger><SelectValue placeholder="Choose agent" /></SelectTrigger><SelectContent>{(agents?.items || []).map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="What's the page for?"><Textarea rows={3} placeholder="e.g. Diwali whitening offer for new patients in Indiranagar" value={v.brief} onChange={(e) => setV({ ...v, brief: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Lead form"><Select value={v.form_id} onValueChange={(x) => setV({ ...v, form_id: x })}><SelectTrigger><SelectValue placeholder="none" /></SelectTrigger><SelectContent>{(forms?.items || []).map((f: any) => <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>)}</SelectContent></Select></Field>
            <Field label="Booking calendar"><Select value={v.calendar_slug} onValueChange={(x) => setV({ ...v, calendar_slug: x })}><SelectTrigger><SelectValue placeholder="none" /></SelectTrigger><SelectContent>{(cals?.items || []).map((c: any) => <SelectItem key={c.id} value={c.slug}>{c.name}</SelectItem>)}</SelectContent></Select></Field>
          </div>
          <Button className="w-full" disabled={gen.isPending} onClick={() => gen.mutate()}>{gen.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />} Generate page</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function SitesPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["pages"], queryFn: () => api.get("/pages") });
  const { data: forms } = useQuery({ queryKey: ["forms"], queryFn: () => api.get("/forms") });
  const { data: cals } = useQuery({ queryKey: ["calendars"], queryFn: () => api.get("/crm/calendars") });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const [sel, setSel] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { if (!sel && data?.items?.[0]) setSel(data.items[0]); }, [data, sel]);
  const create = useMutation({ mutationFn: () => api.post("/pages", { name: "New page", blocks: [{ id: `b${Date.now()}`, type: "hero", props: BLOCKS.hero }] }), onSuccess: (p) => { qc.invalidateQueries({ queryKey: ["pages"] }); setSel(p); } });
  const save = useMutation({ mutationFn: () => api.patch(`/pages/${sel.id}`, { name: sel.name, blocks: sel.blocks, seo: sel.seo, theme: sel.theme, published: sel.published }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["pages"] }); toast.success("Page saved"); }, onError: (e: Error) => toast.error(e.message) });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/pages/${id}`), onSuccess: (_r, id) => { qc.setQueryData(["pages"], (o: any) => o && { ...o, items: o.items.filter((p: any) => p.id !== id) }); setSel(null); } });
  const blocks: any[] = sel?.blocks || [];
  const setBlocks = (b: any[]) => setSel({ ...sel, blocks: b });
  const move = (i: number, d: number) => { const b = [...blocks]; const [x] = b.splice(i, 1); b.splice(i + d, 0, x); setBlocks(b); };

  return (
    <div>
      <PageHeader icon={LayoutTemplate} title="Sites" description="AI-generated landing pages with your forms, booking calendar and live AI agent built in: a complete funnel in minutes."
        actions={<div className="flex gap-2"><GenerateDialog onDone={(p) => { qc.invalidateQueries({ queryKey: ["pages"] }); setSel(p); }} /><Button size="sm" variant="outline" onClick={() => create.mutate()}><Plus className="size-3.5" /> Blank page</Button></div>} />
      {isLoading ? <LoadingBlock /> : (
        <div className="grid gap-6 p-6 lg:grid-cols-[240px_1fr]">
          <div className="space-y-2">
            {(data?.items || []).map((p: any) => (
              <button key={p.id} onClick={() => setSel(p)} className={cn("w-full rounded-lg border p-3 text-left", sel?.id === p.id ? "border-brand bg-brand-soft/40" : "hover:bg-muted/40")}>
                <div className="flex items-center justify-between gap-2"><p className="truncate text-sm font-medium">{p.name}</p>{p.published ? <Badge className="bg-success/15 text-success">live</Badge> : <Badge variant="outline">draft</Badge>}</div>
                <p className="text-[11px] text-muted-foreground">{p.views} views</p>
              </button>
            ))}
            {(data?.items || []).length === 0 && <EmptyState icon={LayoutTemplate} title="No pages yet" description="Generate one with AI from your business profile." />}
          </div>
          {sel && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Input className="max-w-xs font-medium" value={sel.name} onChange={(e) => setSel({ ...sel, name: e.target.value })} />
                <label className="flex items-center gap-2 text-sm">Published <Switch checked={sel.published} onCheckedChange={(v) => setSel({ ...sel, published: v })} /></label>
                <Button size="sm" variant="outline" asChild><a href={`/p/${sel.slug}`} target="_blank" rel="noreferrer"><ExternalLink className="size-3.5" /> Preview</a></Button>
                <Button size="sm" onClick={() => save.mutate()}><Save className="size-3.5" /> Save</Button>
                <Button size="icon" variant="ghost" onClick={() => confirm("Delete page?") && del.mutate(sel.id)}><Trash2 className="size-4" /></Button>
                {!sel.published && <span className="text-xs text-muted-foreground">Publish to make /p/{sel.slug} public.</span>}
              </div>
              <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
                <div className="space-y-2">
                  {blocks.map((b, i) => (
                    <Card key={b.id || i} className="gap-0 p-0">
                      <button onClick={() => setOpen(open === b.id ? null : b.id)} className="flex w-full items-center gap-2 px-4 py-2.5 text-left">
                        <Badge variant="outline" className="font-mono text-[10px]">{b.type}</Badge>
                        <span className="flex-1 truncate text-sm">{b.props?.title || b.props?.eyebrow || ""}</span>
                        <span onClick={(e) => { e.stopPropagation(); if (i > 0) move(i, -1); }} className="rounded p-1 hover:bg-muted"><ArrowUp className="size-3.5" /></span>
                        <span onClick={(e) => { e.stopPropagation(); if (i < blocks.length - 1) move(i, 1); }} className="rounded p-1 hover:bg-muted"><ArrowDown className="size-3.5" /></span>
                        <span onClick={(e) => { e.stopPropagation(); setBlocks(blocks.filter((_, j) => j !== i)); }} className="rounded p-1 hover:bg-muted"><Trash2 className="size-3.5" /></span>
                      </button>
                      {open === b.id && (
                        <div className="space-y-3 border-t p-4">
                          <BlockEditor block={b} onChange={(nb) => setBlocks(blocks.map((x, j) => (j === i ? nb : x)))} forms={forms?.items || []} calendars={cals?.items || []} agents={agents?.items || []} />
                        </div>
                      )}
                    </Card>
                  ))}
                  <Select value="" onValueChange={(t) => { const id = `b${Date.now()}`; setBlocks([...blocks, { id, type: t, props: structuredClone(BLOCKS[t]) }]); setOpen(id); }}>
                    <SelectTrigger className="border-dashed"><SelectValue placeholder="+ Add section" /></SelectTrigger>
                    <SelectContent>{Object.keys(BLOCKS).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <Card className="h-fit gap-3 p-4">
                  <Section title="SEO & style">
                    <TextField label="Page title" value={sel.seo?.title} onChange={(v) => setSel({ ...sel, seo: { ...(sel.seo || {}), title: v } })} />
                    <AreaField label="Description" rows={3} value={sel.seo?.description} onChange={(v) => setSel({ ...sel, seo: { ...(sel.seo || {}), description: v } })} />
                    <Field label="Brand colour"><div className="flex gap-2"><Input type="color" className="h-9 w-14 p-1" value={sel.theme?.color || "#6D5EF8"} onChange={(e) => setSel({ ...sel, theme: { ...(sel.theme || {}), color: e.target.value } })} /><Input value={sel.theme?.color || "#6D5EF8"} onChange={(e) => setSel({ ...sel, theme: { ...(sel.theme || {}), color: e.target.value } })} /></div></Field>
                  </Section>
                </Card>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
