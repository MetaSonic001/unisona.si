"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, CircleDot, FlaskConical, Loader2, MessagesSquare, PhoneCall, Rocket, Save, Smile, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";
import { ChannelsPanel } from "@/components/agent/channels";
import { FlowBuilder } from "@/components/agent/flow-builder";
import { TeamForm } from "@/components/agent/team-form";
import { AnalysisForm, HandoffForm, KnowledgeForm, PersonaForm, ToolsForm, VersionsPanel, VoiceForm } from "@/components/agent/config-forms";
import { Playground } from "@/components/agent/playground";
import { useAgent } from "@/components/agent/use-agent";
import { ChannelBadge, EmptyState, LoadingBlock, StatCard, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { pct, timeAgo } from "@/lib/format";
import { useState } from "react";

const TABS = [
  ["overview", "Overview"], ["playground", "Playground"], ["persona", "Persona"], ["voice", "Voice"], ["knowledge", "Knowledge"],
  ["flow", "Flow"], ["team", "Team & transfers"], ["tools", "Tools"], ["channels", "Channels"], ["handoff", "Handoff & safety"], ["analysis", "Analysis"], ["review", "Review"], ["versions", "Versions"],
] as const;

function Overview({ agent }: { agent: any }) {
  const api = useApi();
  const { data: s } = useQuery({ queryKey: ["agent-stats", agent.id], queryFn: () => api.get(`/agents/${agent.id}/stats`) });
  const { data: convs } = useQuery({ queryKey: ["conversations", "agent", agent.id], queryFn: () => api.get(`/conversations?agent_id=${agent.id}&limit=8`) });
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatCard label="Conversations (30d)" value={s?.conversations ?? "—"} icon={MessagesSquare} />
        <StatCard label="Resolved by AI" value={pct(s?.containment_rate)} icon={Check} />
        <StatCard label="Calls" value={s?.calls ?? "—"} hint={s ? `${s.call_minutes} min` : undefined} icon={PhoneCall} />
        <StatCard label="Voice latency" value={s?.voice_avg_latency_ms ? `${(s.voice_avg_latency_ms / 1000).toFixed(2)}s` : "—"} hint="user stops → agent speaks" />
        <StatCard label="CSAT" value={s?.csat ? `${s.csat}/5` : "—"} icon={Smile} hint={s ? `👍 ${s.thumbs_up} · 👎 ${s.thumbs_down}` : undefined} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card className="gap-0 p-0">
          <p className="border-b px-5 py-3 text-sm font-semibold">Latest conversations</p>
          {(convs?.items || []).length === 0 ? (
            <div className="p-5"><EmptyState icon={MessagesSquare} title="No conversations yet" description="Use the Playground or connect a channel." /></div>
          ) : (
            convs.items.map((c: any) => (
              <Link key={c.id} href={`/app/inbox?c=${c.id}`} className="flex items-center gap-3 border-b px-5 py-3 text-sm last:border-0 hover:bg-muted/40">
                <ChannelBadge channel={c.channel} />
                <span className="flex-1 truncate">{c.summary || c.last_message?.content}</span>
                <StatusBadge status={c.status} />
                <span className="w-24 text-right text-xs text-muted-foreground">{timeAgo(c.last_message_at)}</span>
              </Link>
            ))
          )}
        </Card>
        <Card className="gap-3 p-5">
          <p className="text-sm font-semibold">Deployed on</p>
          {agent.channels.map((c: any) => (
            <div key={c.id} className="flex items-center justify-between">
              <ChannelBadge channel={c.type === "phone" ? "phone" : c.type} />
              <span className={`text-xs ${c.enabled ? "text-success" : "text-muted-foreground"}`}>{c.enabled ? "on" : "off"}</span>
            </div>
          ))}
          <p className="pt-2 text-xs text-muted-foreground">Outcomes: {Object.entries(s?.outcomes || {}).map(([k, v]) => `${k.replaceAll("_", " ")} (${v})`).join(", ") || "none yet"}</p>
          <Button asChild variant="outline" size="sm" className="mt-2">
            <Link href={`/app/evals?agent=${agent.id}`}>
              <FlaskConical className="size-3.5" /> Run evaluations
            </Link>
          </Button>
        </Card>
      </div>
    </div>
  );
}

