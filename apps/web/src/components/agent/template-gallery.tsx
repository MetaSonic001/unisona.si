"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Icons from "lucide-react";
import { Search, Sparkles, Wand2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";

function iconFor(name: string) {
  const key = name.split("-").map((p) => p[0].toUpperCase() + p.slice(1)).join("");
  return (Icons as any)[key] || Sparkles;
}

export function TemplateGallery({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const api = useApi();
  const router = useRouter();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [name, setName] = useState("");
  const { data } = useQuery({ queryKey: ["templates"], queryFn: () => api.get("/templates"), enabled: open });
  const create = useMutation({
    mutationFn: (template_id: string) => api.post("/agents", { template_id, name: name || undefined }),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success(`${a.name} created`);
      onOpenChange(false);
      router.push(`/app/agents/${a.id}?tab=persona`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const items = (data?.items || []).filter((t: any) => !q || (t.name + t.description + t.category).toLowerCase().includes(q.toLowerCase()));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl gap-0 p-0 sm:max-w-4xl">
        <DialogHeader className="border-b p-5">
          <DialogTitle>Create an agent</DialogTitle>
          <DialogDescription>Start from a template. Everything is editable, and you can also auto-build one from your website in the setup wizard.</DialogDescription>
          <div className="mt-3 flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input className="pl-8" placeholder="Search templates" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <Input className="max-w-[220px]" placeholder="Agent name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
            <Button variant="outline" asChild>
              <Link href="/app/onboarding">
                <Wand2 className="size-4" /> From my website
              </Link>
            </Button>
          </div>
        </DialogHeader>
        <div className="grid max-h-[60vh] gap-3 overflow-y-auto p-5 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((t: any) => {
            const Icon = iconFor(t.icon);
            return (
              <button
                key={t.id}
                disabled={create.isPending}
                onClick={() => create.mutate(t.id)}
                className="group rounded-xl border p-4 text-left transition hover:border-brand/50 hover:bg-brand-soft/30 disabled:opacity-60"
              >
                <div className="flex items-center justify-between">
                  <span className="grid size-9 place-items-center rounded-lg bg-brand-soft text-brand">
                    <Icon className="size-[18px]" />
                  </span>
                  <Badge variant="outline" className="text-[10px]">{t.category}</Badge>
                </div>
                <p className="mt-3 text-sm font-medium">{t.name}</p>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{t.description}</p>
              </button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}

