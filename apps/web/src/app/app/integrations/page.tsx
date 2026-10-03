"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Blocks, Calendar, Globe, Loader2, PlugZap, Plus, ServerCog, Sheet as SheetIcon, Trash2, Webhook, Zap } from "lucide-react";
import Link from "next/link";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/agent/fields";
import { NativeIntegrations } from "@/components/app/native-integrations";
import { PageHeader, Section } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { API_URL } from "@/lib/env";

const CATALOG = [
  { icon: Zap, name: "Zapier · Make · n8n", text: "Send every event (calls, leads, bookings) to 6,000+ apps via signed webhooks.", href: "/app/settings?tab=webhooks", cta: "Set up webhooks" },
  { icon: Calendar, name: "Built-in booking calendar", text: "Agents check availability and book. Share a public booking page.", href: "/app/crm/calendar", cta: "Open calendar" },
  { icon: ServerCog, name: "MCP servers", text: "Give agents tools from any MCP server (Streamable HTTP).", href: "#mcp", cta: "Connect below" },
  { icon: Globe, name: "Any REST API", text: "Order lookup, CRM sync, payments, inventory. Describe it and the agent calls it.", href: "#http", cta: "Add below" },
  { icon: SheetIcon, name: "Spreadsheets", text: "Upload CSV/Excel to Knowledge and agents query it with safe SQL.", href: "/app/knowledge", cta: "Upload" },
  { icon: Blocks, name: "Unisona MCP server", text: "Let Claude, Cursor or any MCP client operate your workspace.", href: "/app/settings?tab=api", cta: "Create API key" },
];

