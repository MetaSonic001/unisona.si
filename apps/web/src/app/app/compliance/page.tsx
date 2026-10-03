"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneOff, ShieldCheck, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { SwitchRow, TextField } from "@/components/agent/fields";
import { LoadingBlock, PageHeader, Section, StatCard } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function CompliancePage() {
  const api = useApi();
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const { data, isLoading } = useQuery({ queryKey: ["compliance"], queryFn: () => api.get("/compliance") });
  const { data: cap } = useQuery({ queryKey: ["capacity"], queryFn: () => api.get("/calls/capacity"), refetchInterval: 10000 });
  const [s, setS] = useState<any>(null);
  const [num, setNum] = useState("");
  const [limit, setLimit] = useState("");
  useEffect(() => { if (data && !s) setS(data.settings); }, [data, s]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["compliance"] });
  const save = useMutation({ mutationFn: () => api.patch("/compliance", { ...s, ...(limit ? { max_concurrent_calls: Number(limit) } : {}) }), onSuccess: () => { toast.success("Saved"); qc.invalidateQueries({ queryKey: ["capacity"] }); } });
  const add = useMutation({ mutationFn: () => api.post("/compliance/dnd", { values: num.split(/[\n,]/).map((x) => x.trim()).filter(Boolean) }), onSuccess: (r) => { toast.success(`${r.added} added`); setNum(""); refresh(); } });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/compliance/dnd/${id}`), onSuccess: refresh });
  const upload = useMutation({
    mutationFn: (f: File) => { const fd = new FormData(); fd.append("file", f); return api.upload("/compliance/dnd/import", fd); },
    onSuccess: (r) => { toast.success(`${r.added} numbers imported`); refresh(); },
    onError: (e: Error) => toast.error(e.message),
  });
  if (isLoading || !s) return <LoadingBlock />;
  return (
    <div>
      <PageHeader icon={ShieldCheck} title="Compliance" description="Opt-outs, do-not-contact lists, consent and calling hours, enforced on every AI call, campaign and message (TRAI/TCCCPR-friendly)." />
      <div className="grid gap-6 p-6 lg:grid-cols-2">
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Do-not-contact" value={data.dnd_count} />
            <StatCard label="Live calls" value={cap ? `${cap.active}/${cap.limit}` : "—"} hint={`${cap?.plan || ""} plan lines`} />
            <StatCard label="Calling hours" value={`${s.calling_start}–${s.calling_end}`} />
          </div>
          <Card className="gap-3 p-5">
            <Section title="Rules">
              <SwitchRow label="Honour opt-outs automatically" hint={'"Stop", "don\'t call me", "call mat karo", "message band karo"… on any channel adds them to the do-not-contact list and ends politely.'} checked={s.auto_opt_out} onChange={(v) => setS({ ...s, auto_opt_out: v })} />
              <SwitchRow label="Require consent for promotional outreach" hint="Promotional campaigns only reach contacts with recorded marketing consent (forms, chats). Transactional messages are unaffected." checked={s.require_consent_for_promotional} onChange={(v) => setS({ ...s, require_consent_for_promotional: v })} />
              <div className="grid grid-cols-3 gap-3">
                <TextField label="Calls allowed from" type="time" value={s.calling_start} onChange={(v) => setS({ ...s, calling_start: v })} />
                <TextField label="Until" type="time" value={s.calling_end} onChange={(v) => setS({ ...s, calling_end: v })} />
                <TextField label="Max simultaneous calls" type="number" value={limit} onChange={setLimit} placeholder={String(cap?.limit ?? "")} />
              </div>
              <Button size="sm" className="w-fit" onClick={() => save.mutate()}>Save rules</Button>
            </Section>
          </Card>
        </div>
        <Card className="gap-3 p-5">
          <Section title="Do-not-contact list" description="Numbers and emails here are never called or messaged by AI, campaigns or automations.">
            <div className="flex gap-2">
              <Input placeholder="+91 98xxx xxxxx, email@…" value={num} onChange={(e) => setNum(e.target.value)} />
              <Button disabled={!num} onClick={() => add.mutate()}>Add</Button>
              <Button variant="outline" onClick={() => file.current?.click()}><Upload className="size-3.5" /> CSV</Button>
              <input ref={file} type="file" accept=".csv,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
            </div>
            <div className="max-h-[460px] overflow-y-auto rounded-lg border">
              {(data.dnd || []).map((d: any) => (
                <div key={d.id} className="flex items-center gap-2 border-b px-3 py-2 text-sm last:border-0">
                  <PhoneOff className="size-3.5 text-muted-foreground" />
                  <span className="flex-1 font-mono text-xs">{d.value}</span>
                  <span className="max-w-[160px] truncate text-xs text-muted-foreground">{d.reason}</span>
                  <span className="w-20 text-right text-xs text-muted-foreground">{timeAgo(d.created_at)}</span>
                  <Button size="icon" variant="ghost" className="size-7" onClick={() => del.mutate(d.id)}><Trash2 className="size-3.5" /></Button>
                </div>
              ))}
              {(data.dnd || []).length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">Empty. Opt-outs appear here automatically.</p>}
            </div>
          </Section>
        </Card>
      </div>
    </div>
  );
}
