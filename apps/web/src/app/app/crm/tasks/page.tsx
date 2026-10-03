"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { EmptyState, LoadingBlock, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function TasksPage() {
  const api = useApi();
  const qc = useQueryClient();
  const [status, setStatus] = useState("open");
  const [title, setTitle] = useState("");
  const { data, isLoading } = useQuery({ queryKey: ["tasks", status], queryFn: () => api.get(`/crm/tasks?status=${status}&limit=500`) });
  const toggle = useMutation({ mutationFn: (t: any) => api.patch(`/crm/tasks/${t.id}`, { status: t.status === "open" ? "done" : "open" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }) });
  const add = useMutation({ mutationFn: () => api.post("/crm/tasks", { title }), onSuccess: () => { setTitle(""); qc.invalidateQueries({ queryKey: ["tasks"] }); } });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/crm/tasks/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }) });
  return (
    <div>
      <PageHeader icon={CheckSquare} title="Tasks" description="Follow-ups from your team, your agents and automations." />
      <div className="space-y-4 p-6">
        <div className="flex gap-2">
          {["open", "done"].map((s) => <Button key={s} size="sm" variant={status === s ? "default" : "ghost"} className="capitalize" onClick={() => setStatus(s)}>{s}</Button>)}
          <form className="ml-auto flex gap-2" onSubmit={(e) => { e.preventDefault(); if (title) add.mutate(); }}>
            <Input className="w-72" placeholder="New task…" value={title} onChange={(e) => setTitle(e.target.value)} />
            <Button size="sm" type="submit"><Plus className="size-3.5" /> Add</Button>
          </form>
        </div>
        {isLoading ? <LoadingBlock /> : (data?.items || []).length === 0 ? <EmptyState icon={CheckSquare} title="Nothing here" description="Agents create follow-up tasks automatically after conversations." /> : (
          <Card className="gap-0 p-0">
            {data.items.map((t: any) => (
              <div key={t.id} className="flex items-center gap-3 border-b px-4 py-3 last:border-0">
                <Checkbox checked={t.status === "done"} onCheckedChange={() => toggle.mutate(t)} />
                <div className="flex-1">
                  <p className={`text-sm ${t.status === "done" ? "text-muted-foreground line-through" : ""}`}>{t.title}</p>
                  <p className="text-xs text-muted-foreground">{t.due_at ? `due ${timeAgo(t.due_at)}` : "no due date"}{t.contact_id && <> · <Link className="text-brand hover:underline" href={`/app/crm/contacts/${t.contact_id}`}>contact</Link></>}</p>
                </div>
                <Badge variant={t.created_by === "ai" ? "default" : "outline"} className={t.created_by === "ai" ? "bg-brand-soft text-brand" : ""}>{t.created_by}</Badge>
                <Button size="icon" variant="ghost" className="size-7" onClick={() => del.mutate(t.id)}><Trash2 className="size-3.5" /></Button>
              </div>
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}
