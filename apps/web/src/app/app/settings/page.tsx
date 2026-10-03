"use client";

import { OrganizationProfile } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, Copy, CreditCard, ExternalLink, KeyRound, Loader2, Plus, ScrollText, Settings, Shield, Trash2, Users, Webhook, XCircle } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/agent/fields";
import { PageHeader, Section, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApi } from "@/lib/api";
import { CLERK_ENABLED, isDevSession } from "@/lib/env";
import { timeAgo } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { cn } from "@/lib/utils";

function General() {
  const api = useApi();
  const { me, refetch } = useWorkspace();
  const [name, setName] = useState(me?.workspace.name || "");
  const [tz, setTz] = useState(me?.workspace.timezone || "Asia/Kolkata");
  const [cur, setCur] = useState(me?.workspace.currency || "INR");
  const [secret, setSecret] = useState<string | null>(null);
  const save = useMutation({ mutationFn: (b: any) => api.patch("/workspace", b), onSuccess: () => { refetch(); toast.success("Saved"); } });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-4 p-5">
        <Section title="Workspace">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Timezone"><Input value={tz} onChange={(e) => setTz(e.target.value)} /></Field>
            <Field label="Currency">
              <Select value={cur} onValueChange={setCur}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{["INR", "USD", "EUR", "GBP", "AED", "SGD"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
          <Button onClick={() => save.mutate({ name, timezone: tz, currency: cur })} disabled={save.isPending}>Save</Button>
        </Section>
      </Card>
      <Card className="gap-4 p-5">
        <Section title="Widget identity verification" description="Sign your logged-in users' IDs with HMAC-SHA256 so the widget can trust who they are (and link their history securely).">
          <Button variant="outline" onClick={() => { const s = crypto.randomUUID().replaceAll("-", "") + crypto.randomUUID().replaceAll("-", ""); setSecret(s); save.mutate({ identity_secret: s }); }}>
            Generate new secret
          </Button>
          {secret && <code className="block break-all rounded bg-muted p-2 font-mono text-[11px]">{secret}</code>}
          <pre className="whitespace-pre-wrap rounded-lg bg-muted/50 p-3 font-mono text-[11px]">{`// your server
user_hash = hmac_sha256(secret, user_id).hex()
// your page
window.UnisonaSettings = { userId, userHash, name, email }`}</pre>
        </Section>
      </Card>
    </div>
  );
}

function Members() {
  const api = useApi();
  const { data } = useQuery({ queryKey: ["members"], queryFn: () => api.get("/members") });
  const dev = isDevSession();
  return (
    <div className="space-y-6">
      {CLERK_ENABLED && !dev && (
        <Card className="overflow-hidden p-0">
          <OrganizationProfile routing="hash" appearance={{ elements: { rootBox: "w-full", cardBox: "w-full shadow-none border-0" } }} />
        </Card>
      )}
      {dev && <p className="text-sm text-muted-foreground">Invitations and roles are managed through Clerk Organizations. Sign in with Clerk to invite teammates.</p>}
      <Card className="gap-0 p-0">
        <p className="border-b px-5 py-3 text-sm font-semibold">People in this workspace</p>
        {(data?.items || []).map((m: any) => (
          <div key={m.id} className="flex items-center gap-3 border-b px-5 py-3 text-sm last:border-0">
            <span className={cn("size-2 rounded-full", m.online ? "bg-success" : "bg-muted-foreground/30")} />
            <span className="flex-1">{m.name || m.email || m.user_id}</span>
            <span className="text-xs text-muted-foreground">{m.email}</span>
            <Badge variant="outline" className="capitalize">{m.role}</Badge>
            <span className="w-24 text-right text-xs text-muted-foreground">{timeAgo(m.last_seen_at)}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}

function Providers() {
  const api = useApi();
  const qc = useQueryClient();
  const { refetch } = useWorkspace();
  const { data: cat } = useQuery({ queryKey: ["providers-catalog"], queryFn: () => api.get("/providers/catalog") });
  const { data: keys } = useQuery({ queryKey: ["provider-keys"], queryFn: () => api.get("/providers") });
  const [editing, setEditing] = useState<string | null>(null);
  const [key, setKey] = useState("");
  const [base, setBase] = useState("");
  const [whsec, setWhsec] = useState("");
  const save = useMutation({
    mutationFn: (p: string) => api.put(`/providers/${p}`, { api_key: key, base_url: base || undefined, extra: whsec ? { webhook_secret: whsec } : undefined }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["provider-keys"] });
      refetch();
      if (r.status === "valid") { toast.success("Key validated and saved (encrypted)"); setEditing(null); setKey(""); setBase(""); }
      else toast.error(r.error || "Key rejected");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const del = useMutation({ mutationFn: (p: string) => api.del(`/providers/${p}`), onSuccess: () => { qc.invalidateQueries({ queryKey: ["provider-keys"] }); refetch(); } });
  const byProvider: Record<string, any> = Object.fromEntries((keys?.items || []).map((k: any) => [k.provider, k]));
  const groups = [["llm", "Language models"], ["s2s", "Speech-to-speech (realtime)"], ["stt", "Speech-to-text"], ["tts", "Voices (text-to-speech)"], ["payments", "Customer payments (your account)"]];
  return (
    <div className="space-y-6">
      <Card className="flex-row items-start gap-3 bg-brand-soft/40 p-4 text-sm">
        <Shield className="mt-0.5 size-4 text-brand" />
        <p>Bring your own keys: you pay providers directly at cost, and we never mark up tokens. Keys are validated live, envelope-encrypted (AES-256-GCM, per-workspace key) and never shown again. If a provider fails, agents automatically fall back to your next provider.</p>
      </Card>
      {groups.map(([g, label]) => (
        <Section key={g} title={label}>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(cat?.providers || []).filter((p: any) => p.categories[0] === g || (g !== "llm" && p.categories.includes(g) && !p.categories.includes("llm"))).map((p: any) => {
              const k = byProvider[p.id];
              return (
                <Card key={p.id} className="gap-2 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">{p.name}</p>
                    {k ? <StatusBadge status={k.status} /> : !p.needs_key ? <Badge variant="secondary">no key needed</Badge> : p.platform_key ? <Badge variant="secondary">platform trial key</Badge> : null}
                  </div>
                  <p className="min-h-8 text-xs text-muted-foreground">{p.notes || p.categories.join(" · ")}</p>
                  {k && <p className="font-mono text-xs">{k.masked} · checked {timeAgo(k.last_validated_at)}</p>}
                  {k?.error && <p className="text-xs text-destructive">{k.error}</p>}
                  {editing === p.id ? (
                    <div className="space-y-2">
                      {p.needs_key && <Input type="password" placeholder={p.id === "razorpay" ? "key_id:key_secret" : "API key"} value={key} onChange={(e) => setKey(e.target.value)} autoFocus />}
                      {p.categories.includes("payments") && <Input type="password" placeholder="Webhook signing secret (optional)" value={whsec} onChange={(e) => setWhsec(e.target.value)} />}
                      {p.custom_base_url && <Input placeholder={p.id === "ollama" ? "http://localhost:11434/v1" : "https://your-endpoint/v1"} value={base} onChange={(e) => setBase(e.target.value)} />}
                      <div className="flex gap-2">
                        <Button size="sm" disabled={save.isPending || (p.needs_key && !key)} onClick={() => save.mutate(p.id)}>{save.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />} Validate & save</Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      {(p.needs_key || p.custom_base_url) && <Button size="sm" variant="outline" onClick={() => { setEditing(p.id); setKey(""); setBase(""); }}>{k ? "Replace key" : "Add key"}</Button>}
                      {k && <Button size="sm" variant="ghost" onClick={() => del.mutate(p.id)}><Trash2 className="size-3.5" /></Button>}
                      {p.docs_url && <Button size="sm" variant="ghost" asChild><a href={p.docs_url} target="_blank" rel="noreferrer">Get key <ExternalLink className="size-3" /></a></Button>}
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </Section>
      ))}
    </div>
  );
}

function Billing() {
  const api = useApi();
  const [cur, setCur] = useState<"INR" | "USD">("INR");
  const { data: plans } = useQuery({ queryKey: ["plans"], queryFn: () => api.get("/billing/plans") });
  const { data: usage } = useQuery({ queryKey: ["billing-usage"], queryFn: () => api.get("/billing/usage") });
  const checkout = useMutation({
    mutationFn: (plan: string) => api.post("/billing/checkout", { plan, currency: cur }),
    onSuccess: (r) => { if (r.checkout_url || r.url) window.location.href = r.checkout_url || r.url; },
    onError: (e: Error) => toast.error(e.message),
  });
  const p = usage?.plan;
  const u = usage?.usage;
  return (
    <div className="space-y-6">
      {p && u && (
        <Card className="gap-4 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Current plan</p>
              <p className="text-2xl font-semibold">{p.name}</p>
            </div>
            <Badge variant="secondary">Provider spend this month: ${u.provider_spend_usd}</Badge>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            {[["Voice minutes", u.voice_minutes, p.voice_minutes], ["AI messages", u.messages, p.messages], ["Agents", u.agents, p.agents]].map(([l, v, max]: any) => (
              <div key={l} className="space-y-1.5">
                <div className="flex justify-between text-xs"><span>{l}</span><span className="tabular-nums">{v} / {max >= 9999 ? "∞" : max.toLocaleString()}</span></div>
                <Progress value={Math.min(100, (v / Math.max(1, max)) * 100)} />
              </div>
            ))}
          </div>
        </Card>
      )}
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Plans · unlimited channels on every plan</p>
        <div className="inline-flex rounded-full border p-0.5 text-xs">
          {(["INR", "USD"] as const).map((c) => <button key={c} onClick={() => setCur(c)} className={cn("rounded-full px-3 py-1", cur === c && "bg-foreground text-background")}>{c}</button>)}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        {(plans?.plans || []).map((pl: any) => (
          <Card key={pl.id} className={cn("gap-2 p-4", pl.popular && "border-brand", p?.id === pl.id && "ring-2 ring-brand/30")}>
            <p className="font-medium">{pl.name}</p>
            <p className="text-xl font-semibold">{pl.inr === null ? "Custom" : cur === "INR" ? `₹${pl.inr.toLocaleString("en-IN")}` : `$${pl.usd}`}<span className="text-xs font-normal text-muted-foreground">{pl.inr !== null && "/mo"}</span></p>
            <ul className="flex-1 space-y-1 text-xs text-muted-foreground">{pl.features.map((f: string) => <li key={f}>• {f}</li>)}</ul>
            {p?.id === pl.id ? <Badge className="justify-center">Current</Badge> : pl.inr === null ? (
              <Button size="sm" variant="outline" asChild><a href="mailto:hello@unisona.si">Contact sales</a></Button>
            ) : pl.inr > 0 ? (
              <Button size="sm" variant={pl.popular ? "default" : "outline"} onClick={() => checkout.mutate(pl.id)} disabled={checkout.isPending}><CreditCard className="size-3.5" /> Upgrade</Button>
            ) : null}
          </Card>
        ))}
      </div>
      {plans && !plans.payments_enabled && <p className="text-xs text-muted-foreground">Payments are not configured in this environment (add DODO_PAYMENTS_API_KEY to .env).</p>}
    </div>
  );
}

function ApiKeys() {
  const api = useApi();
  const qc = useQueryClient();
  const [secret, setSecret] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["api-keys"], queryFn: () => api.get("/api-keys") });
  const create = useMutation({ mutationFn: () => api.post("/api-keys", { name: prompt("Key name") || "API key" }), onSuccess: (r) => { setSecret(r.secret); qc.invalidateQueries({ queryKey: ["api-keys"] }); } });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/api-keys/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }) });
  return (
    <div className="space-y-4">
      <Card className="gap-3 p-5">
        <Section title="API keys" description="Use with the REST API (Authorization: Bearer usk_…) or the MCP server at /mcp for Claude, Cursor and other assistants." actions={<Button size="sm" onClick={() => create.mutate()}><Plus className="size-3.5" /> New key</Button>}>
          {secret && (
            <div className="rounded-lg border border-success/40 bg-success/5 p-3 text-sm">
              <p className="font-medium">Copy your key now. It won&apos;t be shown again.</p>
              <div className="mt-2 flex gap-2"><code className="flex-1 break-all font-mono text-xs">{secret}</code><Button size="icon" variant="ghost" onClick={() => { navigator.clipboard.writeText(secret); toast.success("Copied"); }}><Copy className="size-3.5" /></Button></div>
            </div>
          )}
          {(data?.items || []).map((k: any) => (
            <div key={k.id} className="flex items-center gap-3 rounded-lg border p-3 text-sm">
              <KeyRound className="size-4 text-muted-foreground" />
              <span className="flex-1">{k.name} <span className="font-mono text-xs text-muted-foreground">{k.prefix}…</span></span>
              <span className="text-xs text-muted-foreground">{k.last_used_at ? `used ${timeAgo(k.last_used_at)}` : "never used"}</span>
              <Button size="icon" variant="ghost" onClick={() => del.mutate(k.id)}><Trash2 className="size-3.5" /></Button>
            </div>
          ))}
        </Section>
      </Card>
    </div>
  );
}

function Webhooks() {
  const api = useApi();
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const { data } = useQuery({ queryKey: ["webhooks"], queryFn: () => api.get("/webhook-endpoints") });
  const { data: deliveries } = useQuery({ queryKey: ["webhook-deliveries"], queryFn: () => api.get("/webhook-deliveries"), refetchInterval: 10000 });
  const create = useMutation({ mutationFn: () => api.post("/webhook-endpoints", { url, events }), onSuccess: (r) => { toast.success(`Created. Signing secret: ${r.secret}`, { duration: 20000 }); setUrl(""); qc.invalidateQueries({ queryKey: ["webhooks"] }); }, onError: (e: Error) => toast.error(e.message) });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/webhook-endpoints/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["webhooks"] }) });
  const test = useMutation({ mutationFn: (id: string) => api.post(`/webhook-endpoints/${id}/test`), onSuccess: () => toast.success("Test event sent") });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-3 p-5">
        <Section title="Endpoints" description="Signed with HMAC-SHA256 (x-unisona-signature). Retried with backoff. Works with Zapier, Make, n8n.">
          <Input placeholder="https://hooks.zapier.com/…" value={url} onChange={(e) => setUrl(e.target.value)} />
          <div className="grid grid-cols-2 gap-1.5">
            {(data?.events || []).map((e: string) => (
              <label key={e} className="flex items-center gap-2 text-xs"><Checkbox checked={events.includes(e)} onCheckedChange={(c) => setEvents(c ? [...events, e] : events.filter((x) => x !== e))} /> {e}</label>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground">No events selected = all events.</p>
          <Button size="sm" disabled={!url} onClick={() => create.mutate()}>Add endpoint</Button>
          {(data?.items || []).map((w: any) => (
            <div key={w.id} className="flex items-center gap-2 rounded-lg border p-2.5 text-xs">
              <Webhook className="size-3.5 text-muted-foreground" />
              <span className="flex-1 truncate">{w.url}</span>
              <Badge variant="outline">{w.events.length || "all"} events</Badge>
              <Button size="sm" variant="ghost" className="h-6" onClick={() => test.mutate(w.id)}>Test</Button>
              <Button size="icon" variant="ghost" className="size-6" onClick={() => del.mutate(w.id)}><Trash2 className="size-3" /></Button>
            </div>
          ))}
        </Section>
      </Card>
      <Card className="gap-2 p-5">
        <Section title="Recent deliveries">
          {(deliveries?.items || []).length === 0 && <p className="text-sm text-muted-foreground">No deliveries yet.</p>}
          {(deliveries?.items || []).slice(0, 30).map((d: any) => (
            <div key={d.id} className="flex items-center gap-2 text-xs">
              {d.status === "delivered" ? <CheckCircle2 className="size-3.5 text-success" /> : <XCircle className="size-3.5 text-destructive" />}
              <span className="font-mono">{d.event}</span>
              <span className="text-muted-foreground">{d.response_code ?? "—"} · {d.attempts} tries</span>
              <span className="ml-auto text-muted-foreground">{timeAgo(d.created_at)}</span>
            </div>
          ))}
        </Section>
      </Card>
    </div>
  );
}

function Compliance() {
  const api = useApi();
  const qc = useQueryClient();
  const [num, setNum] = useState("");
  const { data } = useQuery({ queryKey: ["dnd"], queryFn: () => api.get("/crm/dnd") });
  const add = useMutation({ mutationFn: () => api.post("/crm/dnd", { value: num, reason: "manual" }), onSuccess: () => { setNum(""); qc.invalidateQueries({ queryKey: ["dnd"] }); } });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/crm/dnd/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["dnd"] }) });
  return (
    <Card className="gap-3 p-5">
      <Section title="Do-not-call list" description="Numbers here are never dialled by campaigns or automations, and incoming calls from them are rejected. Opt-outs are added automatically.">
        <div className="flex gap-2"><Input placeholder="+91…" value={num} onChange={(e) => setNum(e.target.value)} /><Button disabled={!num} onClick={() => add.mutate()}>Block</Button></div>
        {(data?.items || []).map((d: any) => (
          <div key={d.id} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"><span className="flex-1 font-mono">{d.value}</span><span className="text-xs text-muted-foreground">{d.reason}</span><Button size="icon" variant="ghost" className="size-7" onClick={() => del.mutate(d.id)}><Trash2 className="size-3.5" /></Button></div>
        ))}
      </Section>
    </Card>
  );
}

