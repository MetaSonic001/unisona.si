"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, PhoneForwarded, Plus, Trash2, Users } from "lucide-react";
import { Field } from "@/components/agent/fields";
import { Section } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api";

export function TeamForm({ cfg, set, agentId }: { cfg: any; set: (path: string, v: any) => void; agentId: string }) {
  const api = useApi();
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const { data: integ } = useQuery({ queryKey: ["integrations"], queryFn: () => api.get("/integrations") });
  const members: any[] = cfg.squad?.members || [];
  const targets: any[] = cfg.handoff?.transfer_targets || [];
  const others = (agents?.items || []).filter((a: any) => a.id !== agentId);
  const calcom = (integ?.catalog || []).find((c: any) => c.id === "calcom");

  const setMembers = (m: any[]) => set("squad", { ...(cfg.squad || {}), members: m });
  const setTargets = (t: any[]) => set("handoff", { ...cfg.handoff, transfer_targets: t });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="gap-4 p-5">
        <Section title="AI specialist team" description="Hand the conversation to another agent mid-chat or mid-call (e.g. receptionist → billing → technical). Memory, contact and history carry over; on calls the voice changes too.">
          {members.length === 0 && <p className="flex items-center gap-2 rounded-lg border border-dashed p-3 text-xs text-muted-foreground"><Users className="size-4" /> No specialists yet. Create other agents, then add them here.</p>}
          {members.map((m, i) => (
            <div key={i} className="space-y-2 rounded-lg border p-3">
              <div className="flex gap-2">
                <Select value={m.agent_id} onValueChange={(v) => setMembers(members.map((x, j) => (j === i ? { ...x, agent_id: v } : x)))}>
                  <SelectTrigger className="flex-1"><Bot className="size-3.5" /><SelectValue placeholder="Choose agent" /></SelectTrigger>
                  <SelectContent>{others.map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent>
                </Select>
                <Input className="w-36" placeholder="role, e.g. billing" value={m.name} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, name: e.target.value.toLowerCase().replace(/\s+/g, "_") } : x)))} />
                <Button size="icon" variant="ghost" onClick={() => setMembers(members.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
              </div>
              <Input placeholder="Hand over when… (e.g. questions about invoices or refunds)" value={m.when || ""} onChange={(e) => setMembers(members.map((x, j) => (j === i ? { ...x, when: e.target.value } : x)))} />
            </div>
          ))}
          <Button variant="outline" size="sm" className="w-fit" disabled={!others.length} onClick={() => setMembers([...members, { agent_id: others[0]?.id, name: "", when: "" }])}><Plus className="size-3.5" /> Add specialist</Button>
        </Section>
      </Card>
      <div className="space-y-6">
        <Card className="gap-4 p-5">
          <Section title="Live call transfer" description="Phone numbers the agent can transfer callers to. Warm transfer: the human first hears an AI summary of the call, then is connected. Browser calls open a takeover in Live instead.">
            {targets.map((t, i) => (
              <div key={i} className="space-y-2 rounded-lg border p-3">
                <div className="flex gap-2">
                  <Input className="w-32" placeholder="name" value={t.name} onChange={(e) => setTargets(targets.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                  <Input className="flex-1" placeholder="+91 98xxxxxxx" value={t.number} onChange={(e) => setTargets(targets.map((x, j) => (j === i ? { ...x, number: e.target.value } : x)))} />
                  <Select value={t.mode || "warm"} onValueChange={(v) => setTargets(targets.map((x, j) => (j === i ? { ...x, mode: v } : x)))}>
                    <SelectTrigger className="w-24"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="warm">Warm</SelectItem><SelectItem value="cold">Cold</SelectItem></SelectContent>
                  </Select>
                  <Button size="icon" variant="ghost" onClick={() => setTargets(targets.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
                </div>
                <Input placeholder="Who is this? (e.g. senior dentist for emergencies)" value={t.description || ""} onChange={(e) => setTargets(targets.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} />
              </div>
            ))}
            <Button variant="outline" size="sm" className="w-fit" onClick={() => setTargets([...targets, { name: "Front desk", number: "", mode: "warm", description: "" }])}><PhoneForwarded className="size-3.5" /> Add transfer number</Button>
          </Section>
        </Card>
        <Card className="gap-4 p-5">
          <Section title="Booking calendar" description="Where the agent checks availability and books.">
            <Field label="Calendar source">
              <Select value={cfg.calendar_source || "local"} onValueChange={(v) => set("calendar_source", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="local">Unisona calendar (+ Google Calendar busy times if connected)</SelectItem>
                  <SelectItem value="calcom" disabled={!calcom?.connected}>Cal.com {calcom?.connected ? "" : "(connect in Integrations)"}</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </Section>
        </Card>
      </div>
    </div>
  );
}
