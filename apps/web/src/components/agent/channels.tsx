"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Check, Copy, ExternalLink, FileText, Globe, Mail, MessageCircle, MessageSquareText, MessagesSquare, Mic, Phone, Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Field, ListField, SwitchRow, TextField } from "@/components/agent/fields";
import { Section, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useApi } from "@/lib/api";
import { API_URL } from "@/lib/env";
import { cn } from "@/lib/utils";

function CopyBox({ value, label }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <div className="space-y-1">
      {label && <p className="text-xs font-medium">{label}</p>}
      <div className="flex items-start gap-2 rounded-lg border bg-muted/40 p-2.5">
        <code className="flex-1 break-all font-mono text-[11px]">{value}</code>
        <Button
          size="icon"
          variant="ghost"
          className="size-7 shrink-0"
          onClick={() => {
            navigator.clipboard.writeText(value);
            setDone(true);
            setTimeout(() => setDone(false), 1500);
          }}
        >
          {done ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
        </Button>
      </div>
    </div>
  );
}

function WaTemplates({ channelId }: { channelId: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const { data, error, isLoading } = useQuery({ queryKey: ["wa-templates", channelId], queryFn: () => api.get(`/whatsapp/${channelId}/templates`), retry: false });
  const [form, setForm] = useState({ name: "", category: "UTILITY", language: "en", body: "Hi {{1}}, your appointment is confirmed for {{2}}." });
  const create = useMutation({
    mutationFn: () => api.post(`/whatsapp/${channelId}/templates`, form),
    onSuccess: () => { toast.success("Template submitted to Meta for approval"); qc.invalidateQueries({ queryKey: ["wa-templates", channelId] }); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <div className="space-y-4">
      <div className="max-h-64 space-y-2 overflow-y-auto">
        {isLoading && <p className="text-sm text-muted-foreground">Loading templates…</p>}
        {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}
        {(data?.items || []).map((t: any) => (
          <div key={t.name + t.language} className="rounded-lg border p-2.5 text-sm">
            <div className="flex items-center gap-2"><span className="flex-1 font-mono text-xs">{t.name}</span><Badge variant="outline">{t.language}</Badge><StatusBadge status={String(t.status).toLowerCase()} /></div>
            <p className="mt-1 text-xs text-muted-foreground">{(t.components || []).find((c: any) => c.type === "BODY")?.text}</p>
          </div>
        ))}
      </div>
      <div className="space-y-2 rounded-lg border p-3">
        <p className="text-sm font-medium">New template</p>
        <div className="grid grid-cols-3 gap-2">
          <Input placeholder="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="UTILITY">Utility</SelectItem><SelectItem value="MARKETING">Marketing</SelectItem><SelectItem value="AUTHENTICATION">Authentication</SelectItem></SelectContent>
          </Select>
          <Input placeholder="language" value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })} />
        </div>
        <Textarea rows={3} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
        <p className="text-[11px] text-muted-foreground">Use {"{{1}}"}, {"{{2}}"} for variables. Meta reviews templates (usually minutes). Approved templates appear in Campaigns.</p>
        <Button size="sm" disabled={!form.name || create.isPending} onClick={() => create.mutate()}>Submit for approval</Button>
      </div>
    </div>
  );
}

function MetaPage({ kind, agentId, chans, upsert }: { kind: "instagram" | "messenger"; agentId: string; chans: any[]; upsert: any }) {
  const [v, setV] = useState({ id: "", token: "" });
  const key = kind === "instagram" ? "ig_user_id" : "page_id";
  const Icon = kind === "instagram" ? Camera : MessagesSquare;
  return (
    <Card className="gap-4 p-5">
      <Section title={kind === "instagram" ? "Instagram DMs" : "Facebook Messenger"} description={kind === "instagram" ? "Reply to Instagram DMs (professional account linked to a Facebook Page)." : "Reply to messages sent to your Facebook Page."}>
        {chans.map((c) => (
          <div key={c.id} className="flex items-center gap-2 rounded-lg border p-2.5 text-sm">
            <Icon className="size-4" />
            <span className="flex-1">{c.config.account_name || c.config[key]}</span>
            <StatusBadge status={c.enabled ? c.status : "paused"} />
            <Switch checked={c.enabled} onCheckedChange={(on) => upsert.mutate({ id: c.id, type: kind, enabled: on })} />
          </div>
        ))}
        <TextField label={kind === "instagram" ? "Instagram account ID" : "Facebook Page ID"} value={v.id} onChange={(x) => setV({ ...v, id: x })} />
        <TextField label="Page access token" type="password" value={v.token} onChange={(x) => setV({ ...v, token: x })} />
        <Button disabled={!v.id || !v.token || upsert.isPending} onClick={() => upsert.mutate({ type: kind, enabled: true, config: { [key]: v.id }, secret: { page_token: v.token } })}>Connect</Button>
        <CopyBox label="Webhook URL for your Meta app (same app as WhatsApp)" value={`${API_URL}/webhooks/meta`} />
      </Section>
    </Card>
  );
}

