"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, Play, Plus, Save, Trash2, Workflow, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { EmptyState, LoadingBlock, PageHeader, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const RECIPES = [
  { name: "Thank & book after a qualified call", trigger: { event: "analysis.completed", conditions: [{ field: "disposition", op: "equals", value: "interested" }] }, steps: [{ type: "ai_message", channel: "whatsapp", instruction: "Thank them for the call and share the booking link" }, { type: "add_tag", tag: "hot-lead" }, { type: "move_deal", stage: "qualified" }] },
  { name: "Alert team on escalation", trigger: { event: "handoff.requested", conditions: [] }, steps: [{ type: "notify", title: "Escalation: {{name}}", urgent: true }] },
  { name: "Appointment reminder", trigger: { event: "appointment.booked", conditions: [] }, steps: [{ type: "send_message", channel: "whatsapp", text: "Hi {{first_name}}, your appointment is confirmed. Reply here if you need to reschedule." }, { type: "wait", hours: 20 }, { type: "send_message", channel: "whatsapp", text: "Reminder: see you tomorrow, {{first_name}}!" }] },
  { name: "Welcome new leads", trigger: { event: "contact.created", conditions: [] }, steps: [{ type: "wait", minutes: 5 }, { type: "create_task", title: "Call new lead {{name}}", due_hours: 4 }] },
];

