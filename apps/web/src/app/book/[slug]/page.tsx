"use client";

import { format } from "date-fns";
import { CalendarCheck } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { API_URL } from "@/lib/env";
import { cn } from "@/lib/utils";

export default function BookingPage() {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<any>(null);
  const [day, setDay] = useState(0);
  const [slot, setSlot] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", phone: "", email: "", notes: "" });
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { fetch(`${API_URL}/public/booking/${slug}`).then((r) => r.json()).then(setData); }, [slug]);
  const book = async () => {
    setErr(null);
    const r = await fetch(`${API_URL}/public/booking/${slug}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ start: slot, ...form }) });
    const j = await r.json();
    if (!r.ok) return setErr(j.detail || "Could not book");
    setDone(j.start);
  };
  if (!data) return <div className="grid min-h-screen place-items-center text-muted-foreground">Loading…</div>;
  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-soft/40 to-background px-4 py-12">
      <Card className="mx-auto max-w-2xl gap-5 p-6">
        <div>
          <p className="text-sm text-muted-foreground">{data.business}</p>
          <h1 className="font-display text-3xl">{data.calendar.name}</h1>
          <p className="text-sm text-muted-foreground">{data.calendar.description} · {data.calendar.slot_minutes} min · {data.calendar.timezone}</p>
        </div>
        {done ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <CalendarCheck className="size-10 text-success" />
            <p className="text-lg font-semibold">You&apos;re booked!</p>
            <p className="text-muted-foreground">{format(new Date(done), "EEEE d MMMM, HH:mm")}</p>
          </div>
        ) : (
          <>
            <div className="flex gap-2 overflow-x-auto">
              {data.days.map((d: any, i: number) => (
                <button key={d.date} onClick={() => { setDay(i); setSlot(null); }} className={cn("min-w-20 rounded-lg border p-2 text-center text-sm", day === i ? "border-brand bg-brand-soft" : "hover:bg-muted", !d.slots.length && "opacity-40")}>
                  <p className="text-xs text-muted-foreground">{format(new Date(d.date), "EEE")}</p><p className="font-semibold">{format(new Date(d.date), "d MMM")}</p>
                </button>
              ))}
            </div>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {data.days[day].slots.map((s: string) => (
                <button key={s} onClick={() => setSlot(s)} className={cn("rounded-md border py-2 text-sm", slot === s ? "border-brand bg-brand text-brand-foreground" : "hover:bg-muted")}>{s.slice(11, 16)}</button>
              ))}
              {data.days[day].slots.length === 0 && <p className="col-span-full text-sm text-muted-foreground">No free slots this day.</p>}
            </div>
            {slot && (
              <div className="space-y-2">
                <Input placeholder="Your name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                <div className="grid grid-cols-2 gap-2">
                  <Input placeholder="Phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
                  <Input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <Input placeholder="Anything we should know?" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                {err && <p className="text-sm text-destructive">{err}</p>}
                <Button className="w-full bg-brand text-brand-foreground hover:bg-brand/90" disabled={!form.name || !(form.phone || form.email)} onClick={book}>Confirm {slot.slice(11, 16)}</Button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
