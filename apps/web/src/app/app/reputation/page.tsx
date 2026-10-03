"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareHeart, Send, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AreaField, Field, TextField } from "@/components/agent/fields";
import { LoadingBlock, PageHeader, Section, StatCard, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api";
import { pct, timeAgo } from "@/lib/format";

export default function ReputationPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["reputation"], queryFn: () => api.get("/reputation") });
  const [q, setQ] = useState("");
  const { data: contacts } = useQuery({ queryKey: ["contacts", q], queryFn: () => api.get(`/crm/contacts?limit=50${q ? `&q=${encodeURIComponent(q)}` : ""}`) });
  const [s, setS] = useState<any>(null);
  const [picked, setPicked] = useState<string[]>([]);
  useEffect(() => { if (data && !s) setS(data.settings); }, [data, s]);
  const saveS = useMutation({ mutationFn: () => api.patch("/reputation/settings", s), onSuccess: () => toast.success("Saved") });
  const send = useMutation({
    mutationFn: () => api.post("/reputation/request", { contact_ids: picked, channel: s?.channel }),
    onSuccess: (r) => { const ok = r.results.filter((x: any) => x.sent).length; toast.success(`${ok} of ${r.results.length} requests sent`); setPicked([]); qc.invalidateQueries({ queryKey: ["reputation"] }); },
    onError: (e: Error) => toast.error(e.message),
  });
  if (isLoading || !s) return <LoadingBlock />;
  const st = data.stats;
  return (
    <div>
      <PageHeader icon={Star} title="Reputation" description="Ask happy customers for Google reviews automatically; catch unhappy ones privately before they post." />
      <div className="space-y-6 p-6">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StatCard label="Requests sent" value={st.sent} />
          <StatCard label="Response rate" value={pct(st.response_rate)} />
          <StatCard label="Average rating" value={st.avg_rating ? `${st.avg_rating} ★` : "—"} />
          <StatCard label="Sent to Google" value={st.sent_to_review_site} />
          <StatCard label="Private feedback" value={st.private_feedback} hint="recovered before going public" />
        </div>
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          <Card className="gap-0 p-0">
            <p className="border-b px-4 py-3 text-sm font-semibold">Requests</p>
            {(data.items || []).map((r: any) => (
              <div key={r.id} className="flex items-center gap-3 border-b px-4 py-2.5 text-sm last:border-0">
                <span className="flex-1 truncate">{r.contact?.name || r.contact?.phone || "Customer"}</span>
                <span className="text-xs text-muted-foreground">{r.channel}</span>
                {r.rating ? <span className="text-sm">{"★".repeat(r.rating)}<span className="text-muted-foreground/40">{"★".repeat(5 - r.rating)}</span></span> : <StatusBadge status={r.status} />}
                {r.feedback && <span className="max-w-[200px] truncate text-xs text-muted-foreground" title={r.feedback}>“{r.feedback}”</span>}
                <span className="w-20 text-right text-xs text-muted-foreground">{timeAgo(r.sent_at)}</span>
              </div>
            ))}
            {(data.items || []).length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">No requests yet. Send some below or add a “Ask for a review” step to an automation (e.g. after an appointment is completed).</p>}
          </Card>
          <div className="space-y-6">
            <Card className="gap-3 p-5">
              <Section title="Settings">
                <TextField label="Your Google review link" value={s.review_url} onChange={(v) => setS({ ...s, review_url: v })} placeholder="https://g.page/r/…/review" />
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Send to Google from"><Select value={String(s.threshold)} onValueChange={(v) => setS({ ...s, threshold: Number(v) })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{[3, 4, 5].map((n) => <SelectItem key={n} value={String(n)}>{n}★ and above</SelectItem>)}</SelectContent></Select></Field>
                  <Field label="Channel"><Select value={s.channel} onValueChange={(v) => setS({ ...s, channel: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["whatsapp", "sms", "email", "telegram"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></Field>
                </div>
                <AreaField label="Message" rows={3} value={s.message} onChange={(v) => setS({ ...s, message: v })} hint="Variables: {{first_name}}, {{business}}, {{link}}" />
                <Button size="sm" onClick={() => saveS.mutate()}>Save settings</Button>
              </Section>
            </Card>
            <Card className="gap-3 p-5">
              <Section title="Ask for reviews" description="Pick customers to ask now.">
                <Input placeholder="Search contacts…" value={q} onChange={(e) => setQ(e.target.value)} />
                <div className="max-h-56 space-y-1 overflow-y-auto">
                  {(contacts?.items || []).map((c: any) => (
                    <label key={c.id} className="flex items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted/50">
                      <Checkbox checked={picked.includes(c.id)} onCheckedChange={(v) => setPicked(v ? [...picked, c.id] : picked.filter((x) => x !== c.id))} />
                      <span className="flex-1 truncate">{c.name || c.phone || c.email}</span>
                    </label>
                  ))}
                </div>
                <Button size="sm" disabled={!picked.length || send.isPending} onClick={() => send.mutate()}><Send className="size-3.5" /> Send {picked.length || ""} request{picked.length === 1 ? "" : "s"}</Button>
                <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><MessageSquareHeart className="size-3.5" /> Customers get a 1-tap rating page. Max two requests per person per month.</p>
              </Section>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
