"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/brand";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarMenu,
  SidebarMenuBadge, SidebarMenuButton, SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useApi } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { NAV } from "./nav";

export function AppSidebar() {
  const pathname = usePathname();
  const api = useApi();
  const { me, connected } = useWorkspace();
  const { data: convs } = useQuery({ queryKey: ["conversations", "counts"], queryFn: () => api.get("/conversations?limit=1"), refetchInterval: 30000 });
  const { data: live } = useQuery({ queryKey: ["live"], queryFn: () => api.get("/calls/live"), refetchInterval: 15000 });
  const pending = convs?.counts?.handoff_pending || 0;
  const liveCount = live?.items?.length || 0;

  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <Link href="/app" className="flex items-center gap-2 px-1.5 py-1">
          <Logo className="group-data-[collapsible=icon]:hidden" />
          <span className="hidden group-data-[collapsible=icon]:block">
            <Logo compact />
          </span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        {NAV.map((g, gi) => (
          <SidebarGroup key={gi}>
            {g.label && <SidebarGroupLabel>{g.label}</SidebarGroupLabel>}
            <SidebarGroupContent>
              <SidebarMenu>
                {g.items.map((item) => {
                  const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
                  const badge = item.badge === "inbox" ? pending : item.badge === "live" ? liveCount : 0;
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
                        <Link href={item.href}>
                          <item.icon />
                          <span>{item.title}</span>
                        </Link>
                      </SidebarMenuButton>
                      {badge > 0 && (
                        <SidebarMenuBadge className={item.badge === "inbox" ? "bg-warning/20 text-warning" : "bg-success/20 text-success"}>{badge}</SidebarMenuBadge>
                      )}
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
        {me?.dev_mode && (
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={pathname.startsWith("/app/dev")} tooltip="Dev mode">
                    <Link href="/app/dev">
                      <FlaskConical />
                      <span>Dev mode</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter>
        <div className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          <span className={`size-2 rounded-full ${connected ? "bg-success" : "bg-muted-foreground/40"}`} />
          {connected ? "Live updates on" : "Connecting…"}
          <span className="ml-auto rounded bg-brand-soft px-1.5 py-0.5 font-medium capitalize text-brand">{me?.workspace.plan}</span>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
