"use client";

import type { LucideIcon } from "lucide-react";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { channelMeta } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions, icon: Icon, className }: {
  title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; icon?: LucideIcon; className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 border-b px-6 py-5 sm:flex-row sm:items-center sm:justify-between", className)}>
      <div className="flex items-start gap-3">
        {Icon && (
          <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand">
            <Icon className="size-[18px]" />
          </span>
        )}
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({ label, value, hint, icon: Icon, trend, className }: {
  label: string; value: React.ReactNode; hint?: React.ReactNode; icon?: LucideIcon; trend?: "up" | "down"; className?: string;
}) {
  return (
    <Card className={cn("gap-1 p-4", className)}>
      <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
        <span>{label}</span>
        {Icon && <Icon className="size-4 opacity-70" />}
      </div>
      <div className="text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      {hint && <div className={cn("text-xs text-muted-foreground", trend === "up" && "text-success", trend === "down" && "text-destructive")}>{hint}</div>}
    </Card>
  );
}

export function EmptyState({ icon: Icon, title, description, action, className }: {
  icon?: LucideIcon; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-14 text-center", className)}>
      {Icon && (
        <span className="grid size-11 place-items-center rounded-full bg-brand-soft text-brand">
          <Icon className="size-5" />
        </span>
      )}
      <div>
        <p className="font-medium">{title}</p>
        {description && <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ChannelBadge({ channel, className }: { channel?: string | null; className?: string }) {
  const m = channelMeta(channel);
  const Icon = m.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", m.bg, m.color, className)}>
      <Icon className="size-3" />
      {m.label}
    </span>
  );
}

export function ChannelDot({ channel }: { channel?: string | null }) {
  const m = channelMeta(channel);
  const Icon = m.icon;
  return (
    <span className={cn("grid size-6 place-items-center rounded-full", m.bg, m.color)} title={m.label}>
      <Icon className="size-3.5" />
    </span>
  );
}

const STATUS: Record<string, string> = {
  live: "bg-success/15 text-success", ready: "bg-success/15 text-success", active: "bg-success/15 text-success",
  completed: "bg-success/15 text-success", valid: "bg-success/15 text-success", done: "bg-success/15 text-success",
  delivered: "bg-success/15 text-success", approved: "bg-success/15 text-success", running: "bg-brand-soft text-brand",
  processing: "bg-brand-soft text-brand", pending: "bg-warning/15 text-warning", queued: "bg-warning/15 text-warning",
  handoff_pending: "bg-warning/20 text-warning", human: "bg-ch-web/15 text-ch-web", ai: "bg-brand-soft text-brand",
  draft: "bg-muted text-muted-foreground", paused: "bg-muted text-muted-foreground", closed: "bg-muted text-muted-foreground",
  error: "bg-destructive/15 text-destructive", failed: "bg-destructive/15 text-destructive", invalid: "bg-destructive/15 text-destructive",
  open: "bg-ch-web/15 text-ch-web", scheduled: "bg-warning/15 text-warning", won: "bg-success/15 text-success", lost: "bg-destructive/15 text-destructive",
};
const STATUS_LABEL: Record<string, string> = { handoff_pending: "needs human", ai: "AI handling", human: "human handling" };

export function StatusBadge({ status, className }: { status?: string | null; className?: string }) {
  if (!status) return null;
  return (
    <Badge variant="secondary" className={cn("border-0 capitalize", STATUS[status] || "bg-muted text-muted-foreground", className)}>
      {STATUS_LABEL[status] || status.replaceAll("_", " ")}
    </Badge>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin", className)} />;
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
      <Spinner /> {label}
    </div>
  );
}

export function Section({ title, description, children, actions, className }: {
  title: string; description?: React.ReactNode; children: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{children}</kbd>;
}
