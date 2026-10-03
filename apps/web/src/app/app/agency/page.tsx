"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Building, Copy, Download, Palette, Plus, Receipt } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Field, SwitchRow, TextField } from "@/components/agent/fields";
import { EmptyState, LoadingBlock, PageHeader, Section, StatCard } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { setActiveWorkspace, useApi } from "@/lib/api";

function Picker({ title, items, value, onChange }: { title: string; items: any[]; value: string[]; onChange: (v: string[]) => void }) {
  if (!items.length) return null;
  return (
    <Field label={title}>
      <div className="max-h-32 space-y-1 overflow-y-auto rounded-md border p-2">
        {items.map((i) => (
          <label key={i.id} className="flex items-center gap-2 text-sm"><Checkbox checked={value.includes(i.id)} onCheckedChange={(v) => onChange(v ? [...value, i.id] : value.filter((x) => x !== i.id))} />{i.name}</label>
        ))}
      </div>
    </Field>
  );
}

function NewClient({ onDone }: { onDone: () => void }) {
  const api = useApi();
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const { data: autos } = useQuery({ queryKey: ["automations"], queryFn: () => api.get("/automations") });
  const { data: forms } = useQuery({ queryKey: ["forms"], queryFn: () => api.get("/forms") });
  const [open, setOpen] = useState(false);
  const [v, setV] = useState<any>({ name: "", pricing: { monthly_fee: 4999, voice_minute_rate: 6, markup_pct: 30 }, blueprint_agent_ids: [], blueprint_automation_ids: [], blueprint_form_ids: [] });
  const create = useMutation({ mutationFn: () => api.post("/agency/clients", v), onSuccess: () => { toast.success("Client account created"); setOpen(false); onDone(); }, onError: (e: Error) => toast.error(e.message) });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm"><Plus className="size-3.5" /> New client</Button></DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>New client sub-account</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <TextField label="Client business name" value={v.name} onChange={(x) => setV({ ...v, name: x })} />
          <div className="grid grid-cols-3 gap-2">
            <TextField label="Monthly fee" type="number" value={String(v.pricing.monthly_fee)} onChange={(x) => setV({ ...v, pricing: { ...v.pricing, monthly_fee: Number(x) } })} />
            <TextField label="Per voice min" type="number" value={String(v.pricing.voice_minute_rate)} onChange={(x) => setV({ ...v, pricing: { ...v.pricing, voice_minute_rate: Number(x) } })} />
            <TextField label="AI markup %" type="number" value={String(v.pricing.markup_pct)} onChange={(x) => setV({ ...v, pricing: { ...v.pricing, markup_pct: Number(x) } })} />
          </div>
          <p className="text-xs font-medium">Blueprint: copy your proven setup into the new account</p>
          <Picker title="Agents" items={agents?.items || []} value={v.blueprint_agent_ids} onChange={(x) => setV({ ...v, blueprint_agent_ids: x })} />
          <Picker title="Automations" items={autos?.items || []} value={v.blueprint_automation_ids} onChange={(x) => setV({ ...v, blueprint_automation_ids: x })} />
          <Picker title="Forms" items={forms?.items || []} value={v.blueprint_form_ids} onChange={(x) => setV({ ...v, blueprint_form_ids: x })} />
          <Button className="w-full" disabled={!v.name || create.isPending} onClick={() => create.mutate()}>Create client</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Branding() {
  const api = useApi();
  const { data } = useQuery({ queryKey: ["branding"], queryFn: () => api.get("/workspace/branding") });
  const [b, setB] = useState<any>(null);
  useEffect(() => { if (data && !b) setB(data.branding || {}); }, [data, b]);
  const save = useMutation({ mutationFn: () => api.patch("/workspace/branding", b), onSuccess: () => toast.success("Branding saved"), onError: (e: Error) => toast.error(e.message) });
  if (!b) return null;
  return (
    <Card className="gap-3 p-5">
      <Section title="White-label branding" description="Your brand on the hosted chat, widget, booking, forms, review and landing pages. Clients inherit it.">
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Brand name" value={b.name} onChange={(v) => setB({ ...b, name: v })} />
          <Field label="Primary colour"><div className="flex gap-2"><Input type="color" className="h-9 w-14 p-1" value={b.primary_color || "#6D5EF8"} onChange={(e) => setB({ ...b, primary_color: e.target.value })} /><Input value={b.primary_color || ""} onChange={(e) => setB({ ...b, primary_color: e.target.value })} /></div></Field>
          <TextField label="Logo URL" value={b.logo_url} onChange={(v) => setB({ ...b, logo_url: v })} />
          <TextField label="Support email" value={b.support_email} onChange={(v) => setB({ ...b, support_email: v })} />
          <TextField label="Custom domain (CNAME to this app)" value={b.custom_domain} onChange={(v) => setB({ ...b, custom_domain: v })} placeholder="ai.youragency.com" />
        </div>
        <SwitchRow label="Hide “Powered by Unisona”" hint="Growth plan and above." checked={!!b.hide_powered_by} onChange={(v) => setB({ ...b, hide_powered_by: v })} />
        <Button size="sm" className="w-fit" onClick={() => save.mutate()}><Palette className="size-3.5" /> Save branding</Button>
      </Section>
    </Card>
  );
}

export default function AgencyPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({ queryKey: ["agency"], queryFn: () => api.get("/agency"), retry: false });
  const [rb, setRb] = useState<any>(null);
  useEffect(() => { if (data && !rb) setRb(data.rebilling); }, [data, rb]);
  const enable = useMutation({ mutationFn: () => api.post("/agency/enable", {}), onSuccess: () => qc.invalidateQueries({ queryKey: ["agency"] }) });
  const saveRb = useMutation({ mutationFn: () => api.patch("/agency/rebilling", rb), onSuccess: () => { toast.success("Rebilling defaults saved"); qc.invalidateQueries({ queryKey: ["agency"] }); } });
  const report = useMutation({
    mutationFn: () => api.get("/agency/report"),
    onSuccess: (r) => {
      const csv = ["client,voice_minutes,base_fee,usage_charge,total", ...r.rows.map((x: any) => `"${x.client}",${x.voice_minutes},${x.base_fee},${x.usage_charge},${x.total}`), `TOTAL,,,,${r.grand_total}`].join("\n");
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      Object.assign(document.createElement("a"), { href: url, download: `rebilling-${r.period}.csv` }).click();
    },
  });
  if (isLoading) return <LoadingBlock />;
  if (error) return <div className="p-10"><EmptyState icon={Building} title="Open your agency workspace" description={(error as Error).message} /></div>;
  const open = (id: string) => { setActiveWorkspace(id); window.location.href = "/app"; };
  const totalRevenue = data.clients.reduce((s: number, c: any) => s + c.rebill.base_fee + c.rebill.usage_charge, 0);
  return (
    <div>
      <PageHeader icon={Building} title="Agency" description="Run AI agents for your clients: separate client accounts, blueprints, white-label branding and rebilling."
        actions={data.enabled && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => report.mutate()}><Download className="size-3.5" /> Rebilling CSV</Button><NewClient onDone={() => qc.invalidateQueries({ queryKey: ["agency"] })} /></div>} />
      <div className="space-y-6 p-6">
        {data.is_client ? <EmptyState icon={Building} title="This is a client account" description="Agency features live in your agency workspace." /> : !data.enabled ? (
          <Card className="items-center gap-3 p-10 text-center">
            <Building className="size-10 text-brand" />
            <p className="text-lg font-semibold">Turn this workspace into an agency</p>
            <p className="max-w-lg text-sm text-muted-foreground">Create a separate account per client, copy your best agents and automations into them, brand everything as your own, and bill clients with your markup.</p>
            <Button onClick={() => enable.mutate()}>Enable agency mode</Button>
          </Card>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="Clients" value={`${data.clients.length}${data.limit < 1000 ? ` / ${data.limit}` : ""}`} />
              <StatCard label="Client voice minutes (MTD)" value={data.clients.reduce((s: number, c: any) => s + c.usage.voice_minutes, 0).toFixed(1)} />
              <StatCard label="Billable this month" value={`${data.rebilling.currency} ${totalRevenue.toLocaleString()}`} icon={Receipt} />
              <StatCard label="AI provider cost (MTD)" value={`$${data.clients.reduce((s: number, c: any) => s + c.usage.provider_cost_usd, 0).toFixed(2)}`} />
            </div>
            <Card className="gap-0 p-0">
              <p className="border-b px-4 py-3 text-sm font-semibold">Client accounts</p>
              {data.clients.length === 0 && <div className="p-6"><EmptyState icon={Building} title="No clients yet" description="Create one; you can copy agents, automations and forms in as a blueprint." /></div>}
              {data.clients.map((c: any) => (
                <div key={c.id} className="flex flex-wrap items-center gap-3 border-b px-4 py-3 text-sm last:border-0">
                  <span className="grid size-8 place-items-center rounded-lg bg-muted font-semibold">{c.name[0]}</span>
                  <div className="min-w-[160px] flex-1"><p className="font-medium">{c.name}</p><p className="text-xs text-muted-foreground">{c.agents} agents · {c.usage.voice_minutes} voice min · {c.usage.ai_calls} AI calls</p></div>
                  <Badge variant="outline">{c.plan}</Badge>
                  <span className="w-40 text-right text-xs"><b>{data.rebilling.currency} {(c.rebill.base_fee + c.rebill.usage_charge).toLocaleString()}</b><br /><span className="text-muted-foreground">fee {c.rebill.base_fee} + usage {c.rebill.usage_charge}</span></span>
                  <Button size="sm" variant="outline" onClick={() => open(c.id)}>Open <ArrowRight className="size-3.5" /></Button>
                </div>
              ))}
            </Card>
            <div className="grid gap-6 lg:grid-cols-2">
              <Branding />
              {rb && (
                <Card className="gap-3 p-5">
                  <Section title="Rebilling defaults" description="Used for new clients; each client can be overridden.">
                    <div className="grid grid-cols-2 gap-3">
                      <TextField label="Currency" value={rb.currency} onChange={(v) => setRb({ ...rb, currency: v.toUpperCase() })} />
                      <TextField label="Monthly platform fee" type="number" value={String(rb.default_monthly_fee)} onChange={(v) => setRb({ ...rb, default_monthly_fee: Number(v) })} />
                      <TextField label="Price per voice minute" type="number" value={String(rb.default_voice_minute_rate)} onChange={(v) => setRb({ ...rb, default_voice_minute_rate: Number(v) })} />
                      <TextField label="Markup on AI costs (%)" type="number" value={String(rb.default_markup_pct)} onChange={(v) => setRb({ ...rb, default_markup_pct: Number(v) })} />
                    </div>
                    <Button size="sm" className="w-fit" onClick={() => saveRb.mutate()}><Copy className="size-3.5" /> Save defaults</Button>
                  </Section>
                </Card>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
