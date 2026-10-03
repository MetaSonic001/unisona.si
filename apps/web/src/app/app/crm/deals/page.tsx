"use client";

import { DndContext, type DragEndEvent, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KanbanSquare, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { LoadingBlock, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useApi } from "@/lib/api";
import { money, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

function DealCard({ d }: { d: any }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: d.id, data: d });
  return (
    <div ref={setNodeRef} {...listeners} {...attributes} style={transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined}
      className={cn("cursor-grab rounded-lg border bg-card p-3 shadow-sm active:cursor-grabbing", isDragging && "z-50 opacity-80 shadow-lg")}>
      <p className="text-sm font-medium">{d.title}</p>
      <div className="mt-1.5 flex items-center justify-between text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{money(d.value, d.currency)}</span>
        <span>{timeAgo(d.updated_at)}</span>
      </div>
      {d.contact_id && <Link href={`/app/crm/contacts/${d.contact_id}`} onPointerDown={(e) => e.stopPropagation()} className="mt-1 block text-[11px] text-brand hover:underline">View contact</Link>}
    </div>
  );
}

function Column({ stage, deals }: { stage: any; deals: any[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.id });
  const total = deals.reduce((a, d) => a + (d.value || 0), 0);
  return (
    <div ref={setNodeRef} className={cn("flex w-72 shrink-0 flex-col rounded-xl border bg-muted/30 p-2.5", isOver && "border-brand bg-brand-soft/30")}>
      <div className="mb-2 flex items-center justify-between px-1">
        <p className="flex items-center gap-2 text-sm font-medium"><span className="size-2 rounded-full" style={{ background: stage.color }} />{stage.name}<Badge variant="secondary" className="h-5">{deals.length}</Badge></p>
        <span className="text-xs text-muted-foreground">{money(total)}</span>
      </div>
      <div className="flex min-h-24 flex-col gap-2">{deals.map((d) => <DealCard key={d.id} d={d} />)}</div>
    </div>
  );
}

export default function DealsPage() {
  const api = useApi();
  const qc = useQueryClient();
  const [pid, setPid] = useState<string | null>(null);
  const { data: pls } = useQuery({ queryKey: ["pipelines"], queryFn: () => api.get("/crm/pipelines") });
  const pipeline = (pls?.items || []).find((p: any) => p.id === pid) || pls?.items?.[0];
  const { data: deals, isLoading } = useQuery({ queryKey: ["deals", pipeline?.id], queryFn: () => api.get(`/crm/deals?pipeline_id=${pipeline.id}&limit=500`), enabled: !!pipeline });
  const move = useMutation({
    mutationFn: ({ id, stage }: { id: string; stage: string }) => api.patch(`/crm/deals/${id}`, { stage, status: stage === "won" ? "won" : stage === "lost" ? "lost" : "open" }),
    onMutate: ({ id, stage }) => qc.setQueryData(["deals", pipeline?.id], (old: any) => ({ ...old, items: old.items.map((d: any) => (d.id === id ? { ...d, stage } : d)) })),
    onSettled: () => qc.invalidateQueries({ queryKey: ["deals"] }),
  });
  const create = useMutation({ mutationFn: (title: string) => api.post("/crm/deals", { pipeline_id: pipeline.id, stage: pipeline.stages[0].id, title, value: Number(prompt("Value (₹)") || 0) }), onSuccess: () => qc.invalidateQueries({ queryKey: ["deals"] }) });
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const onEnd = (e: DragEndEvent) => { if (e.over && e.active.data.current?.stage !== e.over.id) move.mutate({ id: String(e.active.id), stage: String(e.over.id) }); };

  return (
    <div>
      <PageHeader icon={KanbanSquare} title="Deals" description="Pipelines fill themselves: qualified conversations create deals automatically."
        actions={<>
          {(pls?.items || []).length > 1 && <select className="rounded-md border bg-background px-2 py-1.5 text-sm" value={pipeline?.id} onChange={(e) => setPid(e.target.value)}>{pls.items.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select>}
          <Button size="sm" onClick={() => { const t = prompt("Deal title"); if (t) create.mutate(t); }}><Plus className="size-3.5" /> New deal</Button>
        </>} />
      {isLoading || !pipeline ? <LoadingBlock /> : (
        <DndContext sensors={sensors} onDragEnd={onEnd}>
          <div className="flex gap-3 overflow-x-auto p-6">
            {pipeline.stages.map((s: any) => <Column key={s.id} stage={s} deals={(deals?.items || []).filter((d: any) => d.stage === s.id)} />)}
          </div>
        </DndContext>
      )}
      <Card className="hidden" />
    </div>
  );
}
