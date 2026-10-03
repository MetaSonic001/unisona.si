"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ClipboardList, ExternalLink, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AreaField, Field, ListField, TextField } from "@/components/agent/fields";
import { EmptyState, LoadingBlock, PageHeader, Section, StatCard } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const MAP = [["", "—"], ["name", "Contact name"], ["phone", "Phone"], ["email", "Email"], ["consent", "Marketing consent"]];

function Submissions({ formId }: { formId: string }) {
  const api = useApi();
  const { data } = useQuery({ queryKey: ["form-subs", formId], queryFn: () => api.get(`/forms/${formId}/submissions`) });
  const fields: any[] = data?.form?.fields || [];
  return (
    <div className="space-y-4">
      {data?.stats && Object.keys(data.stats).length > 0 && (
        <div className="grid gap-3 sm:grid-cols-3">
          {Object.entries(data.stats).map(([k, v]: any) => (
            <StatCard key={k} label={fields.find((f) => f.id === k)?.label || k} value={v.nps !== undefined ? `NPS ${v.nps}` : v.avg} hint={`avg ${v.avg} · ${v.count} responses`} />
          ))}
        </div>
      )}
      <Card className="gap-0 overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
            <tr>{fields.slice(0, 5).map((f) => <th key={f.id} className="px-3 py-2 font-medium">{f.label}</th>)}<th className="px-3 py-2">When</th></tr>
          </thead>
          <tbody>
            {(data?.items || []).map((s: any) => (
              <tr key={s.id} className="border-b last:border-0">
                {fields.slice(0, 5).map((f) => <td key={f.id} className="max-w-[200px] truncate px-3 py-2">{String(s.data?.[f.id] ?? "")}</td>)}
                <td className="px-3 py-2 text-xs text-muted-foreground">{timeAgo(s.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(data?.items || []).length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">No submissions yet. Share the form link.</p>}
      </Card>
    </div>
  );
}

export default function FormsPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["forms"], queryFn: () => api.get("/forms") });
  const { data: meta } = useQuery({ queryKey: ["forms-meta"], queryFn: () => api.get("/forms-meta") });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const [sel, setSel] = useState<any>(null);
  useEffect(() => { if (!sel && data?.items?.[0]) setSel(data.items[0]); }, [data, sel]);
  const fromTpl = useMutation({ mutationFn: (t: string) => api.post(`/forms/from-template/${t}`), onSuccess: (f) => { qc.invalidateQueries({ queryKey: ["forms"] }); setSel(f); } });
  const blank = useMutation({ mutationFn: () => api.post("/forms", { name: "Untitled form", kind: "form", fields: [{ id: "name", label: "Name", type: "text", required: true, map_to: "name" }], settings: { thank_you: "Thank you!" } }), onSuccess: (f) => { qc.invalidateQueries({ queryKey: ["forms"] }); setSel(f); } });
  const save = useMutation({ mutationFn: () => api.patch(`/forms/${sel.id}`, { name: sel.name, kind: sel.kind, fields: sel.fields, settings: sel.settings, enabled: sel.enabled }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["forms"] }); toast.success("Form saved"); }, onError: (e: Error) => toast.error(e.message) });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/forms/${id}`),
    onSuccess: (_r, id) => { qc.setQueryData(["forms"], (o: any) => o && { ...o, items: o.items.filter((f: any) => f.id !== id) }); setSel(null); qc.invalidateQueries({ queryKey: ["forms"] }); },
  });
  const appUrl = typeof window !== "undefined" ? window.location.origin : "";
  const setField = (i: number, patch: any) => setSel({ ...sel, fields: sel.fields.map((f: any, j: number) => (j === i ? { ...f, ...patch } : f)) });
  const move = (i: number, d: number) => { const f = [...sel.fields]; const [x] = f.splice(i, 1); f.splice(i + d, 0, x); setSel({ ...sel, fields: f }); };
  const st = sel?.settings || {};
  const setS = (k: string, v: any) => setSel({ ...sel, settings: { ...st, [k]: v } });

  return (
    <div>
      <PageHeader icon={ClipboardList} title="Forms & surveys" description="Capture leads and feedback anywhere. Every submission lands in the CRM and can trigger an instant AI call or message."
        actions={<div className="flex gap-2">
          <Select onValueChange={(t) => fromTpl.mutate(t)}><SelectTrigger className="h-8 w-[170px]"><SelectValue placeholder="From template" /></SelectTrigger>
            <SelectContent>{Object.entries(meta?.templates || {}).map(([k, t]: any) => <SelectItem key={k} value={k}>{t.name}</SelectItem>)}</SelectContent></Select>
          <Button size="sm" onClick={() => blank.mutate()}><Plus className="size-3.5" /> New form</Button></div>} />
      {isLoading ? <LoadingBlock /> : (
        <div className="grid gap-6 p-6 lg:grid-cols-[260px_1fr]">
          <div className="space-y-2">
            {(data?.items || []).map((f: any) => (
              <button key={f.id} onClick={() => setSel(f)} className={cn("w-full rounded-lg border p-3 text-left", sel?.id === f.id ? "border-brand bg-brand-soft/40" : "hover:bg-muted/40")}>
                <div className="flex items-center justify-between gap-2"><p className="truncate text-sm font-medium">{f.name}</p><Badge variant="outline">{f.kind}</Badge></div>
                <p className="text-[11px] text-muted-foreground">{f.submissions} submissions</p>
              </button>
            ))}
            {(data?.items || []).length === 0 && <EmptyState icon={ClipboardList} title="No forms yet" description="Start from a template: contact, quote or NPS survey." />}
          </div>
          {sel && (
            <Tabs defaultValue="build" className="gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <Input className="max-w-xs font-medium" value={sel.name} onChange={(e) => setSel({ ...sel, name: e.target.value })} />
                <TabsList><TabsTrigger value="build">Build</TabsTrigger><TabsTrigger value="share">Share</TabsTrigger><TabsTrigger value="subs">Submissions</TabsTrigger></TabsList>
                <label className="ml-auto flex items-center gap-2 text-sm">Live <Switch checked={sel.enabled} onCheckedChange={(v) => setSel({ ...sel, enabled: v })} /></label>
                <Button size="sm" onClick={() => save.mutate()}><Save className="size-3.5" /> Save</Button>
                <Button size="icon" variant="ghost" onClick={() => confirm("Delete form?") && del.mutate(sel.id)}><Trash2 className="size-4" /></Button>
              </div>
              <TabsContent value="build">
                <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
                  <Card className="gap-3 p-5">
                    {(sel.fields || []).map((f: any, i: number) => (
                      <div key={i} className="space-y-2 rounded-lg border p-3">
                        <div className="flex flex-wrap gap-2">
                          <Input className="min-w-[200px] flex-1" value={f.label} onChange={(e) => setField(i, { label: e.target.value })} />
                          <Select value={f.type} onValueChange={(v) => setField(i, { type: v })}>
                            <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                            <SelectContent>{(meta?.field_types || []).map((t: string) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                          </Select>
                          <Select value={f.map_to || ""} onValueChange={(v) => setField(i, { map_to: v.trim() || undefined })}>
                            <SelectTrigger className="w-40"><SelectValue placeholder="Save to CRM as…" /></SelectTrigger>
                            <SelectContent>{MAP.map(([v, l]) => <SelectItem key={v || "none"} value={v || " "}>{l}</SelectItem>)}</SelectContent>
                          </Select>
                          <label className="flex items-center gap-1.5 text-xs">Required <Switch checked={!!f.required} onCheckedChange={(v) => setField(i, { required: v })} /></label>
                          <Button size="icon" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="size-3.5" /></Button>
                          <Button size="icon" variant="ghost" disabled={i === sel.fields.length - 1} onClick={() => move(i, 1)}><ArrowDown className="size-3.5" /></Button>
                          <Button size="icon" variant="ghost" onClick={() => setSel({ ...sel, fields: sel.fields.filter((_: any, j: number) => j !== i) })}><Trash2 className="size-3.5" /></Button>
                        </div>
                        {["select", "radio"].includes(f.type) && <Input placeholder="Options, comma separated" value={(f.options || []).join(", ")} onChange={(e) => setField(i, { options: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />}
                      </div>
                    ))}
                    <Button variant="outline" size="sm" className="w-fit" onClick={() => setSel({ ...sel, fields: [...(sel.fields || []), { id: `f${Date.now().toString(36)}`, label: "New question", type: "text" }] })}><Plus className="size-3.5" /> Add field</Button>
                  </Card>
                  <div className="space-y-4">
                    <Card className="gap-3 p-4">
                      <Section title="After submit">
                        <Field label="Type"><Select value={sel.kind} onValueChange={(v) => setSel({ ...sel, kind: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="form">Lead / contact form</SelectItem><SelectItem value="survey">Survey (NPS / ratings)</SelectItem></SelectContent></Select></Field>
                        <AreaField label="Thank-you message" rows={2} value={st.thank_you} onChange={(v) => setS("thank_you", v)} />
                        <TextField label="Redirect URL (optional)" value={st.redirect_url} onChange={(v) => setS("redirect_url", v)} />
                        <ListField label="Tag contacts with" values={st.tags || []} onChange={(v) => setS("tags", v)} placeholder="e.g. website-lead" />
                      </Section>
                    </Card>
                    <Card className="gap-3 p-4">
                      <Section title="Speed-to-lead" description="Contact new leads within seconds, while they're still interested.">
                        <Field label="Instant follow-up">
                          <Select value={st.follow_up?.type || "none"} onValueChange={(v) => setS("follow_up", { ...(st.follow_up || {}), type: v === "none" ? null : v })}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="none">None</SelectItem>
                              <SelectItem value="call">AI phone call</SelectItem>
                              <SelectItem value="whatsapp">WhatsApp message</SelectItem>
                              <SelectItem value="sms">SMS</SelectItem>
                              <SelectItem value="email">Email</SelectItem>
                            </SelectContent>
                          </Select>
                        </Field>
                        {st.follow_up?.type && (
                          <>
                            <Field label="Agent"><Select value={st.follow_up?.agent_id || ""} onValueChange={(v) => setS("follow_up", { ...st.follow_up, agent_id: v })}><SelectTrigger><SelectValue placeholder="Choose agent" /></SelectTrigger><SelectContent>{(agents?.items || []).map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent></Select></Field>
                            {st.follow_up.type !== "call" && <AreaField label="Message" rows={2} value={st.follow_up?.message} onChange={(v) => setS("follow_up", { ...st.follow_up, message: v })} />}
                          </>
                        )}
                      </Section>
                    </Card>
                  </div>
                </div>
              </TabsContent>
              <TabsContent value="share">
                <Card className="gap-4 p-5">
                  <Section title="Share" description="Link, QR or embed on any website.">
                    <Field label="Public link"><div className="flex gap-2"><Input readOnly value={`${appUrl}/f/${sel.slug}`} /><Button variant="outline" asChild><a href={`/f/${sel.slug}`} target="_blank" rel="noreferrer"><ExternalLink className="size-3.5" /> Open</a></Button></div></Field>
                    <Field label="Embed code"><Input readOnly className="font-mono text-xs" value={`<iframe src="${appUrl}/f/${sel.slug}?embed=1" style="width:100%;min-height:640px;border:0" loading="lazy"></iframe>`} /></Field>
                  </Section>
                </Card>
              </TabsContent>
              <TabsContent value="subs"><Submissions formId={sel.id} /></TabsContent>
            </Tabs>
          )}
        </div>
      )}
    </div>
  );
}
