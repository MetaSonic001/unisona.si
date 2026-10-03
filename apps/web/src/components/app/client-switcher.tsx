"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Building, Check, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { activeWorkspace, setActiveWorkspace, useApi } from "@/lib/api";

function switchTo(id: string | null) {
  setActiveWorkspace(id);
  window.location.href = "/app"; // fresh load: every cache, socket and query re-scopes to the chosen account
}

/** Agency switcher: jump between your agency workspace and client sub-accounts (shown only for agencies). */
export function ClientSwitcher() {
  const api = useApi();
  const { data } = useQuery({ queryKey: ["accessible"], queryFn: () => api.get("/workspaces/accessible"), staleTime: 60000 });
  if (!data || (!data.home.agency && data.clients.length === 0)) return null;
  const current = activeWorkspace();
  const currentClient = data.clients.find((c: any) => c.id === current);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline" className="max-w-[200px] gap-1.5">
          <Building className="size-3.5 text-brand" />
          <span className="truncate">{currentClient ? currentClient.name : data.home.name}</span>
          <ChevronsUpDown className="size-3.5 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="text-xs text-muted-foreground">Agency</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => switchTo(null)}>
          <Building className="size-4" /> <span className="flex-1">{data.home.name}</span> {!currentClient && <Check className="size-4" />}
        </DropdownMenuItem>
        {data.clients.length > 0 && <DropdownMenuSeparator />}
        {data.clients.length > 0 && <DropdownMenuLabel className="text-xs text-muted-foreground">Client accounts</DropdownMenuLabel>}
        {data.clients.map((c: any) => (
          <DropdownMenuItem key={c.id} onSelect={() => switchTo(c.id)}>
            <span className="grid size-5 place-items-center rounded bg-muted text-[10px] font-semibold">{c.name[0]}</span>
            <span className="flex-1 truncate">{c.name}</span> {currentClient?.id === c.id && <Check className="size-4" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => { setActiveWorkspace(null); window.location.href = "/app/agency"; }}>
          <ArrowLeftRight className="size-4" /> Manage clients
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ClientBanner() {
  const api = useApi();
  const { data } = useQuery({ queryKey: ["accessible"], queryFn: () => api.get("/workspaces/accessible"), staleTime: 60000 });
  const current = activeWorkspace();
  const client = data?.clients?.find((c: any) => c.id === current);
  if (!client) return null;
  return (
    <div className="flex items-center gap-2 border-b bg-brand-soft/60 px-4 py-1.5 text-xs">
      <Building className="size-3.5 text-brand" />
      <span>You&apos;re managing <b>{client.name}</b> as their agency. Changes apply to this client only.</span>
      <button className="ml-auto font-medium text-brand hover:underline" onClick={() => switchTo(null)}>Back to {data.home.name}</button>
    </div>
  );
}
