"use client";

import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, FlaskConical, LogOut, Moon, Plus, Search, Sun } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Kbd } from "@/components/common";
import { Button } from "@/components/ui/button";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useApi } from "@/lib/api";
import { CLERK_ENABLED, isDevSession, setDevSession } from "@/lib/env";
import { timeAgo } from "@/lib/format";
import { ClientSwitcher } from "./client-switcher";
import { NAV } from "./nav";

export function Topbar() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const api = useApi();
  const qc = useQueryClient();
  const [dev, setDev] = useState(false);
  useEffect(() => setDev(isDevSession()), []);
  const { data: notes } = useQuery({ queryKey: ["notifications"], queryFn: () => api.get("/notifications"), refetchInterval: 60000 });
  const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: () => api.get("/agents") });

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/80 px-3 backdrop-blur-xl">
      <SidebarTrigger />
      <Separator orientation="vertical" className="mx-1 h-5" />
      <button onClick={() => setOpen(true)} className="flex h-8 w-full max-w-xs items-center gap-2 rounded-lg border bg-muted/40 px-2.5 text-sm text-muted-foreground transition hover:bg-muted">
        <Search className="size-3.5" /> <span className="flex-1 text-left">Search or jump to…</span> <Kbd>Ctrl K</Kbd>
      </button>
      <div className="ml-auto flex items-center gap-1.5">
        <ClientSwitcher />
        <Button size="sm" variant="ghost" className="hidden sm:inline-flex" onClick={() => router.push("/app/agents?new=1")}>
          <Plus className="size-4" /> New agent
        </Button>
        <Popover
          onOpenChange={(o) => {
            if (!o && notes?.unread) api.post("/notifications/read").then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
          }}
        >
          <PopoverTrigger asChild>
            <Button size="icon" variant="ghost" className="relative" aria-label="Notifications">
              <Bell className="size-4" />
              {notes?.unread > 0 && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive" />}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 p-0">
            <div className="flex items-center justify-between border-b px-3 py-2">
              <p className="text-sm font-medium">Notifications</p>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => typeof Notification !== "undefined" && Notification.requestPermission()}
              >
                Enable desktop alerts
              </Button>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {(notes?.items || []).length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>}
              {(notes?.items || []).map((n: any) => (
                <Link key={n.id} href={n.link || "#"} className="block border-b px-3 py-2.5 text-sm last:border-0 hover:bg-muted/50">
                  <div className="flex items-center gap-2">
                    {!n.read && <span className="size-1.5 rounded-full bg-brand" />}
                    <span className="font-medium">{n.title}</span>
                  </div>
                  {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{n.body}</p>}
                  <p className="mt-1 text-[11px] text-muted-foreground">{timeAgo(n.created_at)}</p>
                </Link>
              ))}
            </div>
          </PopoverContent>
        </Popover>
        <Button size="icon" variant="ghost" aria-label="Toggle theme" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          <Sun className="size-4 dark:hidden" />
          <Moon className="hidden size-4 dark:block" />
        </Button>
        {dev ? (
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 border-dashed"
            onClick={() => {
              setDevSession(false);
              router.push("/sign-in");
            }}
          >
            <FlaskConical className="size-3.5 text-brand" /> Dev mode <LogOut className="size-3.5" />
          </Button>
        ) : CLERK_ENABLED ? (
          <div className="flex items-center gap-2">
            <OrganizationSwitcher
              hidePersonal={false}
              afterCreateOrganizationUrl="/app/onboarding"
              afterSelectOrganizationUrl="/app"
              appearance={{ elements: { organizationSwitcherTrigger: "px-2 py-1 rounded-md" } }}
            />
            <UserButton />
          </div>
        ) : null}
      </div>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Jump to a page or agent…" />
        <CommandList>
          <CommandEmpty>No results.</CommandEmpty>
          <CommandGroup heading="Pages">
            {NAV.flatMap((g) => g.items).map((i) => (
              <CommandItem key={i.href} onSelect={() => go(i.href)}>
                <i.icon className="size-4" /> {i.title}
              </CommandItem>
            ))}
          </CommandGroup>
          {(agents?.items || []).length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Agents">
                {agents.items.map((a: any) => (
                  <CommandItem key={a.id} onSelect={() => go(`/app/agents/${a.id}`)}>
                    {a.name}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}
          <CommandSeparator />
          <CommandGroup heading="Actions">
            <CommandItem onSelect={() => go("/app/agents?new=1")}>Create an agent</CommandItem>
            <CommandItem onSelect={() => go("/app/knowledge")}>Add knowledge</CommandItem>
            <CommandItem onSelect={() => go("/app/settings?tab=providers")}>Add an AI provider key</CommandItem>
            <CommandItem onSelect={() => go("/app/onboarding")}>Run the setup wizard</CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </header>
  );
}
