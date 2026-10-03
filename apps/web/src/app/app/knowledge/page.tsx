"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, FileSearch, FileSpreadsheet, FileText, FileUp, Globe, Link2, Loader2, MessageSquareQuote, Plus, RefreshCw, Search, Trash2, Type } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { TraceView } from "@/components/agent/diagnostics";
import { EmptyState, LoadingBlock, PageHeader, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const ICON: Record<string, any> = { url: Link2, website: Globe, file: FileText, table: FileSpreadsheet, text: Type, qa: MessageSquareQuote };

export default function KnowledgePage() {
  const api = useApi();
  const qc = useQueryClient();
  const [kb, setKb] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [viewing, setViewing] = useState<any>(null);
  const { data: kbs, isLoading } = useQuery({ queryKey: ["kbs"], queryFn: () => api.get("/knowledge/bases") });
  const active = kb || kbs?.items?.[0]?.id;
  const { data: sources } = useQuery({ queryKey: ["sources", active], queryFn: () => api.get(`/knowledge/sources?kb_id=${active}`), enabled: !!active, refetchInterval: (q) => ((q.state.data as any)?.items?.some((s: any) => ["pending", "processing"].includes(s.status)) ? 2500 : 15000) });
  const createKb = useMutation({ mutationFn: (name: string) => api.post("/knowledge/bases", { name }), onSuccess: (k) => { qc.invalidateQueries({ queryKey: ["kbs"] }); setKb(k.id); } });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/knowledge/sources/${id}`), onSuccess: () => { qc.invalidateQueries({ queryKey: ["sources"] }); qc.invalidateQueries({ queryKey: ["kbs"] }); } });
  const reindex = useMutation({ mutationFn: (id: string) => api.post(`/knowledge/sources/${id}/reindex`), onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }) });

  return (
    <div>
      <PageHeader icon={BookOpen} title="Knowledge" description="Everything your agents know. Shared across agents, searchable, fully transparent."
        actions={<Button className="bg-brand text-brand-foreground hover:bg-brand/90" onClick={() => setAddOpen(true)} disabled={!active}><Plus className="size-4" /> Add knowledge</Button>} />
      {isLoading ? <LoadingBlock /> : (
        <div className="grid gap-6 p-6 lg:grid-cols-[240px_1fr]">
          <div className="space-y-2">
            {(kbs?.items || []).map((k: any) => (
              <button key={k.id} onClick={() => setKb(k.id)} className={cn("w-full rounded-lg border p-3 text-left transition", active === k.id ? "border-brand bg-brand-soft/40" : "hover:bg-muted/50")}>
                <p className="text-sm font-medium">{k.name}</p>
                <p className="text-xs text-muted-foreground">{k.sources} sources · {k.chunks} chunks · {k.agent_ids.length} agents</p>
              </button>
            ))}
            <Button variant="outline" size="sm" className="w-full" onClick={() => { const n = prompt("Knowledge base name"); if (n) createKb.mutate(n); }}><Plus className="size-3.5" /> New knowledge base</Button>
          </div>
          <Tabs defaultValue="sources" className="min-w-0">
            <TabsList>
              <TabsTrigger value="sources">Sources</TabsTrigger>
              <TabsTrigger value="test"><FileSearch className="size-3.5" /> Test a question</TabsTrigger>
            </TabsList>
            <TabsContent value="sources" className="mt-4">
              {(sources?.items || []).length === 0 ? (
                <EmptyState icon={FileUp} title="No sources yet" description="Upload PDFs, Word, PowerPoint, Excel/CSV, or add links, whole websites, text and Q&A." action={<Button onClick={() => setAddOpen(true)}>Add knowledge</Button>} />
              ) : (
                <Card className="gap-0 overflow-hidden p-0">
                  <table className="w-full text-sm">
                    <thead className="border-b bg-muted/30 text-left text-xs text-muted-foreground">
                      <tr><th className="px-4 py-2 font-medium">Source</th><th className="px-2 font-medium">Status</th><th className="px-2 font-medium">Chunks</th><th className="px-2 font-medium">Updated</th><th /></tr>
                    </thead>
                    <tbody>
                      {sources.items.map((s: any) => {
                        const Icon = ICON[s.type] || FileText;
                        return (
                          <tr key={s.id} className="border-b last:border-0 hover:bg-muted/20">
                            <td className="max-w-[380px] px-4 py-2.5">
                              <button className="flex items-center gap-2 text-left" onClick={() => setViewing(s)}>
                                <Icon className="size-4 shrink-0 text-muted-foreground" />
                                <span className="truncate font-medium hover:underline">{s.title}</span>
                                {s.type === "table" && <Badge variant="secondary" className="text-[10px]">SQL table · {s.meta?.rows} rows</Badge>}
                                {s.type === "website" && s.meta?.documents && <Badge variant="secondary" className="text-[10px]">{s.meta.documents} pages</Badge>}
                              </button>
                              {s.error && <p className="mt-0.5 text-xs text-destructive">{s.error}</p>}
                            </td>
                            <td className="px-2"><StatusBadge status={s.status} />{s.meta?.progress && <span className="ml-1 text-[11px] text-muted-foreground">{s.meta.progress}</span>}</td>
                            <td className="px-2 tabular-nums">{s.chunks}</td>
                            <td className="px-2 text-xs text-muted-foreground">{timeAgo(s.last_ingested_at || s.created_at)}</td>
                            <td className="px-2 text-right">
                              <Button size="icon" variant="ghost" className="size-7" onClick={() => reindex.mutate(s.id)} title="Re-index"><RefreshCw className="size-3.5" /></Button>
                              <Button size="icon" variant="ghost" className="size-7" onClick={() => confirm(`Delete ${s.title}?`) && del.mutate(s.id)} title="Delete"><Trash2 className="size-3.5" /></Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </Card>
              )}
            </TabsContent>
            <TabsContent value="test" className="mt-4"><TestQuery kbId={active} /></TabsContent>
          </Tabs>
        </div>
      )}
      <AddDialog open={addOpen} onOpenChange={setAddOpen} kbId={active} />
      <Sheet open={!!viewing} onOpenChange={(o) => !o && setViewing(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          <SheetHeader><SheetTitle>{viewing?.title}</SheetTitle></SheetHeader>
          {viewing && <ChunkList sourceId={viewing.id} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function ChunkList({ sourceId }: { sourceId: string }) {
  const api = useApi();
  const { data, isLoading } = useQuery({ queryKey: ["chunks", sourceId], queryFn: () => api.get(`/knowledge/sources/${sourceId}/chunks`) });
  if (isLoading) return <LoadingBlock />;
  return (
    <div className="space-y-3 px-4 pb-6">
      {data?.dataset && (
        <Card className="gap-2 p-3">
          <p className="text-sm font-medium">Queryable table <code className="font-mono text-xs">{data.dataset.table_name}</code> · {data.dataset.row_count} rows</p>
          <div className="flex flex-wrap gap-1">{data.dataset.schema_card.columns?.map((c: any) => <Badge key={c.name} variant="outline" className="font-mono text-[10px]">{c.name}: {c.type}</Badge>)}</div>
          <p className="text-xs text-muted-foreground">Agents answer questions about this table with safe, read-only SQL (e.g. “Where is order SK10231?”).</p>
        </Card>
      )}
      {(data?.items || []).map((c: any) => (
        <div key={c.id} className="rounded-lg border p-3">
          <p className="mb-1 font-mono text-[10px] text-muted-foreground">#{c.ordinal} · {c.meta?.heading || c.meta?.title}</p>
          <p className="whitespace-pre-wrap text-xs">{c.text}</p>
        </div>
      ))}
    </div>
  );
}

function TestQuery({ kbId }: { kbId?: string }) {
  const api = useApi();
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("deep");
  const run = useMutation({ mutationFn: () => api.post("/knowledge/search", { query: q, kb_ids: kbId ? [kbId] : undefined, mode, k: 6 }) });
  return (
    <div className="space-y-4">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q) run.mutate(); }}>
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Ask what a customer would ask… (any language)" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select value={mode} onValueChange={setMode}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="fast">Fast hybrid</SelectItem><SelectItem value="deep">Deep + rerank</SelectItem></SelectContent>
        </Select>
        <Button type="submit" disabled={!q || run.isPending}>{run.isPending ? <Loader2 className="size-4 animate-spin" /> : "Search"}</Button>
      </form>
      {run.data && <TraceView trace={{ router: run.data.mode, confidence: run.data.confidence, confident: run.data.confidence >= 0.32, retrieval: run.data, timings_ms: run.data.timings_ms }} />}
      {!run.data && <p className="text-sm text-muted-foreground">See exactly which passages an agent would use, with semantic, keyword, fusion and rerank scores.</p>}
    </div>
  );
}

function AddDialog({ open, onOpenChange, kbId }: { open: boolean; onOpenChange: (o: boolean) => void; kbId?: string }) {
  const api = useApi();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState("");
  const [pages, setPages] = useState("25");
  const [refresh, setRefresh] = useState("0");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [qa, setQa] = useState("");
  const [busy, setBusy] = useState(false);
  const done = () => { qc.invalidateQueries({ queryKey: ["sources"] }); qc.invalidateQueries({ queryKey: ["kbs"] }); onOpenChange(false); toast.success("Added. Indexing in the background."); };
  const post = async (body: any) => { setBusy(true); try { await api.post("/knowledge/sources", { kb_id: kbId, ...body }); done(); } catch (e: any) { toast.error(e.message); } finally { setBusy(false); } };
  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    if (kbId) fd.append("kb_id", kbId);
    try { await api.upload("/knowledge/sources/upload", fd); done(); } catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader><DialogTitle>Add knowledge</DialogTitle></DialogHeader>
        <Tabs defaultValue="file">
          <TabsList className="w-full">
            <TabsTrigger value="file">Files</TabsTrigger><TabsTrigger value="web">Website</TabsTrigger><TabsTrigger value="text">Text</TabsTrigger><TabsTrigger value="qa">Q&amp;A</TabsTrigger>
          </TabsList>
          <TabsContent value="file" className="mt-4">
            <button onClick={() => fileRef.current?.click()} className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center hover:border-brand/50">
              {busy ? <Loader2 className="size-6 animate-spin" /> : <FileUp className="size-6 text-brand" />}
              <p className="text-sm font-medium">Choose files</p>
              <p className="text-xs text-muted-foreground">PDF, DOCX, PPTX, TXT, MD, HTML · CSV/XLSX become SQL tables</p>
            </button>
            <input ref={fileRef} hidden type="file" multiple accept=".pdf,.docx,.pptx,.xlsx,.xls,.csv,.txt,.md,.html,.json" onChange={(e) => upload(e.target.files)} />
          </TabsContent>
          <TabsContent value="web" className="mt-4 space-y-3">
            <Input placeholder="https://yourbusiness.com" value={url} onChange={(e) => setUrl(e.target.value)} />
            <div className="grid grid-cols-2 gap-3">
              <div><p className="mb-1 text-xs">Max pages (whole site)</p><Input type="number" value={pages} onChange={(e) => setPages(e.target.value)} /></div>
              <div><p className="mb-1 text-xs">Auto-refresh every N days (0 = off)</p><Input type="number" value={refresh} onChange={(e) => setRefresh(e.target.value)} /></div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" disabled={!url || busy} onClick={() => post({ type: "url", uri: url, refresh_days: Number(refresh) })}>Just this page</Button>
              <Button disabled={!url || busy} onClick={() => post({ type: "website", uri: url, max_pages: Number(pages), refresh_days: Number(refresh) })}>Crawl the whole site</Button>
            </div>
          </TabsContent>
          <TabsContent value="text" className="mt-4 space-y-3">
            <Input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <Textarea rows={8} placeholder="Paste policies, scripts, product details… Markdown headings help structure." value={text} onChange={(e) => setText(e.target.value)} />
            <Button disabled={text.length < 5 || busy} onClick={() => post({ type: "text", title: title || text.slice(0, 60), text })}>Add text</Button>
          </TabsContent>
          <TabsContent value="qa" className="mt-4 space-y-3">
            <p className="text-xs text-muted-foreground">One pair per block: a line starting with Q: and a line starting with A:.</p>
            <Textarea rows={8} placeholder={"Q: Do you deliver on Sundays?\nA: Yes, between 10 AM and 4 PM in metro cities."} value={qa} onChange={(e) => setQa(e.target.value)} />
            <Button disabled={!qa || busy} onClick={() => {
              const pairs = qa.split(/\n\s*\n/).map((b) => ({ question: (b.match(/Q:\s*(.+)/i) || [])[1], answer: (b.match(/A:\s*([\s\S]+)/i) || [])[1]?.trim() })).filter((p) => p.question && p.answer);
              if (!pairs.length) return toast.error("No Q:/A: pairs found");
              post({ type: "qa", title: `Q&A (${pairs.length})`, pairs });
            }}>Add Q&amp;A</Button>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
