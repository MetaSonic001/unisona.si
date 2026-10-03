"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus, Trash2 } from "lucide-react";
import { EmptyState, LoadingBlock, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useApi } from "@/lib/api";

export default function CompaniesPage() {
  const api = useApi();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["companies"], queryFn: () => api.get("/crm/companies") });
  const add = useMutation({ mutationFn: (name: string) => api.post("/crm/companies", { name, domain: prompt("Domain (optional)") || undefined }), onSuccess: () => qc.invalidateQueries({ queryKey: ["companies"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.del(`/crm/companies/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["companies"] }) });
  return (
    <div>
      <PageHeader icon={Building2} title="Companies" description="Accounts for B2B relationships." actions={<Button size="sm" onClick={() => { const n = prompt("Company name"); if (n) add.mutate(n); }}><Plus className="size-3.5" /> Add company</Button>} />
      <div className="p-6">
        {isLoading ? <LoadingBlock /> : (data?.items || []).length === 0 ? <EmptyState icon={Building2} title="No companies yet" /> : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.items.map((c: any) => (
              <Card key={c.id} className="flex-row items-center gap-3 p-4">
                <span className="grid size-10 place-items-center rounded-lg bg-muted font-semibold">{c.name[0]}</span>
                <div className="flex-1"><p className="font-medium">{c.name}</p><p className="text-xs text-muted-foreground">{c.domain || "—"}</p></div>
                <Button size="icon" variant="ghost" onClick={() => del.mutate(c.id)}><Trash2 className="size-3.5" /></Button>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
