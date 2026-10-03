"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format, startOfWeek } from "date-fns";
import { Calendar, ChevronLeft, ChevronRight, Copy, ExternalLink } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { LoadingBlock, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export default function CalendarPage() {
  const api = useApi();
  const qc = useQueryClient();
  const [week, setWeek] = useState(startOfWeek(new Date(), { weekStartsOn: 1 }));
  const { data: cals } = useQuery({ queryKey: ["calendars"], queryFn: () => api.get("/crm/calendars") });
  const cal = cals?.items?.[0];
  const { data: appts, isLoading } = useQuery({ queryKey: ["appointments"], queryFn: () => api.get("/crm/appointments?limit=500") });
  const save = useMutation({ mutationFn: (b: any) => api.patch(`/crm/calendars/${cal.id}`, b), onSuccess: () => { qc.invalidateQueries({ queryKey: ["calendars"] }); toast.success("Availability saved"); } });
  const cancel = useMutation({ mutationFn: (id: string) => api.patch(`/crm/appointments/${id}`, { status: "cancelled" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["appointments"] }) });
  const days = Array.from({ length: 7 }, (_, i) => addDays(week, i));
  const bookUrl = cal && typeof window !== "undefined" ? `${window.location.origin}/book/${cal.slug}` : "";

  return (
    <div>
      <PageHeader icon={Calendar} title="Calendar" description="Agents check availability and book directly. Share your booking page anywhere."
        actions={cal && <>
          <Button size="sm" variant="outline" onClick={() => { navigator.clipboard.writeText(bookUrl); toast.success("Booking link copied"); }}><Copy className="size-3.5" /> Copy booking link</Button>
          <Button size="sm" variant="outline" asChild><a href={`/book/${cal.slug}`} target="_blank" rel="noreferrer"><ExternalLink className="size-3.5" /> Open</a></Button>
        </>} />
      <div className="grid gap-6 p-6 xl:grid-cols-[1fr_320px]">
        <Card className="gap-0 overflow-hidden p-0">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <p className="font-medium">{format(week, "d MMM")} – {format(addDays(week, 6), "d MMM yyyy")}</p>
            <div className="flex gap-1">
              <Button size="icon" variant="ghost" onClick={() => setWeek(addDays(week, -7))}><ChevronLeft className="size-4" /></Button>
              <Button size="sm" variant="ghost" onClick={() => setWeek(startOfWeek(new Date(), { weekStartsOn: 1 }))}>Today</Button>
              <Button size="icon" variant="ghost" onClick={() => setWeek(addDays(week, 7))}><ChevronRight className="size-4" /></Button>
            </div>
          </div>
          {isLoading ? <LoadingBlock /> : (
            <div className="grid grid-cols-7 divide-x">
              {days.map((d) => {
                const items = (appts?.items || []).filter((a: any) => format(new Date(a.start_at), "yyyy-MM-dd") === format(d, "yyyy-MM-dd"));
                const today = format(d, "yyyy-MM-dd") === format(new Date(), "yyyy-MM-dd");
                return (
                  <div key={d.toISOString()} className="min-h-[360px] p-2">
                    <p className={cn("mb-2 text-center text-xs", today && "font-semibold text-brand")}>{format(d, "EEE d")}</p>
                    <div className="space-y-1.5">
                      {items.map((a: any) => (
                        <div key={a.id} className={cn("rounded-md border-l-2 bg-brand-soft/50 p-1.5 text-[11px]", a.status === "cancelled" ? "border-muted-foreground opacity-50 line-through" : "border-brand")}>
                          <p className="font-medium">{format(new Date(a.start_at), "HH:mm")}</p>
                          <p className="line-clamp-2">{a.title}</p>
                          <p className="text-muted-foreground">{a.source}</p>
                          {a.status === "booked" && <button className="text-destructive" onClick={() => cancel.mutate(a.id)}>cancel</button>}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
        {cal && (
          <Card className="gap-3 p-4">
            <p className="text-sm font-semibold">Availability · {cal.timezone}</p>
            {DAYS.map((d) => {
              const win = cal.availability?.[d] || [];
              return (
                <div key={d} className="flex items-center gap-2 text-xs">
                  <span className="w-10 font-medium capitalize">{d}</span>
                  <Input className="h-7 text-xs" defaultValue={win.map((w: string[]) => w.join("-")).join(", ")} placeholder="closed"
                    onBlur={(e) => {
                      const v = e.target.value.split(",").map((s) => s.trim()).filter(Boolean).map((s) => s.split("-").map((x) => x.trim()));
                      save.mutate({ availability: { ...cal.availability, [d]: v } });
                    }} />
                </div>
              );
            })}
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs">Slot (min)<Input className="h-7" type="number" defaultValue={cal.slot_minutes} onBlur={(e) => save.mutate({ slot_minutes: Number(e.target.value) })} /></label>
              <label className="text-xs">Buffer (min)<Input className="h-7" type="number" defaultValue={cal.buffer_minutes} onBlur={(e) => save.mutate({ buffer_minutes: Number(e.target.value) })} /></label>
            </div>
            <p className="text-[11px] text-muted-foreground">Format: 10:00-13:00, 14:00-18:00</p>
          </Card>
        )}
      </div>
    </div>
  );
}