export default function IntegrationsPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data: tools } = useQuery({ queryKey: ["tools"], queryFn: () => api.get("/tools") });
  const [http, setHttp] = useState({ name: "", description: "", url: "", method: "POST", params: '{"type":"object","properties":{"order_id":{"type":"string","description":"Order ID"}},"required":["order_id"]}', header: "", secret: "" });
  const [mcp, setMcp] = useState({ url: "", token: "" });
  const [found, setFound] = useState<any[]>([]);
  const [testOut, setTestOut] = useState<Record<string, string>>({});
  const createHttp = useMutation({
    mutationFn: () => {
      let parameters;
      try { parameters = JSON.parse(http.params); } catch { throw new Error("Parameters must be valid JSON schema"); }
      return api.post("/tools", { name: http.name, description: http.description, type: "http", config: { url: http.url, method: http.method, parameters, headers: http.header ? { Authorization: "{{token}}" } : {} }, secret: http.secret ? { token: http.secret } : undefined });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["tools"] }); toast.success("Tool added. Enable it on an agent's Tools tab."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const discover = useMutation({ mutationFn: () => api.post("/tools/mcp/discover", mcp), onSuccess: (r) => setFound(r.tools), onError: (e: Error) => toast.error(e.message) });
  const addMcp = useMutation({ mutationFn: (t: any) => api.post("/tools", { name: t.name, description: t.description, type: "mcp", config: { url: mcp.url, remote_name: t.name, parameters: t.parameters }, secret: mcp.token ? { token: mcp.token } : undefined }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["tools"] }); toast.success("MCP tool added"); } });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/tools/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["tools"] }) });
  const test = useMutation({ mutationFn: ({ id, args }: { id: string; args: any }) => api.post(`/tools/${id}/test`, { args }), onSuccess: (r, v) => setTestOut((o) => ({ ...o, [v.id]: r.result })) });

  return (
    <div>
      <PageHeader icon={PlugZap} title="Integrations" description="Connect agents to your systems: tools they can call mid-conversation, and events your other apps receive." />
      <div className="space-y-8 p-6">
        <Suspense><NativeIntegrations /></Suspense>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {CATALOG.map((c) => (
            <Card key={c.name} className="gap-2 p-4">
              <c.icon className="size-5 text-brand" />
              <p className="font-medium">{c.name}</p>
              <p className="flex-1 text-xs text-muted-foreground">{c.text}</p>
              <Button size="sm" variant="outline" asChild className="w-fit"><Link href={c.href}>{c.cta}</Link></Button>
            </Card>
          ))}
        </div>
        <div className="grid gap-6 xl:grid-cols-2">
          <Card id="http" className="gap-3 p-5">
            <Section title="Add an API tool" description="The agent decides when to call it, using the description and parameters you give.">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Name"><Input value={http.name} placeholder="lookup_order" onChange={(e) => setHttp({ ...http, name: e.target.value })} /></Field>
                <Field label="Method"><Select value={http.method} onValueChange={(v) => setHttp({ ...http, method: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["GET", "POST", "PUT", "PATCH"].map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select></Field>
              </div>
              <Field label="Description (when should the agent use it?)"><Input value={http.description} placeholder="Look up an order's status by order ID" onChange={(e) => setHttp({ ...http, description: e.target.value })} /></Field>
              <Field label="URL" hint="Use {{param}} placeholders, plus {{contact_phone}}, {{contact_email}}, {{conversation_id}}."><Input value={http.url} placeholder="https://api.yourstore.com/orders/{{order_id}}" onChange={(e) => setHttp({ ...http, url: e.target.value })} /></Field>
              <Field label="Parameters (JSON schema)"><Textarea rows={4} className="font-mono text-xs" value={http.params} onChange={(e) => setHttp({ ...http, params: e.target.value })} /></Field>
              <Field label="Auth header value (optional, stored encrypted)" hint="Sent as Authorization header."><Input type="password" value={http.secret} placeholder="Bearer sk_…" onChange={(e) => setHttp({ ...http, secret: e.target.value, header: e.target.value ? "1" : "" })} /></Field>
              <Button disabled={!http.name || !http.url || createHttp.isPending} onClick={() => createHttp.mutate()}><Plus className="size-4" /> Add tool</Button>
            </Section>
          </Card>
          <div className="space-y-6">
            <Card id="mcp" className="gap-3 p-5">
              <Section title="Connect an MCP server" description="Discover its tools, then add the ones your agents may use.">
                <Input placeholder="https://mcp.example.com/mcp" value={mcp.url} onChange={(e) => setMcp({ ...mcp, url: e.target.value })} />
                <Input type="password" placeholder="Bearer token (optional)" value={mcp.token} onChange={(e) => setMcp({ ...mcp, token: e.target.value })} />
                <Button variant="outline" disabled={!mcp.url || discover.isPending} onClick={() => discover.mutate()}>{discover.isPending ? <Loader2 className="size-4 animate-spin" /> : "Discover tools"}</Button>
                {found.map((t) => (
                  <div key={t.name} className="flex items-center gap-2 rounded-md border p-2 text-xs">
                    <span className="flex-1"><b className="font-mono">{t.name}</b> · {t.description}</span>
                    <Button size="sm" className="h-7" onClick={() => addMcp.mutate(t)}>Add</Button>
                  </div>
                ))}
              </Section>
            </Card>
            <Card className="gap-3 p-5">
              <Section title="Your tools">
                {(tools?.items || []).length === 0 && <p className="text-sm text-muted-foreground">No tools yet.</p>}
                {(tools?.items || []).map((t: any) => (
                  <div key={t.id} className="space-y-2 rounded-lg border p-3">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{t.type}</Badge>
                      <p className="flex-1 font-mono text-sm">{t.name}</p>
                      <Button size="sm" variant="ghost" onClick={() => { const a = prompt("Test arguments (JSON)", "{}"); if (a) test.mutate({ id: t.id, args: JSON.parse(a) }); }}>Test</Button>
                      <Button size="icon" variant="ghost" onClick={() => del.mutate(t.id)}><Trash2 className="size-3.5" /></Button>
                    </div>
                    <p className="text-xs text-muted-foreground">{t.description}</p>
                    {testOut[t.id] && <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-muted/50 p-2 text-[11px]">{testOut[t.id]}</pre>}
                  </div>
                ))}
              </Section>
            </Card>
            <Card className="gap-2 p-5">
              <p className="flex items-center gap-2 text-sm font-semibold"><Webhook className="size-4" /> Unisona MCP endpoint</p>
              <code className="rounded bg-muted p-2 font-mono text-xs">{API_URL}/mcp/</code>
              <p className="text-xs text-muted-foreground">Tools: list_agents, ask_agent, search_knowledge, add_knowledge, crm_search_contacts, crm_create_task, get_conversation, workspace_summary. Authenticate with a workspace API key.</p>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
