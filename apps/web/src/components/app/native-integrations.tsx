"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Check, Cloud, Copy, Inbox, Link2, Plus, Trash2, Users } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/agent/fields";
import { Section } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";

const ICONS: Record<string, any> = { hubspot: Users, salesforce: Cloud, calcom: CalendarDays, google_calendar: CalendarDays };

function ConnectDialog({ item, onDone }: { item: any; onDone: () => void }) {
  const api = useApi();
  const [v, setV] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(false);
  const connect = useMutation({ mutationFn: () => api.post(`/integrations/${item.id}`, v), onSuccess: (r) => { toast.success(r.message); setOpen(false); onDone(); }, onError: (e: Error) => toast.error(e.message) });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" variant="outline">Connect</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Connect {item.name}</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">{item.help}</p>
        {item.fields.map((f: any) => (
          <Field key={f.key} label={f.label}><Input type={f.secret ? "password" : "text"} value={v[f.key] || ""} onChange={(e) => setV({ ...v, [f.key]: e.target.value })} /></Field>
        ))}
        <Button disabled={connect.isPending} onClick={() => connect.mutate()}>Test & connect</Button>
      </DialogContent>
    </Dialog>
  );
}

export function NativeIntegrations() {
  const api = useApi();
  const qc = useQueryClient();
  const params = useSearchParams();
  const { data } = useQuery({ queryKey: ["integrations"], queryFn: () => api.get("/integrations") });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["integrations"] });
  useEffect(() => {
    if (params.get("google") === "connected") toast.success("Google Calendar connected");
    if (params.get("google") === "error") toast.error("Google Calendar was not connected");
  }, [params]);
  const disconnect = useMutation({ mutationFn: (t: string) => api.del(`/integrations/${t}`), onSuccess: refresh });
  const google = useMutation({ mutationFn: () => api.get("/integrations/google/start"), onSuccess: (r) => { window.location.href = r.url; }, onError: (e: Error) => toast.error(e.message) });
  const [hook, setHook] = useState({ name: "", action: "upsert_contact", agent_id: "", channel: "whatsapp", message: "" });
  const addHook = useMutation({
    mutationFn: () => api.post("/incoming-hooks", { name: hook.name, action: hook.action, config: { agent_id: hook.agent_id || undefined, channel: hook.channel, message: hook.message || undefined } }),
    onSuccess: () => { refresh(); setHook({ ...hook, name: "" }); toast.success("Webhook created: paste its URL into Zapier / Make / n8n"); },
  });
  const delHook = useMutation({ mutationFn: (id: string) => api.del(`/incoming-hooks/${id}`), onSuccess: refresh });

  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
      <Card className="gap-3 p-5">
        <Section title="Native apps" description="Two-way sync: leads, call summaries and bookings flow into your CRM and calendar automatically.">
          <div className="grid gap-3 sm:grid-cols-2">
            {(data?.catalog || []).map((c: any) => {
              const Icon = ICONS[c.id] || Link2;
              return (
                <div key={c.id} className="flex flex-col gap-2 rounded-lg border p-3">
                  <div className="flex items-center gap-2">
                    <Icon className="size-4 text-brand" />
                    <p className="flex-1 text-sm font-medium">{c.name}</p>
                    {c.connected ? <Badge className="bg-success/15 text-success"><Check className="size-3" /> connected</Badge> : <Badge variant="outline">{c.kind}</Badge>}
                  </div>
                  <p className="flex-1 text-xs text-muted-foreground">{c.help}</p>
                  {c.error && <p className="text-[11px] text-destructive">{c.error}</p>}
                  {c.last_sync_at && <p className="text-[11px] text-muted-foreground">Last sync {timeAgo(c.last_sync_at)}</p>}
                  <div className="flex gap-2">
                    {c.connected ? (
                      <Button size="sm" variant="ghost" onClick={() => disconnect.mutate(c.id)}>Disconnect</Button>
                    ) : c.oauth ? (
                      <Button size="sm" variant="outline" disabled={!c.available || google.isPending} onClick={() => google.mutate()} title={c.available ? "" : "Set GOOGLE_OAUTH_CLIENT_ID/SECRET in .env"}>Connect with Google</Button>
                    ) : <ConnectDialog item={c} onDone={refresh} />}
                    {c.oauth && !c.available && <span className="text-[11px] text-muted-foreground">needs GOOGLE_OAUTH_* in .env</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      </Card>
      <Card className="gap-3 p-5">
        <Section title="Incoming webhooks (Zapier · Make · n8n · forms · ads)" description="Any app can push a lead here: we create the contact and can instantly call or message them.">
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="Name, e.g. Facebook lead ads" value={hook.name} onChange={(e) => setHook({ ...hook, name: e.target.value })} />
            <Select value={hook.action} onValueChange={(v) => setHook({ ...hook, action: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="upsert_contact">Create/update contact</SelectItem>
                <SelectItem value="start_call">…and call them (AI)</SelectItem>
                <SelectItem value="send_message">…and message them (AI)</SelectItem>
                <SelectItem value="event_only">Trigger automations only</SelectItem>
              </SelectContent>
            </Select>
            {hook.action !== "upsert_contact" && hook.action !== "event_only" && (
              <Select value={hook.agent_id} onValueChange={(v) => setHook({ ...hook, agent_id: v })}>
                <SelectTrigger><SelectValue placeholder="Agent" /></SelectTrigger>
                <SelectContent>{(agents?.items || []).map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent>
              </Select>
            )}
            {hook.action === "send_message" && (
              <Select value={hook.channel} onValueChange={(v) => setHook({ ...hook, channel: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{["whatsapp", "sms", "email"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            )}
          </div>
          <Button size="sm" className="w-fit" disabled={!hook.name} onClick={() => addHook.mutate()}><Plus className="size-3.5" /> Create webhook</Button>
          {(data?.hooks || []).map((h: any) => (
            <div key={h.id} className="space-y-1 rounded-lg border p-2.5">
              <div className="flex items-center gap-2 text-sm"><Inbox className="size-3.5" /><span className="flex-1 font-medium">{h.name}</span><Badge variant="outline">{h.action}</Badge><span className="text-xs text-muted-foreground">{h.calls} calls</span>
                <Button size="icon" variant="ghost" className="size-7" onClick={() => delHook.mutate(h.id)}><Trash2 className="size-3.5" /></Button></div>
              <div className="flex items-center gap-1.5"><code className="flex-1 break-all rounded bg-muted/50 px-2 py-1 text-[11px]">{h.url}</code>
                <Button size="icon" variant="ghost" className="size-7" onClick={() => { navigator.clipboard.writeText(h.url); toast.success("Copied"); }}><Copy className="size-3.5" /></Button></div>
            </div>
          ))}
          <p className="text-[11px] text-muted-foreground">Send JSON with name / phone / email (any common field names). Outgoing events (calls, leads, bookings, payments) are in Settings → Webhooks.</p>
        </Section>
      </Card>
    </div>
  );
}