function StepEditor({ step, onChange, onDelete }: { step: any; onChange: (s: any) => void; onDelete: () => void }) {
  const f = (k: string, v: any) => onChange({ ...step, [k]: v });
  return (
    <Card className="gap-2 p-3">
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="font-mono">{step.type}</Badge>
        <Button size="icon" variant="ghost" className="ml-auto size-7" onClick={onDelete}><Trash2 className="size-3.5" /></Button>
      </div>
      {["send_message", "ai_message"].includes(step.type) && (
        <Select value={step.channel || "whatsapp"} onValueChange={(v) => f("channel", v)}>
          <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
          <SelectContent>{["whatsapp", "telegram", "email", "sms", "instagram", "messenger"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
        </Select>
      )}
      {step.type === "send_message" && <Input className="h-8 text-xs" value={step.text || ""} placeholder="Message ({{first_name}} works)" onChange={(e) => f("text", e.target.value)} />}
      {step.type === "ai_message" && <Input className="h-8 text-xs" value={step.instruction || ""} placeholder="What should the AI write?" onChange={(e) => f("instruction", e.target.value)} />}
      {["add_tag", "remove_tag"].includes(step.type) && <Input className="h-8 text-xs" value={step.tag || ""} placeholder="tag" onChange={(e) => f("tag", e.target.value)} />}
      {step.type === "update_field" && <div className="flex gap-2"><Input className="h-8 text-xs" value={step.field || ""} placeholder="field" onChange={(e) => f("field", e.target.value)} /><Input className="h-8 text-xs" value={step.value || ""} placeholder="value" onChange={(e) => f("value", e.target.value)} /></div>}
      {step.type === "set_lifecycle" && <Input className="h-8 text-xs" value={step.value || ""} placeholder="qualified / customer" onChange={(e) => f("value", e.target.value)} />}
      {step.type === "create_task" && <Input className="h-8 text-xs" value={step.title || ""} placeholder="Task title" onChange={(e) => f("title", e.target.value)} />}
      {step.type === "move_deal" && <Input className="h-8 text-xs" value={step.stage || ""} placeholder="stage id (e.g. qualified)" onChange={(e) => f("stage", e.target.value)} />}
      {step.type === "notify" && <Input className="h-8 text-xs" value={step.title || ""} placeholder="Notification title" onChange={(e) => f("title", e.target.value)} />}
      {step.type === "webhook" && <Input className="h-8 text-xs" value={step.url || ""} placeholder="https://…" onChange={(e) => f("url", e.target.value)} />}
      {["review_request", "send_payment_link"].includes(step.type) && (
        <Select value={step.channel || "whatsapp"} onValueChange={(v) => f("channel", v)}>
          <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
          <SelectContent>{["whatsapp", "sms", "email", "telegram"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
        </Select>
      )}
      {step.type === "send_payment_link" && <div className="flex gap-2"><Input className="h-8 w-28 text-xs" type="number" value={step.amount || ""} placeholder="amount" onChange={(e) => f("amount", Number(e.target.value))} /><Input className="h-8 text-xs" value={step.description || ""} placeholder="for… ({{first_name}} works)" onChange={(e) => f("description", e.target.value)} /></div>}
      {step.type === "add_to_campaign" && <Input className="h-8 text-xs" value={step.campaign_id || ""} placeholder="campaign id (cmp_…)" onChange={(e) => f("campaign_id", e.target.value)} />}
      {step.type === "wait" && <div className="flex gap-2 text-xs">{["minutes", "hours", "days"].map((u) => <label key={u} className="flex items-center gap-1">{u}<Input className="h-8 w-16" type="number" value={step[u] || ""} onChange={(e) => f(u, Number(e.target.value))} /></label>)}</div>}
      {step.type === "condition" && <div className="flex gap-2"><Input className="h-8 text-xs" value={step.field || ""} placeholder="contact.lifecycle" onChange={(e) => f("field", e.target.value)} /><Select value={step.op || "equals"} onValueChange={(v) => f("op", v)}><SelectTrigger className="h-8 w-28"><SelectValue /></SelectTrigger><SelectContent>{["equals", "not_equals", "contains", "exists", "gt", "lt"].map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent></Select><Input className="h-8 text-xs" value={step.value || ""} placeholder="value" onChange={(e) => f("value", e.target.value)} /></div>}
    </Card>
  );
}

export default function AutomationsPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["automations"], queryFn: () => api.get("/automations") });
  const { data: meta } = useQuery({ queryKey: ["automations-meta"], queryFn: () => api.get("/automations-meta") });
  const [sel, setSel] = useState<any>(null);
  useEffect(() => { if (!sel && data?.items?.[0]) setSel(data.items[0]); }, [data, sel]);
  const { data: runs } = useQuery({ queryKey: ["auto-runs", sel?.id], queryFn: () => api.get(`/automations/${sel.id}/runs`), enabled: !!sel?.id, refetchInterval: 10000 });
  const create = useMutation({ mutationFn: (body: any) => api.post("/automations", body), onSuccess: (a) => { qc.invalidateQueries({ queryKey: ["automations"] }); setSel(a); } });
  const save = useMutation({ mutationFn: () => api.patch(`/automations/${sel.id}`, { name: sel.name, trigger: sel.trigger, steps: sel.steps, enabled: sel.enabled }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["automations"] }); toast.success("Saved"); } });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/automations/${id}`),
    onSuccess: (_r, id) => {
      // Drop it from the cached list first, or the auto-select effect re-selects the deleted item before the refetch lands.
      qc.setQueryData(["automations"], (old: any) => old && { ...old, items: old.items.filter((a: any) => a.id !== id), total: Math.max(0, (old.total || 1) - 1) });
      setSel(null);
      qc.invalidateQueries({ queryKey: ["automations"] });
      toast.success("Automation deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const run = useMutation({ mutationFn: () => api.post(`/automations/${sel.id}/run`, { contact_id: prompt("Contact ID to run on (optional)") || undefined }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["auto-runs"] }); toast.success("Run started"); } });

  return (
    <div>
      <PageHeader icon={Workflow} title="Automations" description="When something happens, do things: message, call, tag, update the CRM, alert the team."
        actions={<Button size="sm" onClick={() => create.mutate({ name: "New automation", trigger: { event: "conversation.ended", conditions: [] }, steps: [] })}><Plus className="size-3.5" /> New automation</Button>} />
      {isLoading ? <LoadingBlock /> : (
        <div className="grid gap-6 p-6 lg:grid-cols-[280px_1fr_300px]">
          <div className="space-y-2">
            {(data?.items || []).map((a: any) => (
              <button key={a.id} onClick={() => setSel(a)} className={cn("w-full rounded-lg border p-3 text-left", sel?.id === a.id ? "border-brand bg-brand-soft/40" : "hover:bg-muted/40")}>
                <div className="flex items-center justify-between"><p className="truncate text-sm font-medium">{a.name}</p><StatusBadge status={a.enabled ? "active" : "paused"} /></div>
                <p className="font-mono text-[11px] text-muted-foreground">{a.trigger?.event} · {a.run_count} runs</p>
              </button>
            ))}
            <p className="pt-3 text-xs font-semibold text-muted-foreground">Recipes</p>
            {RECIPES.map((r) => <button key={r.name} onClick={() => create.mutate({ ...r, enabled: false })} className="w-full rounded-lg border border-dashed p-2.5 text-left text-xs hover:border-brand/50"><Zap className="mr-1 inline size-3 text-brand" />{r.name}</button>)}
          </div>
          {sel ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Input className="font-medium" value={sel.name} onChange={(e) => setSel({ ...sel, name: e.target.value })} />
                <label className="flex items-center gap-2 text-sm">On <Switch checked={sel.enabled} onCheckedChange={(v) => setSel({ ...sel, enabled: v })} /></label>
                <Button size="sm" onClick={() => save.mutate()}><Save className="size-3.5" /> Save</Button>
                <Button size="sm" variant="outline" onClick={() => run.mutate()}><Play className="size-3.5" /> Test</Button>
                <Button size="icon" variant="ghost" onClick={() => confirm("Delete automation?") && del.mutate(sel.id)}><Trash2 className="size-4" /></Button>
              </div>
              <Card className="gap-2 border-brand/40 p-3">
                <p className="text-xs font-semibold text-brand">WHEN</p>
                <Select value={sel.trigger?.event} onValueChange={(v) => setSel({ ...sel, trigger: { ...sel.trigger, event: v } })}>
                  <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                  <SelectContent>{(meta?.triggers || []).map((t: string) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
                </Select>
                {(sel.trigger?.conditions || []).map((c: any, i: number) => (
                  <div key={i} className="flex gap-2">
                    <Input className="h-8 text-xs" value={c.field} placeholder="field e.g. disposition" onChange={(e) => { const cs = [...sel.trigger.conditions]; cs[i] = { ...c, field: e.target.value }; setSel({ ...sel, trigger: { ...sel.trigger, conditions: cs } }); }} />
                    <Input className="h-8 text-xs" value={c.value} placeholder="equals…" onChange={(e) => { const cs = [...sel.trigger.conditions]; cs[i] = { ...c, value: e.target.value }; setSel({ ...sel, trigger: { ...sel.trigger, conditions: cs } }); }} />
                  </div>
                ))}
                <Button size="sm" variant="ghost" className="w-fit" onClick={() => setSel({ ...sel, trigger: { ...sel.trigger, conditions: [...(sel.trigger?.conditions || []), { field: "", op: "equals", value: "" }] } })}><Plus className="size-3" /> condition</Button>
              </Card>
              {(sel.steps || []).map((s: any, i: number) => (
                <div key={i} className="space-y-3">
                  <ArrowDown className="mx-auto size-4 text-muted-foreground" />
                  <StepEditor step={s} onChange={(n) => { const st = [...sel.steps]; st[i] = n; setSel({ ...sel, steps: st }); }} onDelete={() => setSel({ ...sel, steps: sel.steps.filter((_: any, j: number) => j !== i) })} />
                </div>
              ))}
              <ArrowDown className="mx-auto size-4 text-muted-foreground" />
              <Select value="" onValueChange={(v) => setSel({ ...sel, steps: [...(sel.steps || []), { type: v }] })}>
                <SelectTrigger className="border-dashed"><SelectValue placeholder="+ Add step" /></SelectTrigger>
                <SelectContent>{Object.entries(meta?.steps || {}).map(([k, v]: any) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          ) : <EmptyState icon={Workflow} title="No automation selected" description="Create one or start from a recipe." />}
          <Card className="h-fit gap-2 p-4">
            <p className="text-sm font-semibold">Recent runs</p>
            {(runs?.items || []).length === 0 && <p className="text-xs text-muted-foreground">No runs yet.</p>}
            {(runs?.items || []).map((r: any) => (
              <details key={r.id} className="rounded-md border p-2 text-xs">
                <summary className="flex cursor-pointer items-center justify-between"><StatusBadge status={r.status} /> <span className="text-muted-foreground">{timeAgo(r.created_at)}</span></summary>
                <pre className="mt-2 whitespace-pre-wrap text-[10px]">{JSON.stringify(r.log, null, 1)}</pre>
              </details>
            ))}
          </Card>
        </div>
      )}
    </div>
  );
}