const QUICK = [
  { type: "web", icon: Globe, title: "Web chat page", text: "A hosted chat page with citations and voice." },
  { type: "widget", icon: Sparkles, title: "Website widget", text: "Chat + voice bubble on your site with one script tag." },
  { type: "voice", icon: Mic, title: "Browser voice calls", text: "Talk from the widget, hosted page or playground over WebRTC." },
];

export function ChannelsPanel({ agent, cfg, set }: { agent: any; cfg: any; set: (p: string, v: any) => void }) {
  const api = useApi();
  const qc = useQueryClient();
  const chans: any[] = agent.channels || [];
  const byType = (t: string) => chans.filter((c) => c.type === t);
  const upsert = useMutation({
    mutationFn: (body: any) => api.post(`/agents/${agent.id}/channels`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agent", agent.id] });
      toast.success("Channel updated");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const [tg, setTg] = useState("");
  const [wa, setWa] = useState({ phone_number_id: "", waba_id: "", access_token: "" });
  const [ph, setPh] = useState({ provider: "twilio", phone_number: "", account_sid: "", auth_token: "", api_key: "", api_token: "", subdomain: "api.exotel.com", auth_id: "", connection_id: "" });
  const appUrl = typeof window !== "undefined" ? window.location.origin : "";
  const embed = `<script src="${API_URL}/widget/widget.js" data-agent="${agent.public_key}" data-api="${API_URL}" async></script>`;
  const w = cfg.widget;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {QUICK.map((q) => {
          const ch = byType(q.type)[0];
          return (
            <Card key={q.type} className="gap-3 p-4">
              <div className="flex items-center justify-between">
                <span className="grid size-9 place-items-center rounded-lg bg-brand-soft text-brand"><q.icon className="size-4" /></span>
                <Switch checked={!!ch?.enabled} onCheckedChange={(on) => upsert.mutate({ type: q.type, enabled: on })} />
              </div>
              <div>
                <p className="text-sm font-medium">{q.title}</p>
                <p className="text-xs text-muted-foreground">{q.text}</p>
              </div>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="gap-4 p-5">
          <Section title="Install on your website" description="Paste before </body>. Works on any site: WordPress, Shopify, Webflow, React…">
            <CopyBox label="Embed code" value={embed} />
            <CopyBox label="Hosted chat page (share anywhere, QR codes, ads)" value={`${appUrl}/chat/${agent.public_key}`} />
            <Button asChild size="sm" variant="outline">
              <a href={`/chat/${agent.public_key}`} target="_blank" rel="noreferrer">
                <ExternalLink className="size-3.5" /> Open hosted page
              </a>
            </Button>
            {agent.status === "draft" && <p className="text-xs text-warning">Publish the agent so the widget uses your latest configuration.</p>}
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="Widget appearance">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Brand colour">
                <div className="flex gap-2">
                  <Input type="color" className="h-9 w-14 p-1" value={w.color} onChange={(e) => set("widget.color", e.target.value)} />
                  <Input value={w.color} onChange={(e) => set("widget.color", e.target.value)} />
                </div>
              </Field>
              <Field label="Position">
                <Select value={w.position} onValueChange={(v) => set("widget.position", v)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="right">Bottom right</SelectItem>
                    <SelectItem value="left">Bottom left</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <TextField label="Title" value={w.title} onChange={(v) => set("widget.title", v)} placeholder={cfg.business?.name || "Chat with us"} />
              <TextField label="Subtitle" value={w.subtitle} onChange={(v) => set("widget.subtitle", v)} />
            </div>
            <SwitchRow label="Voice button in widget" checked={w.voice} onChange={(v) => set("widget.voice", v)} />
            <ListField label="Conversation starters" values={w.starters || []} onChange={(v) => set("widget.starters", v)} placeholder="e.g. What are your timings?" />
            <ListField label="Allowed domains" hint="Leave empty to allow any site." values={w.allowed_domains || []} onChange={(v) => set("widget.allowed_domains", v)} placeholder="example.com" />
          </Section>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="gap-4 p-5">
          <Section title="Telegram" description="Create a bot with @BotFather, paste the token. Works on localhost (polling).">
            {byType("telegram").map((c) => (
              <div key={c.id} className="flex items-center gap-2 rounded-lg border p-2.5 text-sm">
                <Send className="size-4 text-ch-telegram" />
                <span className="flex-1">@{c.config.bot_username}</span>
                <StatusBadge status={c.enabled ? c.status : "paused"} />
                <Switch checked={c.enabled} onCheckedChange={(on) => upsert.mutate({ id: c.id, type: "telegram", enabled: on })} />
              </div>
            ))}
            <div className="flex gap-2">
              <Input placeholder="123456:ABC-DEF… bot token" value={tg} onChange={(e) => setTg(e.target.value)} />
              <Button disabled={!tg || upsert.isPending} onClick={() => upsert.mutate({ type: "telegram", enabled: true, secret: { bot_token: tg } }, { onSuccess: () => setTg("") })}>Connect</Button>
            </div>
            <p className="text-[11px] text-muted-foreground">Customers can tap “Share my phone number” (/phone) so their Telegram links to calls and WhatsApp.</p>
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="WhatsApp Business" description="Meta Cloud API. Your own number, your own Meta billing.">
            {byType("whatsapp").map((c) => (
              <div key={c.id} className="flex items-center gap-2 rounded-lg border p-2.5 text-sm">
                <MessageCircle className="size-4 text-ch-whatsapp" />
                <span className="flex-1">{c.config.display_phone || c.config.phone_number_id}</span>
                <StatusBadge status={c.status} />
                <Dialog>
                  <DialogTrigger asChild><Button size="sm" variant="outline" className="h-7"><FileText className="size-3.5" /> Templates</Button></DialogTrigger>
                  <DialogContent className="sm:max-w-lg">
                    <DialogHeader><DialogTitle>WhatsApp message templates</DialogTitle></DialogHeader>
                    <WaTemplates channelId={c.id} />
                  </DialogContent>
                </Dialog>
              </div>
            ))}
            <TextField label="Phone number ID" value={wa.phone_number_id} onChange={(v) => setWa({ ...wa, phone_number_id: v })} />
            <TextField label="WhatsApp Business Account ID" value={wa.waba_id} onChange={(v) => setWa({ ...wa, waba_id: v })} hint="Needed for templates & broadcasts" />
            <TextField label="Permanent access token" type="password" value={wa.access_token} onChange={(v) => setWa({ ...wa, access_token: v })} />
            <Button disabled={!wa.phone_number_id || !wa.access_token || upsert.isPending} onClick={() => upsert.mutate({ type: "whatsapp", enabled: true, config: { phone_number_id: wa.phone_number_id, waba_id: wa.waba_id }, secret: { access_token: wa.access_token } })}>
              Connect WhatsApp
            </Button>
            <CopyBox label="Webhook URL for your Meta app" value={`${API_URL}/webhooks/whatsapp`} />
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="Phone number" description="Twilio, Exotel or Plivo (bring your own account).">
            {byType("phone").map((c) => (
              <div key={c.id} className="space-y-2 rounded-lg border p-2.5 text-sm">
                <div className="flex items-center gap-2">
                  <Phone className="size-4 text-ch-phone" />
                  <span className="flex-1">{c.config.phone_number} · {c.config.provider}</span>
                  <Badge variant="outline">{c.enabled ? "on" : "off"}</Badge>
                </div>
                <CopyBox label="Voice webhook (incoming calls)" value={`${API_URL.replace("http://127.0.0.1:8000", "https://<your-public-url>")}/telephony/${c.id}/incoming`} />
                <CopyBox label="SMS webhook (incoming texts)" value={`${API_URL.replace("http://127.0.0.1:8000", "https://<your-public-url>")}/telephony/${c.id}/sms`} />
                <div className="flex items-center justify-between rounded-md bg-muted/40 px-2.5 py-1.5 text-xs">
                  <span className="flex items-center gap-1.5"><MessageSquareText className="size-3.5" /> AI replies to SMS</span>
                  <Switch checked={c.config.sms_enabled !== false} onCheckedChange={(on) => upsert.mutate({ id: c.id, type: "phone", config: { sms_enabled: on } })} />
                </div>
              </div>
            ))}
            <Field label="Provider">
              <Select value={ph.provider} onValueChange={(v) => setPh({ ...ph, provider: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="twilio">Twilio</SelectItem>
                  <SelectItem value="exotel">Exotel (India)</SelectItem>
                  <SelectItem value="plivo">Plivo</SelectItem>
                  <SelectItem value="telnyx">Telnyx</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <TextField label="Phone number (E.164)" value={ph.phone_number} onChange={(v) => setPh({ ...ph, phone_number: v })} placeholder="+91…" />
            {ph.provider === "twilio" && (
              <>
                <TextField label="Account SID" value={ph.account_sid} onChange={(v) => setPh({ ...ph, account_sid: v })} />
                <TextField label="Auth token" type="password" value={ph.auth_token} onChange={(v) => setPh({ ...ph, auth_token: v })} />
              </>
            )}
            {ph.provider === "exotel" && (
              <>
                <TextField label="Account SID" value={ph.account_sid} onChange={(v) => setPh({ ...ph, account_sid: v })} />
                <TextField label="API key" value={ph.api_key} onChange={(v) => setPh({ ...ph, api_key: v })} />
                <TextField label="API token" type="password" value={ph.api_token} onChange={(v) => setPh({ ...ph, api_token: v })} />
              </>
            )}
            {ph.provider === "telnyx" && (
              <>
                <TextField label="API key" type="password" value={ph.api_key} onChange={(v) => setPh({ ...ph, api_key: v })} />
                <TextField label="Call Control connection ID" value={ph.connection_id} onChange={(v) => setPh({ ...ph, connection_id: v })} />
              </>
            )}
            {ph.provider === "plivo" && (
              <>
                <TextField label="Auth ID" value={ph.auth_id} onChange={(v) => setPh({ ...ph, auth_id: v })} />
                <TextField label="Auth token" type="password" value={ph.auth_token} onChange={(v) => setPh({ ...ph, auth_token: v })} />
              </>
            )}
            <Button
              disabled={!ph.phone_number || upsert.isPending}
              onClick={() =>
                upsert.mutate({
                  type: "phone",
                  enabled: true,
                  name: ph.phone_number,
                  config: { provider: ph.provider, phone_number: ph.phone_number, account_sid: ph.account_sid, auth_id: ph.auth_id, subdomain: ph.subdomain, connection_id: ph.connection_id, sms_enabled: true },
                  secret: { auth_token: ph.auth_token, api_key: ph.api_key, api_token: ph.api_token },
                })
              }
            >
              Connect number
            </Button>
            <p className="text-[11px] text-muted-foreground">Phone calls need a public URL (set PUBLIC_WEBHOOK_URL, e.g. an ngrok tunnel).</p>
          </Section>
        </Card>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <MetaPage kind="instagram" agentId={agent.id} chans={byType("instagram")} upsert={upsert} />
        <MetaPage kind="messenger" agentId={agent.id} chans={byType("messenger")} upsert={upsert} />
      </div>
      <Card className={cn("flex-row items-center gap-3 p-4 text-sm")}>
        <Mail className="size-4 text-ch-email" />
        <p className="flex-1 text-muted-foreground">Email uses your Resend settings (.env). SMS uses the phone number connected above: two-way, with STOP handled automatically.</p>
      </Card>
    </div>
  );
}
