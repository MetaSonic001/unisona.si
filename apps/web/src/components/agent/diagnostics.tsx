"use client";

import { useQuery } from "@tanstack/react-query";
import { Brain, ChevronRight, Clock, Coins, Database, FileSearch, ShieldCheck, Wrench } from "lucide-react";
import { useState } from "react";
import { LoadingBlock } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { useApi } from "@/lib/api";
import { cn } from "@/lib/utils";

function Num({ v, digits = 3 }: { v?: number | null; digits?: number }) {
  return <span className="font-mono tabular-nums">{v === null || v === undefined ? "—" : Number(v).toFixed(digits)}</span>;
}

function Block({ icon: Icon, title, children, right }: { icon: any; title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/30 px-3 py-2">
        <p className="flex items-center gap-2 text-xs font-semibold">
          <Icon className="size-3.5 text-brand" /> {title}
        </p>
        {right}
      </div>
      <div className="p-3 text-xs">{children}</div>
    </div>
  );
}

export function TraceView({ trace }: { trace: any }) {
  const [openSection, setOpenSection] = useState<string | null>(null);
  if (!trace) return null;
  const r = trace.retrieval;
  const timings = trace.timings_ms || {};
  const total = Object.values(timings).reduce((a: number, b: any) => a + (Number(b) || 0), 0) || 1;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="secondary">route: {trace.router}</Badge>
        {trace.language && <Badge variant="secondary">lang: {trace.language}</Badge>}
        {trace.confidence !== null && trace.confidence !== undefined && (
          <Badge variant="secondary" className={trace.confident ? "bg-success/15 text-success" : "bg-warning/15 text-warning"}>
            confidence {Number(trace.confidence).toFixed(2)}
          </Badge>
        )}
        {trace.handoff_trigger && <Badge className="bg-warning/20 text-warning">handoff: {trace.handoff_trigger}</Badge>}
        {trace.blocked && <Badge className="bg-destructive/15 text-destructive">blocked</Badge>}
      </div>

      {Object.keys(timings).length > 0 && (
        <Block icon={Clock} title="Latency by stage" right={<span className="font-mono text-[11px] text-muted-foreground">{total} ms</span>}>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
            {Object.entries(timings).map(([k, v]: any, i) => (
              <div key={k} title={`${k}: ${v}ms`} className={cn("h-full", ["bg-brand", "bg-ch-web", "bg-ch-whatsapp", "bg-ch-phone", "bg-ch-telegram"][i % 5])} style={{ width: `${(v / total) * 100}%` }} />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
            {Object.entries(timings).map(([k, v]: any) => (
              <span key={k}>
                {k} <span className="font-mono text-foreground">{v}ms</span>
              </span>
            ))}
          </div>
        </Block>
      )}

      {trace.guard && (
        <Block icon={ShieldCheck} title="Prompt-injection guard" right={<span className="text-[11px] text-muted-foreground">{trace.guard.model_used ? "Prompt Guard 2 + heuristics" : "heuristics"}</span>}>
          score <Num v={trace.guard.score} /> {trace.guard.reasons?.length > 0 && <span className="text-destructive">· {trace.guard.reasons.join(", ")}</span>}
        </Block>
      )}

      {trace.memory && Object.keys(trace.memory).length > 0 && (
        <Block icon={Brain} title="Cross-channel memory" right={<span className="text-[11px] text-muted-foreground">{trace.memory.facts} facts · {trace.memory.previous_conversations} past conversations</span>}>
          <pre className="whitespace-pre-wrap font-sans text-[11px] text-muted-foreground">{trace.memory_brief || "No memory for this customer yet."}</pre>
        </Block>
      )}

      {r && (
        <Block icon={FileSearch} title={`Retrieval (${r.mode})`} right={<span className="font-mono text-[11px] text-muted-foreground">{r.timings_ms?.total}ms</span>}>
          <p className="mb-2 text-muted-foreground">
            Query: <span className="text-foreground">{r.query}</span>
          </p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px]">
              <thead className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="py-1 pr-2">Chunk</th>
                  <th className="px-1">dense</th>
                  <th className="px-1">bm25</th>
                  <th className="px-1">rrf</th>
                  <th className="px-1">rerank</th>
                  <th className="px-1">policy</th>
                  <th className="px-1">score</th>
                </tr>
              </thead>
              <tbody>
                {(r.candidates || []).slice(0, 10).map((c: any) => {
                  const used = r.chunks.some((u: any) => u.id === c.id);
                  return (
                    <tr key={c.id} className={cn("border-t align-top", !used && "opacity-50")} title={c.text}>
                      <td className="max-w-[220px] py-1.5 pr-2">
                        <p className="truncate font-medium">{c.title}</p>
                        <p className="line-clamp-2 text-[11px] text-muted-foreground">{c.text.replace(/^\[.*?\]\n/, "")}</p>
                      </td>
                      <td className="px-1"><Num v={c.dense} /></td>
                      <td className="px-1"><Num v={c.bm25} digits={2} /></td>
                      <td className="px-1"><Num v={c.rrf} digits={4} /></td>
                      <td className="px-1"><Num v={c.rerank} /></td>
                      <td className={cn("px-1 font-mono", c.policy < 1 && "text-destructive", c.policy > 1 && "text-success")}>×{c.policy}</td>
                      <td className="px-1"><Num v={c.score} digits={4} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">Faded rows were retrieved but not used. Hover a row for the full text.</p>
        </Block>
      )}

      {trace.golden?.length > 0 && (
        <Block icon={Database} title="Approved answers matched">
          {trace.golden.map((g: any) => (
            <p key={g.id} className="mb-1">
              <Num v={g.similarity} digits={2} /> · {g.question}
            </p>
          ))}
        </Block>
      )}

      {(trace.tools?.length > 0 || trace.sql?.length > 0) && (
        <Block icon={Wrench} title="Tools used">
          {trace.tools.map((t: any, i: number) => (
            <div key={i} className="mb-2 rounded-md bg-muted/40 p-2">
              <p className="font-mono font-medium">
                {t.tool}({JSON.stringify(t.args)}) {t.ok ? "" : <span className="text-destructive">failed</span>}
              </p>
              <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[11px] text-muted-foreground">{t.result}</p>
            </div>
          ))}
          {trace.sql?.map((q: string, i: number) => (
            <pre key={i} className="mt-1 whitespace-pre-wrap rounded bg-muted/40 p-2 font-mono text-[11px]">{q}</pre>
          ))}
        </Block>
      )}

      {trace.prompt_sections?.length > 0 && (
        <Block icon={Brain} title="Prompt sections">
          <div className="space-y-1">
            {trace.prompt_sections.map((s: any) => (
              <div key={s.name} className="rounded-md border">
                <button className="flex w-full items-center justify-between px-2 py-1.5 text-left" onClick={() => setOpenSection(openSection === s.name ? null : s.name)}>
                  <span className="flex items-center gap-1.5 font-mono">
                    <ChevronRight className={cn("size-3 transition", openSection === s.name && "rotate-90")} /> {s.name}
                  </span>
                  <span className="text-[11px] text-muted-foreground">{s.chars} chars</span>
                </button>
                {openSection === s.name && <pre className="max-h-64 overflow-auto whitespace-pre-wrap border-t bg-muted/30 p-2 font-mono text-[11px]">{s.text}</pre>}
              </div>
            ))}
          </div>
        </Block>
      )}

      {trace.llm && (
        <Block icon={Coins} title="Model & cost">
          <p>
            {trace.llm.provider}/{trace.llm.model} · key: {trace.llm.key_source} · {trace.llm.tokens_in} in / {trace.llm.tokens_out} out tokens ·{" "}
            <span className="font-mono">${Number(trace.llm.cost_usd || 0).toFixed(5)}</span>
          </p>
          {trace.rounds?.length > 1 && <p className="mt-1 text-muted-foreground">{trace.rounds.length} LLM rounds (tool calls in between)</p>}
        </Block>
      )}
    </div>
  );
}

export function TraceById({ traceId }: { traceId: string | null }) {
  const api = useApi();
  const { data, isLoading } = useQuery({ queryKey: ["trace", traceId], queryFn: () => api.get(`/traces/${traceId}`), enabled: !!traceId });
  if (!traceId) return <p className="p-6 text-center text-sm text-muted-foreground">Select an AI reply to see exactly how it was produced.</p>;
  if (isLoading) return <LoadingBlock />;
  return <TraceView trace={data?.data} />;
}
