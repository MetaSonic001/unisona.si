"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus, Search, Upload, Users } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Field } from "@/components/agent/fields";
import { ChannelDot, EmptyState, LoadingBlock, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";
import { initials, timeAgo } from "@/lib/format";

const ID_CHANNEL: Record<string, string> = { wa_id: "whatsapp", telegram_id: "telegram", phone: "phone", email: "email", web_session: "web" };
const STAGES = ["", "lead", "qualified", "customer", "churned"];

export default function ContactsPage() {
  const api = useApi();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [stage, setStage] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", phone: "", email: "" });
  const fileRef = useRef<HTMLInputElement>(null);
  const { data, isLoading } = useQuery({ queryKey: ["contacts", q, stage], queryFn: () => api.get(`/crm/contacts?limit=300${q ? `&q=${encodeURIComponent(q)}` : ""}${stage ? `&lifecycle=${stage}` : ""}`) });
  const create = useMutation({ mutationFn: () => api.post("/crm/contacts", form), onSuccess: () => { setOpen(false); setForm({ name: "", phone: "", email: "" }); qc.invalidateQueries({ queryKey: ["contacts"] }); toast.success("Contact added"); } });
  const importCsv = async (f?: File) => {
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api.upload("/crm/contacts/import", fd);
      toast.success(`Imported: ${r.created} new, ${r.updated} updated`);
      qc.invalidateQueries({ queryKey: ["contacts"] });
    } catch (e: any) { toast.error(e.message); }
  };
  const exportCsv = async () => {
    const blob = await api.get<Blob>("/crm/contacts-export");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "contacts.csv";
    a.click();
  };

  return (
    <div>
      <PageHeader icon={Users} title="Contacts" description="One record per person across every channel. The AI keeps these up to date."
        actions={<>
          <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}><Upload className="size-3.5" /> Import CSV</Button>
          <Button variant="outline" size="sm" onClick={exportCsv}><Download className="size-3.5" /> Export</Button>
          <Button size="sm" onClick={() => setOpen(true)}><Plus className="size-3.5" /> Add contact</Button>
          <input ref={fileRef} hidden type="file" accept=".csv" onChange={(e) => importCsv(e.target.files?.[0])} />
        </>} />
      <div className="space-y-4 p-6">
        <div className="flex flex-wrap gap-2">
          <div className="relative w-72"><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input className="pl-8" placeholder="Search name, phone, email" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          {STAGES.map((s) => <Button key={s} size="sm" variant={stage === s ? "default" : "ghost"} onClick={() => setStage(s)} className="capitalize">{s || "All"}</Button>)}
          <span className="ml-auto self-center text-sm text-muted-foreground">{data?.total ?? 0} contacts</span>
        </div>
        {isLoading ? <LoadingBlock /> : (data?.items || []).length === 0 ? (
          <EmptyState icon={Users} title="No contacts yet" description="Contacts are created automatically when people talk to your agents on any channel, or import a CSV." />
        ) : (
          <Card className="gap-0 overflow-x-auto p-0">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="border-b bg-muted/30 text-left text-xs text-muted-foreground">
                <tr><th className="px-4 py-2 font-medium">Name</th><th className="font-medium">Channels</th><th className="font-medium">Stage</th><th className="font-medium">Score</th><th className="font-medium">Tags</th><th className="font-medium">Summary</th><th className="pr-4 text-right font-medium">Last seen</th></tr>
              </thead>
              <tbody>
                {data.items.map((c: any) => (
                  <tr key={c.id} className="border-b last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5">
                      <Link href={`/app/crm/contacts/${c.id}`} className="flex items-center gap-2.5">
                        <span className="grid size-8 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-brand">{initials(c.name || c.phone)}</span>
                        <span><span className="block font-medium hover:underline">{c.name || "Unknown"}</span><span className="block text-xs text-muted-foreground">{c.phone || c.email}</span></span>
                      </Link>
                    </td>
                    <td><div className="flex -space-x-1">{c.identity_types.map((t: string) => ID_CHANNEL[t] && <ChannelDot key={t} channel={ID_CHANNEL[t]} />)}</div></td>
                    <td><Badge variant="outline" className="capitalize">{c.lifecycle}</Badge></td>
                    <td><span className="tabular-nums">{c.score}</span></td>
                    <td><div className="flex flex-wrap gap-1">{c.tags.slice(0, 3).map((t: string) => <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>)}</div></td>
                    <td className="max-w-[260px]"><p className="truncate text-xs text-muted-foreground">{c.summary}</p></td>
                    <td className="pr-4 text-right text-xs text-muted-foreground">{timeAgo(c.last_seen_at || c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add contact</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Phone"><Input value={form.phone} placeholder="+91…" onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
            <Field label="Email"><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Button onClick={() => create.mutate()} disabled={create.isPending || !(form.name || form.phone || form.email)}>Save</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