function Audit() {
  const api = useApi();
  const { data } = useQuery({ queryKey: ["audit"], queryFn: () => api.get("/audit") });
  return (
    <Card className="gap-0 p-0">
      {(data?.items || []).map((a: any) => (
        <div key={a.id} className="flex items-center gap-3 border-b px-5 py-2.5 text-sm last:border-0">
          <ScrollText className="size-3.5 text-muted-foreground" />
          <span className="font-mono text-xs">{a.action}</span>
          <span className="truncate text-xs text-muted-foreground">{a.target}</span>
          <span className="ml-auto text-xs text-muted-foreground">{a.actor} · {timeAgo(a.created_at)}</span>
        </div>
      ))}
      {(data?.items || []).length === 0 && <p className="p-6 text-sm text-muted-foreground">No activity yet.</p>}
    </Card>
  );
}

function SettingsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") || "general";
  return (
    <div>
      <PageHeader icon={Settings} title="Settings" description="Workspace, team, AI providers, billing and developer settings." />
      <Tabs value={tab} onValueChange={(t) => router.replace(`/app/settings?tab=${t}`)} className="p-6">
        <TabsList className="flex-wrap">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="members"><Users className="size-3.5" /> Team</TabsTrigger>
          <TabsTrigger value="providers"><KeyRound className="size-3.5" /> AI providers</TabsTrigger>
          <TabsTrigger value="billing"><CreditCard className="size-3.5" /> Billing</TabsTrigger>
          <TabsTrigger value="api">API & MCP</TabsTrigger>
          <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
          <TabsTrigger value="compliance">Compliance</TabsTrigger>
          <TabsTrigger value="audit">Audit log</TabsTrigger>
        </TabsList>
        <div className="mt-6">
          <TabsContent value="general"><General /></TabsContent>
          <TabsContent value="members"><Members /></TabsContent>
          <TabsContent value="providers"><Providers /></TabsContent>
          <TabsContent value="billing"><Billing /></TabsContent>
          <TabsContent value="api"><ApiKeys /></TabsContent>
          <TabsContent value="webhooks"><Webhooks /></TabsContent>
          <TabsContent value="compliance"><Compliance /></TabsContent>
          <TabsContent value="audit"><Audit /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

export default function SettingsPage() {
  return <Suspense><SettingsInner /></Suspense>;
}
