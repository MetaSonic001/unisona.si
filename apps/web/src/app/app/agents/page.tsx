"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Copy, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { ChannelDot, EmptyState, LoadingBlock, PageHeader, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { TemplateGallery } from "@/components/agent/template-gallery";
import { useApi } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

function AgentsInner() {
  const api = useApi();
  const qc = useQueryClient();
  const params = useSearchParams();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (params.get("new")) setOpen(true);
  }, [params]);
  const { data, isLoading } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });
  const dup = useMutation({ mutationFn: (id: string) => api.post(`/agents/${id}/duplicate`), onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }) });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/agents/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success("Agent deleted");
    },
  });

  return (
    <div>
      <PageHeader
        icon={Bot}
        title="Agents"
        description="Each agent is one brain you can deploy to every channel."
        actions={
          <Button className="bg-brand text-brand-foreground hover:bg-brand/90" onClick={() => setOpen(true)}>
            <Plus className="size-4" /> New agent
          </Button>
        }
      />
      <div className="p-6">
        {isLoading ? (
          <LoadingBlock />
        ) : (data?.items || []).length === 0 ? (
          <EmptyState icon={Bot} title="No agents yet" description="Create your first agent from a template or let us build one from your website." action={<Button onClick={() => setOpen(true)}>Create agent</Button>} />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.items.map((a: any) => (
              <Card key={a.id} className="group relative gap-0 overflow-hidden p-0 transition hover:shadow-md">
                <Link href={`/app/agents/${a.id}`} className="block p-5">
                  <div className="flex items-start gap-3">
                    <span className="grid size-11 place-items-center rounded-xl bg-gradient-to-br from-brand to-[oklch(0.7_0.15_220)] text-lg font-semibold text-white">
                      {a.config.persona?.name?.[0] || a.name[0]}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{a.name}</p>
                      <p className="truncate text-xs text-muted-foreground">{a.config.persona?.role}</p>
                    </div>
                    <StatusBadge status={a.status} />
                  </div>
                  <p className="mt-3 line-clamp-2 min-h-8 text-xs text-muted-foreground">{a.config.business?.description || a.description || "No description yet."}</p>
                  <div className="mt-4 flex items-center justify-between">
                    <div className="flex -space-x-1">
                      {a.channels.filter((c: any) => c.enabled).map((c: any) => (
                        <ChannelDot key={c.id} channel={c.type} />
                      ))}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {a.conversations} conversations · v{a.published_version}
                      {a.has_unpublished_changes && <span className="ml-1 text-warning">· unpublished edits</span>}
                    </span>
                  </div>
                </Link>
                <div className="absolute right-3 top-14 opacity-0 transition group-hover:opacity-100">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="icon" variant="ghost" className="size-7">
                        <MoreHorizontal className="size-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => dup.mutate(a.id)}>
                        <Copy className="size-4" /> Duplicate
                      </DropdownMenuItem>
                      <DropdownMenuItem className="text-destructive" onClick={() => confirm(`Delete ${a.name}? This removes its conversations.`) && del.mutate(a.id)}>
                        <Trash2 className="size-4" /> Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <div className={cn("border-t bg-muted/30 px-5 py-2 text-[11px] text-muted-foreground")}>Updated {timeAgo(a.updated_at)}</div>
              </Card>
            ))}
            <button onClick={() => setOpen(true)} className="flex min-h-[180px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-sm text-muted-foreground transition hover:border-brand/50 hover:text-brand">
              <Plus className="size-5" /> New agent
            </button>
          </div>
        )}
      </div>
      <TemplateGallery open={open} onOpenChange={setOpen} />
    </div>
  );
}

export default function AgentsPage() {
  return (
    <Suspense>
      <AgentsInner />
    </Suspense>
  );
}
