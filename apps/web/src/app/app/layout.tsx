"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { ClientBanner } from "@/components/app/client-switcher";
import { AppSidebar } from "@/components/app/sidebar";
import { Topbar } from "@/components/app/topbar";
import { LoadingBlock } from "@/components/common";
import { Button } from "@/components/ui/button";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { activeWorkspace, setActiveWorkspace } from "@/lib/api";
import { WorkspaceProvider, useWorkspace } from "@/lib/workspace";

function Gate({ children }: { children: React.ReactNode }) {
  const { me, loading, error } = useWorkspace();
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (me && me.counts.agents === 0 && !me.workspace.onboarding?.completed && !me.workspace.onboarding?.skipped && pathname !== "/app/onboarding" && !pathname.startsWith("/app/dev")) {
      router.replace("/app/onboarding");
    }
  }, [me, pathname, router]);
  useEffect(() => {
    // A client account you no longer have access to: fall back to your own workspace.
    if (error && activeWorkspace() && /access|403/i.test(error.message)) {
      setActiveWorkspace(null);
      location.reload();
    }
  }, [error]);
  if (loading) return <LoadingBlock label="Loading your workspace…" />;
  if (error)
    return (
      <div className="mx-auto mt-24 max-w-md rounded-xl border p-6 text-center">
        <p className="font-medium">Can&apos;t reach the Unisona API</p>
        <p className="mt-2 text-sm text-muted-foreground">{error.message}. Make sure the API is running (`pnpm dev:api`) on {process.env.NEXT_PUBLIC_API_URL}.</p>
        <Button className="mt-4" variant="outline" onClick={() => location.reload()}>
          Retry
        </Button>
      </div>
    );
  return <>{children}</>;
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const bare = pathname === "/app/onboarding";
  return (
    <WorkspaceProvider>
      {bare ? (
        <Gate>{children}</Gate>
      ) : (
        <SidebarProvider>
          <AppSidebar />
          <SidebarInset className="min-w-0">
            <Topbar />
            <ClientBanner />
            <Gate>
              <div className="min-w-0 flex-1">{children}</div>
            </Gate>
          </SidebarInset>
        </SidebarProvider>
      )}
    </WorkspaceProvider>
  );
}