function ReviewQueue({ agentId }: { agentId: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["review", agentId], queryFn: () => api.get(`/agents/${agentId}/review`) });
  const [edits, setEdits] = useState<Record<string, string>>({});
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: string }) => api.post(`/agents/${agentId}/review/${id}`, { decision, answer: edits[id] }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["review", agentId] });
      toast.success(v.decision === "approve" ? "Approved: the agent will use this answer from now on" : "Dismissed");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const run = useMutation({ mutationFn: () => api.post(`/agents/${agentId}/review/run`), onSuccess: () => toast.success("Improve loop started", { description: "New suggestions appear here in a minute." }) });
  return (
    <div className="space-y-4">
      <Card className="flex-row items-center gap-4 p-4">
        <div className="flex-1">
          <p className="text-sm font-medium">Improve loop</p>
          <p className="text-xs text-muted-foreground">Thumbs-down answers, flagged replies and knowledge gaps become suggestions here every night at 2 AM. Approve them to teach the agent.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => run.mutate()} disabled={run.isPending}>Run now</Button>
      </Card>
      {(data?.items || []).length === 0 && <EmptyState icon={CircleDot} title="Nothing to review" description="When customers rate answers poorly or the agent can't answer, suggestions appear here." />}
      {(data?.items || []).map((r: any) => (
        <Card key={r.id} className="gap-3 p-4">
          <div className="flex items-center gap-2">
            <Badge variant="outline">{r.reason.replaceAll("_", " ")}</Badge>
            <span className="text-xs text-muted-foreground">{timeAgo(r.created_at)}</span>
          </div>
          <p className="text-sm font-medium">“{r.question}”</p>
          {r.bad_answer && <p className="rounded-md bg-destructive/5 p-2 text-xs text-muted-foreground"><span className="font-medium text-destructive">Agent said:</span> {r.bad_answer}</p>}
          <Textarea rows={3} placeholder="Write the ideal answer…" value={edits[r.id] ?? r.proposed_answer} onChange={(e) => setEdits({ ...edits, [r.id]: e.target.value })} />
          <div className="flex gap-2">
            <Button size="sm" onClick={() => decide.mutate({ id: r.id, decision: "approve" })}><Check className="size-3.5" /> Approve</Button>
            <Button size="sm" variant="ghost" onClick={() => decide.mutate({ id: r.id, decision: "reject" })}><X className="size-3.5" /> Dismiss</Button>
          </div>
        </Card>
      ))}
    </div>
  );
}

function AgentInner() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") || "overview";
  const a = useAgent(id);
  if (a.loading || !a.agent || !a.draft) return <LoadingBlock label="Loading agent…" />;
  const agent = a.agent;
  const setTab = (t: string) => router.replace(`/app/agents/${id}?tab=${t}`, { scroll: false });

  return (
    <div>
      <div className="flex flex-col gap-3 border-b px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3">
          <Button asChild size="icon" variant="ghost">
            <Link href="/app/agents" aria-label="Back"><ArrowLeft className="size-4" /></Link>
          </Button>
          <span className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-brand to-[oklch(0.7_0.15_220)] font-semibold text-white">{a.draft.persona?.name?.[0] || agent.name[0]}</span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-semibold">{a.name}</h1>
              <StatusBadge status={agent.status} />
              <Badge variant="outline" className="font-mono text-[10px]">v{agent.published_version}</Badge>
              {(a.dirty || agent.has_unpublished_changes) && <Badge className="bg-warning/15 text-warning">{a.dirty ? "unsaved changes" : "draft differs from live"}</Badge>}
            </div>
            <p className="text-xs text-muted-foreground">{a.draft.persona?.role} · updated {timeAgo(agent.updated_at)}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" disabled={!a.dirty || a.save.isPending} onClick={() => a.save.mutate()}>
            {a.save.isPending ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />} Save draft
          </Button>
          <Button className="bg-brand text-brand-foreground hover:bg-brand/90" disabled={a.publish.isPending} onClick={() => a.publish.mutate(undefined)}>
            {a.publish.isPending ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />} Publish
          </Button>
        </div>
      </div>
      <Tabs value={tab} onValueChange={setTab} className="gap-0">
        <div className="overflow-x-auto border-b px-6">
          <TabsList variant="line" className="h-11">
            {TABS.map(([v, l]) => (
              <TabsTrigger key={v} value={v}>{l}</TabsTrigger>
            ))}
          </TabsList>
        </div>
        <div className="p-6">
          <TabsContent value="overview"><Overview agent={agent} /></TabsContent>
          <TabsContent value="playground"><Playground agentId={id} greeting={a.draft.persona?.greeting?.replace("{{agent_name}}", a.draft.persona?.name || "").replace("{{business_name}}", a.draft.business?.name || "us")} dirty={a.dirty} /></TabsContent>
          <TabsContent value="persona"><PersonaForm cfg={a.draft} set={a.set} name={a.name} setName={a.setName} /></TabsContent>
          <TabsContent value="voice"><VoiceForm cfg={a.draft} set={a.set} /></TabsContent>
          <TabsContent value="knowledge"><KnowledgeForm cfg={a.draft} set={a.set} agentId={id} kbIds={a.kbIds} setKbIds={a.setKbIds} /></TabsContent>
          <TabsContent value="flow"><FlowBuilder cfg={a.draft} set={a.set} /></TabsContent>
          <TabsContent value="team"><TeamForm cfg={a.draft} set={a.set} agentId={id} /></TabsContent>
          <TabsContent value="tools"><ToolsForm cfg={a.draft} set={a.set} /></TabsContent>
          <TabsContent value="channels"><ChannelsPanel agent={agent} cfg={a.draft} set={a.set} /></TabsContent>
          <TabsContent value="handoff"><HandoffForm cfg={a.draft} set={a.set} /></TabsContent>
          <TabsContent value="analysis"><AnalysisForm cfg={a.draft} set={a.set} /></TabsContent>
          <TabsContent value="review"><ReviewQueue agentId={id} /></TabsContent>
          <TabsContent value="versions"><VersionsPanel agentId={id} onRestore={a.refresh} /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

export default function AgentPage() {
  return (
    <Suspense>
      <AgentInner />
    </Suspense>
  );
}
