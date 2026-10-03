"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, ExternalLink, KeyRound, Link2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Field, TextField } from "@/components/agent/fields";
import { EmptyState, LoadingBlock, PageHeader, Section, StatCard, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function PaymentsPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["payments"], queryFn: () => api.get("/payments") });
  const [q, setQ] = useState("");
  const { data: contacts } = useQuery({ queryKey: ["contacts", q], queryFn: () => api.get(`/crm/contacts?limit=30${q ? `&q=${encodeURIComponent(q)}` : ""}`) });
  const [f, setF] = useState({ contact_id: "", amount: "", description: "", channel: "whatsapp", currency: "" });
  const create = useMutation({
    mutationFn: () => api.post("/payments/links", { ...f, amount: Number(f.amount), contact_id: f.contact_id || undefined, channel: f.contact_id ? f.channel : undefined, currency: f.currency || undefined }),
    onSuccess: (l) => { toast.success("Payment link created", { description: l.url }); qc.invalidateQueries({ queryKey: ["payments"] }); setF({ ...f, amount: "", description: "" }); },
    onError: (e: Error) => toast.error(e.message),
  });
  if (isLoading) return <LoadingBlock />;
  return (
    <div>
      <PageHeader icon={CreditCard} title="Payments" description="Collect payments on chat and calls with payment links from your own Razorpay (UPI, cards) or Stripe account. Agents can send them too." />
      <div className="space-y-6 p-6">
        {!data.provider && (
          <Card className="flex-row items-center gap-4 border-warning/40 bg-warning/5 p-4">
            <KeyRound className="size-5 text-warning" />
            <div className="flex-1 text-sm"><p className="font-medium">Connect Razorpay or Stripe</p><p className="text-muted-foreground">Add your key in Settings → AI providers (Razorpay key format: <code>key_id:key_secret</code>). Money goes straight to your account.</p></div>
            <Button size="sm" asChild><Link href="/app/settings?tab=providers">Add key</Link></Button>
          </Card>
        )}
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="Links created" value={data.totals.links} />
          <StatCard label="Paid" value={data.totals.paid_count} />
          <StatCard label="Collected" value={data.totals.paid_amount.toLocaleString()} hint={data.provider ? `via ${data.provider}` : undefined} />
        </div>
        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <Card className="gap-0 p-0">
            <p className="border-b px-4 py-3 text-sm font-semibold">Payment links</p>
            {(data.items || []).length === 0 ? <div className="p-6"><EmptyState icon={Link2} title="No payment links yet" description="Create one here, enable 'Collect payments' on an agent, or add a payment step to an automation." /></div> :
              data.items.map((p: any) => (
                <div key={p.id} className="flex items-center gap-3 border-b px-4 py-2.5 text-sm last:border-0">
                  <span className="w-28 font-medium">{p.currency} {Number(p.amount).toLocaleString()}</span>
                  <span className="flex-1 truncate">{p.description}</span>
                  <span className="text-xs text-muted-foreground">{p.contact?.name}</span>
                  <StatusBadge status={p.status} />
                  {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground"><ExternalLink className="size-3.5" /></a>}
                  <span className="w-20 text-right text-xs text-muted-foreground">{timeAgo(p.created_at)}</span>
                </div>
              ))}
          </Card>
          <div className="space-y-6">
            <Card className="gap-3 p-5">
              <Section title="New payment link">
                <div className="grid grid-cols-[1fr_90px] gap-2">
                  <TextField label="Amount" type="number" value={f.amount} onChange={(v) => setF({ ...f, amount: v })} />
                  <TextField label="Currency" value={f.currency} onChange={(v) => setF({ ...f, currency: v.toUpperCase() })} placeholder="INR" />
                </div>
                <TextField label="For" value={f.description} onChange={(v) => setF({ ...f, description: v })} placeholder="e.g. Root canal (advance)" />
                <Field label="Send to (optional)">
                  <Input placeholder="Search contact…" value={q} onChange={(e) => setQ(e.target.value)} />
                  <Select value={f.contact_id} onValueChange={(v) => setF({ ...f, contact_id: v })}><SelectTrigger><SelectValue placeholder="Just create the link" /></SelectTrigger><SelectContent>{(contacts?.items || []).map((c: any) => <SelectItem key={c.id} value={c.id}>{c.name || c.phone || c.email}</SelectItem>)}</SelectContent></Select>
                </Field>
                {f.contact_id && <Field label="Via"><Select value={f.channel} onValueChange={(v) => setF({ ...f, channel: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["whatsapp", "sms", "email", "telegram"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></Field>}
                <Button disabled={!f.amount || !f.description || create.isPending} onClick={() => create.mutate()}>Create link</Button>
              </Section>
            </Card>
            <Card className="gap-2 p-5 text-xs">
              <p className="text-sm font-semibold">Webhooks (mark links paid automatically)</p>
              <p className="text-muted-foreground">Razorpay: event <code>payment_link.paid</code>. Stripe: <code>checkout.session.completed</code>. Add the signing secret as <code>webhook_secret</code> on the provider key.</p>
              {Object.entries(data.webhook_urls).map(([p, u]: any) => <div key={p}><p className="font-medium capitalize">{p}</p><code className="break-all text-[11px] text-muted-foreground">{u}</code></div>)}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
