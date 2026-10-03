"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone, Pause, Play, Plus, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/agent/fields";
import { EmptyState, LoadingBlock, PageHeader, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function CampaignsPage() {
  const api = useApi();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<any>(null);
  const { data, isLoading } = useQuery({ queryKey: ["campaigns"], queryFn: () => api.get("/campaigns"), refetchInterval: 10000 });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const { data: defs } = useQuery({ queryKey: ["campaign-defaults"], queryFn: () => api.get("/campaigns-defaults") });
  const [form, setForm] = useState<any>({ name: "", type: "voice", agent_id: "", message: "", purpose: "transactional", subject: "", template_name: "", template_language: "en" });
  const create = useMutation({
    mutationFn: () => api.post("/campaigns", { name: form.name, type: form.type, agent_id: form.agent_id, settings: { ...(defs?.settings || {}), message: form.message, purpose: form.purpose,
      subject: form.subject, template_name: form.template_name, template_language: form.template_language } }),
    onSuccess: (c) => { setOpen(false); qc.invalidateQueries({ queryKey: ["campaigns"] }); setSel(c); },
    onError: (e: Error) => toast.error(e.message),
  });
  const action = useMutation({ mutationFn: ({ id, a }: { id: string; a: string }) => api.post(`/campaigns/${id}/${a}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["campaigns"] }), onError: (e: Error) => toast.error(e.message) });

  return (
    <div>
      <PageHeader icon={Megaphone} title="Campaigns" description="Batch AI calls and WhatsApp, SMS, email, Telegram and Instagram broadcasts, with calling windows, consent and DND checks, and retries."
        actions={<Button size="sm" onClick={() => setOpen(true)}><Plus className="size-3.5" /> New campaign</Button>} />
      <div className="p-6">
        {isLoading ? <LoadingBlock /> : (data?.items || []).length === 0 ? <EmptyState icon={Megaphone} title="No campaigns yet" description="Upload a CSV or pick a contact tag, choose an agent, and start. Results flow into the CRM." action={<Button onClick={() => setOpen(true)}>Create campaign</Button>} /> : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.items.map((c: any) => {
              const total = c.stats?.total || 0;
              const done = (c.stats?.done || 0) + (c.stats?.failed || 0) + (c.stats?.skipped || 0);
              return (
                <Card key={c.id} className="cursor-pointer gap-3 p-4 transition hover:shadow-md" onClick={() => setSel(c)}>
                  <div className="flex items-center justify-between"><p className="font-medium">{c.name}</p><StatusBadge status={c.status} /></div>
                  <p className="text-xs capitalize text-muted-foreground">{c.type} · created {timeAgo(c.created_at)}</p>
                  <Progress value={total ? (done / total) * 100 : 0} />
                  <p className="text-xs text-muted-foreground">{done}/{total} processed · {c.stats?.done || 0} reached · {c.stats?.failed || 0} failed</p>
                  <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                    {["draft", "paused"].includes(c.status) && <Button size="sm" onClick={() => action.mutate({ id: c.id, a: c.status === "paused" ? "resume" : "start" })}><Play className="size-3.5" /> Start</Button>}
                    {c.status === "running" && <Button size="sm" variant="outline" onClick={() => action.mutate({ id: c.id, a: "pause" })}><Pause className="size-3.5" /> Pause</Button>}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New campaign</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Type">
              <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="voice">AI phone calls</SelectItem>
                  <SelectItem value="whatsapp_template">WhatsApp template broadcast (anyone)</SelectItem>
                  <SelectItem value="whatsapp">WhatsApp message (24h window)</SelectItem>
                  <SelectItem value="sms">SMS</SelectItem>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="telegram">Telegram broadcast</SelectItem>
                  <SelectItem value="instagram">Instagram DM (24h window)</SelectItem>
                  <SelectItem value="messenger">Messenger (24h window)</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Agent">
              <Select value={form.agent_id} onValueChange={(v) => setForm({ ...form, agent_id: v })}>
                <SelectTrigger><SelectValue placeholder="Choose an agent" /></SelectTrigger>
                <SelectContent>{(agents?.items || []).map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Purpose" hint="Promotional outreach only reaches contacts with recorded marketing consent (Compliance settings).">
              <Select value={form.purpose} onValueChange={(v) => setForm({ ...form, purpose: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="transactional">Transactional (reminders, updates, service)</SelectItem><SelectItem value="promotional">Promotional (offers, marketing)</SelectItem></SelectContent>
              </Select>
            </Field>
            {form.type === "email" && <Field label="Subject"><Input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} /></Field>}
            {form.type === "whatsapp_template" && (
              <div className="grid grid-cols-[1fr_90px] gap-2">
                <Field label="Approved template name" hint="Manage templates on the agent's Channels tab"><Input value={form.template_name} onChange={(e) => setForm({ ...form, template_name: e.target.value })} /></Field>
                <Field label="Language"><Input value={form.template_language} onChange={(e) => setForm({ ...form, template_language: e.target.value })} /></Field>
              </div>
            )}
            {form.type !== "voice" && <Field label={form.type === "whatsapp_template" ? "Template variable {{1}}" : "Message"} hint="Use {{first_name}}, {{name}} or any CSV column as {{column}}. Replies are handled by the agent."><Textarea rows={3} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} /></Field>}
            <Button disabled={!form.name || !form.agent_id || create.isPending} onClick={() => create.mutate()}>Create</Button>
          </div>
        </DialogContent>
      </Dialog>
      <Sheet open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader><SheetTitle>{sel?.name}</SheetTitle></SheetHeader>
          {sel && <CampaignDetail campaign={sel} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function CampaignDetail({ campaign }: { campaign: any }) {
  const api = useApi();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [tag, setTag] = useState("");
  const s = campaign.settings || {};
  const { data: targets } = useQuery({ queryKey: ["targets", campaign.id], queryFn: () => api.get(`/campaigns/${campaign.id}/targets`), refetchInterval: 8000 });
  const saveSettings = useMutation({ mutationFn: (settings: any) => api.patch(`/campaigns/${campaign.id}`, { settings: { ...s, ...settings } }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["campaigns"] }); toast.success("Saved"); } });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["targets", campaign.id] }); qc.invalidateQueries({ queryKey: ["campaigns"] }); };
  const upload = async (f?: File) => {
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    const r = await api.upload(`/campaigns/${campaign.id}/targets/upload`, fd);
    toast.success(`${r.added} recipients added`);
    refresh();
  };
  const addTag = async () => { const r = await api.post(`/campaigns/${campaign.id}/targets`, { tag }); toast.success(`${r.added} contacts added`); refresh(); };
  return (
    <div className="space-y-5 px-4 pb-8">
      <div className="space-y-2">
        <p className="text-sm font-semibold">Recipients</p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}><Upload className="size-3.5" /> Upload CSV (phone, name, …)</Button>
          <input ref={fileRef} hidden type="file" accept=".csv" onChange={(e) => upload(e.target.files?.[0])} />
        </div>
        <div className="flex gap-2"><Input className="h-8" placeholder="…or all contacts with tag" value={tag} onChange={(e) => setTag(e.target.value)} /><Button size="sm" className="h-8" disabled={!tag} onClick={addTag}>Add</Button></div>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-semibold">Guardrails</p>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <label>Window start<Input className="h-8" defaultValue={s.window_start} onBlur={(e) => saveSettings.mutate({ window_start: e.target.value })} /></label>
          <label>Window end<Input className="h-8" defaultValue={s.window_end} onBlur={(e) => saveSettings.mutate({ window_end: e.target.value })} /></label>
          <label>Concurrent calls<Input className="h-8" type="number" defaultValue={s.concurrency} onBlur={(e) => saveSettings.mutate({ concurrency: Number(e.target.value) })} /></label>
          <label>Max attempts<Input className="h-8" type="number" defaultValue={s.max_attempts} onBlur={(e) => saveSettings.mutate({ max_attempts: Number(e.target.value) })} /></label>
          <label>Retry after (min)<Input className="h-8" type="number" defaultValue={s.retry_minutes} onBlur={(e) => saveSettings.mutate({ retry_minutes: Number(e.target.value) })} /></label>
          <label>Timezone<Input className="h-8" defaultValue={s.timezone} onBlur={(e) => saveSettings.mutate({ timezone: e.target.value })} /></label>
        </div>
        <p className="text-[11px] text-muted-foreground">Numbers on your do-not-call list are always skipped.</p>
      </div>
      <div>
        <p className="mb-2 text-sm font-semibold">{targets?.items?.length || 0} recipients</p>
        <div className="max-h-80 space-y-1 overflow-y-auto">
          {(targets?.items || []).map((t: any) => (
            <div key={t.id} className="flex items-center justify-between rounded border px-2.5 py-1.5 text-xs">
              <span className="font-mono">{t.address}</span><span className="text-muted-foreground">{t.variables?.name}</span>
              <StatusBadge status={t.status === "done" ? "completed" : t.status} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
