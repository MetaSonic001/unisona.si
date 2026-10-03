"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FlaskConical, Loader2, Mic, Plus, ShieldAlert, Users, XCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { EmptyState, PageHeader, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const METRICS = ["correctness", "faithfulness", "answer_relevancy", "context_precision", "context_recall"];

function Score({ v, label }: { v?: number; label: string }) {
  if (v === undefined || v === null) return null;
  const pct = Math.round(v * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[11px]"><span className="text-muted-foreground">{label.replaceAll("_", " ")}</span><span className="font-mono">{pct}%</span></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", pct >= 80 ? "bg-success" : pct >= 60 ? "bg-warning" : "bg-destructive")} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

function EvalsInner() {
  const api = useApi();
  const qc = useQueryClient();
  const params = useSearchParams();
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const [agentId, setAgentId] = useState(params.get("agent") || "");
  useEffect(() => { if (!agentId && agents?.items?.[0]) setAgentId(agents.items[0].id); }, [agents, agentId]);
  const { data: suites } = useQuery({ queryKey: ["suites", agentId], queryFn: () => api.get(`/eval-suites?agent_id=${agentId}`), enabled: !!agentId });
  const { data: runs } = useQuery({ queryKey: ["eval-runs", agentId], queryFn: () => api.get(`/evals/runs?agent_id=${agentId}`), enabled: !!agentId, refetchInterval: (q) => ((q.state.data as any)?.items?.some((r: any) => ["queued", "running"].includes(r.status)) ? 3000 : 20000) });
  const [viewing, setViewing] = useState<string | null>(null);
  const [cases, setCases] = useState("");
  const run = useMutation({ mutationFn: (b: any) => api.post("/evals/run", { agent_id: agentId, ...b }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["eval-runs"] }); toast.success("Evaluation started"); }, onError: (e: Error) => toast.error(e.message) });
  const createSuite = useMutation({
    mutationFn: () => {
      const parsed = cases.split(/\n\s*\n/).map((b) => ({ input: (b.match(/Q:\s*(.+)/i) || [])[1], expected: ((b.match(/A:\s*([\s\S]+)/i) || [])[1] || "").trim() })).filter((c) => c.input);
      return api.post("/eval-suites", { agent_id: agentId, name: `Suite ${new Date().toLocaleDateString()}`, kind: "qa", cases: parsed });
    },
    onSuccess: () => { setCases(""); qc.invalidateQueries({ queryKey: ["suites"] }); toast.success("Test suite saved"); },
  });

  return (
    <div>
      <PageHeader icon={FlaskConical} title="Evaluations" description="Measure accuracy before customers do: answer quality, grounding, safety and full simulated conversations."
        actions={<Select value={agentId} onValueChange={setAgentId}><SelectTrigger className="w-64"><SelectValue placeholder="Choose agent" /></SelectTrigger><SelectContent>{(agents?.items || []).map((a: any) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent></Select>} />
      <div className="grid gap-6 p-6 xl:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
            <Card className="gap-2 p-4">
              <p className="flex items-center gap-2 font-medium"><CheckCircle2 className="size-4 text-brand" /> Answer quality</p>
              <p className="text-xs text-muted-foreground">Correctness, faithfulness, relevancy and context precision/recall (Ragas-style, LLM-judged).</p>
              {(suites?.items || []).map((s: any) => <Button key={s.id} size="sm" variant="outline" onClick={() => run.mutate({ kind: "qa", suite_id: s.id })}>Run “{s.name}” ({s.cases.length})</Button>)}
              {(suites?.items || []).length === 0 && <p className="text-xs text-warning">Add a test suite below first.</p>}
            </Card>
            <Card className="gap-2 p-4">
              <p className="flex items-center gap-2 font-medium"><ShieldAlert className="size-4 text-destructive" /> Red-team</p>
              <p className="text-xs text-muted-foreground">12 attacks: prompt extraction, role override, data exfiltration, policy injection, in English, Hindi and Hinglish.</p>
              <Button size="sm" variant="outline" onClick={() => run.mutate({ kind: "redteam" })}>Run security suite</Button>
            </Card>
            <Card className="gap-2 p-4">
              <p className="flex items-center gap-2 font-medium"><Users className="size-4 text-ch-web" /> Simulations</p>
              <p className="text-xs text-muted-foreground">AI customers (happy, frustrated, Hinglish) talk to your agent; a judge scores goal completion, tone and hallucinations.</p>
              <Button size="sm" variant="outline" onClick={() => run.mutate({ kind: "simulation" })}>Run simulations</Button>
            </Card>
            <Card className="gap-2 p-4">
              <p className="flex items-center gap-2 font-medium"><Mic className="size-4 text-ch-voice" /> Voice simulations</p>
              <p className="text-xs text-muted-foreground">Real calls with synthetic callers: Indian/US/UK accents, Hindi, street noise and barge-in. Scores word-error-rate, latency and handling. Agent must be published.</p>
              <Button size="sm" variant="outline" onClick={() => run.mutate({ kind: "voice" })}>Run voice tests</Button>
            </Card>
          </div>
          <Card className="gap-0 p-0">
            <p className="border-b px-4 py-3 text-sm font-semibold">Runs</p>
            {(runs?.items || []).length === 0 && <div className="p-4"><EmptyState icon={FlaskConical} title="No runs yet" /></div>}
            {(runs?.items || []).map((r: any) => (
              <button key={r.id} onClick={() => setViewing(r.id)} className="flex w-full items-center gap-4 border-b px-4 py-3 text-left last:border-0 hover:bg-muted/30">
                <Badge variant="outline" className="w-24 justify-center capitalize">{r.kind}</Badge>
                <StatusBadge status={r.status} />
                {["queued", "running"].includes(r.status) && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
                <div className="flex flex-1 flex-wrap gap-x-4 gap-y-1 text-xs">
                  {r.scores?.pass_rate !== undefined && <span>pass <b>{Math.round(r.scores.pass_rate * 100)}%</b></span>}
                  {r.scores?.faithfulness !== undefined && <span>faithful <b>{Math.round(r.scores.faithfulness * 100)}%</b></span>}
                  {r.scores?.correctness !== undefined && <span>correct <b>{Math.round(r.scores.correctness * 100)}%</b></span>}
                  {r.scores?.goal_completed !== undefined && <span>goal <b>{Math.round(r.scores.goal_completed * 100)}%</b></span>}
                  {r.scores?.leaks !== undefined && <span>leaks <b>{r.scores.leaks}</b></span>}
                  {r.scores?.avg_latency_ms && <span>latency <b>{(r.scores.avg_latency_ms / 1000).toFixed(1)}s</b></span>}
                  {r.scores?.avg_word_error_rate !== undefined && r.scores?.avg_word_error_rate !== null && <span>WER <b>{Math.round(r.scores.avg_word_error_rate * 100)}%</b></span>}
                  {r.scores?.error && <span className="text-destructive">{r.scores.error}</span>}
                </div>
                <span className="text-xs text-muted-foreground">{timeAgo(r.created_at)}</span>
              </button>
            ))}
          </Card>
        </div>
        <Card className="h-fit gap-3 p-4">
          <p className="flex items-center gap-2 text-sm font-semibold"><Plus className="size-4" /> New test suite</p>
          <p className="text-xs text-muted-foreground">Blocks separated by a blank line. Q: the customer message; A: the expected answer (facts that must be right).</p>
          <Textarea rows={10} value={cases} onChange={(e) => setCases(e.target.value)} placeholder={"Q: What are your Saturday hours?\nA: 9 AM to 2 PM\n\nQ: Do you offer EMI?\nA: Yes, no-cost EMI above ₹20,000"} />
          <Button size="sm" disabled={!cases || !agentId} onClick={() => createSuite.mutate()}>Save suite</Button>
        </Card>
      </div>
      <Sheet open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          <SheetHeader><SheetTitle>Evaluation results</SheetTitle></SheetHeader>
          {viewing && <RunDetail id={viewing} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function RunDetail({ id }: { id: string }) {
  const api = useApi();
  const { data: r } = useQuery({ queryKey: ["eval-run", id], queryFn: () => api.get(`/evals/runs/${id}`), refetchInterval: 4000 });
  if (!r) return null;
  return (
    <div className="space-y-4 px-4 pb-8">
      <Card className="gap-2 p-4">
        {METRICS.map((m) => <Score key={m} label={m} v={r.scores?.[m]} />)}
        {["goal_completed", "helpfulness", "tone", "hallucination_free", "pass_rate", "guard_block_rate"].map((m) => <Score key={m} label={m} v={r.scores?.[m]} />)}
      </Card>
      {(r.results || []).map((x: any, i: number) => (
        <Card key={i} className="gap-2 p-3 text-sm">
          <div className="flex items-start gap-2">
            {x.passed === false ? <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" /> : x.passed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : null}
            <p className="font-medium">{x.input || x.scenario}{x.attack && <Badge variant="outline" className="ml-2 text-[10px]">{x.attack}</Badge>}</p>
          </div>
          {x.expected && <p className="text-xs text-muted-foreground"><b>Expected:</b> {x.expected}</p>}
          {x.answer && <p className="text-xs"><b>Agent:</b> {x.answer}</p>}
          {x.word_error_rate !== undefined && (
            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="rounded bg-muted px-1.5 py-0.5">accent {x.accent}</span>
              <span className="rounded bg-muted px-1.5 py-0.5">noise {x.noise}</span>
              {x.barge_in && <span className="rounded bg-muted px-1.5 py-0.5">barge-in</span>}
              <span className="rounded bg-muted px-1.5 py-0.5">WER {Math.round(x.word_error_rate * 100)}%</span>
              {x.avg_latency_ms && <span className="rounded bg-muted px-1.5 py-0.5">latency {x.avg_latency_ms}ms (p95 {x.p95_latency_ms}ms)</span>}
            </div>
          )}
          {x.error && <p className="text-xs text-destructive">{x.error}</p>}
          {x.transcript && <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded bg-muted/40 p-2 text-[11px]">{Array.isArray(x.transcript) ? x.transcript.join("\n") : x.transcript}</pre>}
          {x.scores && <div className="flex flex-wrap gap-2 text-[11px]">{Object.entries(x.scores).filter(([, v]) => typeof v === "number").map(([k, v]: any) => <span key={k} className="rounded bg-muted px-1.5 py-0.5">{k.replaceAll("_", " ")} {Math.round(v * 100)}%</span>)}</div>}
          {(x.reason || x.scores?.reason || x.summary) && <p className="text-[11px] italic text-muted-foreground">{x.reason || x.scores?.reason || x.summary}</p>}
          {x.leaks?.length > 0 && <p className="text-[11px] text-destructive">Leaked: {x.leaks.join(", ")}</p>}
        </Card>
      ))}
    </div>
  );
}

export default function EvalsPage() {
  return <Suspense><EvalsInner /></Suspense>;
}
