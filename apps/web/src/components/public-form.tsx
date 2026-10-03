"use client";

import { CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { API_URL } from "@/lib/env";
import { cn } from "@/lib/utils";

export function PublicForm({ slug, embedded = false }: { slug: string; embedded?: boolean }) {
  const [form, setForm] = useState<any>(null);
  const [data, setData] = useState<Record<string, any>>({});
  const [hp, setHp] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [err, setErr] = useState<string | null>(null);
  const [thanks, setThanks] = useState("");
  useEffect(() => { fetch(`${API_URL}/public/forms/${slug}`).then(async (r) => (r.ok ? setForm(await r.json()) : setErr("This form is not available."))); }, [slug]);
  const submit = async () => {
    setState("sending");
    setErr(null);
    const r = await fetch(`${API_URL}/public/forms/${slug}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ data, _hp: hp }) });
    const j = await r.json();
    if (!r.ok) {
      setErr(j.detail || "Please check the form");
      setState("idle");
      return;
    }
    if (j.redirect_url) window.location.href = j.redirect_url;
    setThanks(j.thank_you || "Thank you!");
    setState("done");
  };
  if (err && !form) return <p className="p-10 text-center text-muted-foreground">{err}</p>;
  if (!form) return <div className="grid min-h-[300px] place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>;
  const color = form.brand?.primary_color || "#6D5EF8";
  if (state === "done")
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <CheckCircle2 className="size-12" style={{ color }} />
        <p className="text-lg font-semibold">{thanks}</p>
      </div>
    );
  return (
    <div className={cn("space-y-4", embedded && "p-1")}>
      {form.fields.map((f: any) => {
        const v = data[f.id];
        const set = (x: any) => setData({ ...data, [f.id]: x });
        return (
          <div key={f.id} className="space-y-1.5">
            {f.type !== "checkbox" && <Label className="text-sm">{f.label}{f.required && <span className="text-destructive"> *</span>}</Label>}
            {f.type === "textarea" ? <Textarea rows={3} value={v || ""} onChange={(e) => set(e.target.value)} />
              : f.type === "select" ? (
                <select className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={v || ""} onChange={(e) => set(e.target.value)}>
                  <option value="">Choose…</option>{(f.options || []).map((o: string) => <option key={o}>{o}</option>)}
                </select>)
              : f.type === "radio" ? (
                <div className="flex flex-wrap gap-2">{(f.options || []).map((o: string) => (
                  <button key={o} type="button" onClick={() => set(o)} className={cn("rounded-full border px-3 py-1.5 text-sm", v === o ? "text-white" : "hover:bg-muted")} style={v === o ? { background: color, borderColor: color } : undefined}>{o}</button>))}</div>)
              : f.type === "checkbox" ? (
                <label className="flex items-start gap-2 text-sm"><Checkbox checked={!!v} onCheckedChange={(x) => set(!!x)} /> <span>{f.label}{f.required && <span className="text-destructive"> *</span>}</span></label>)
              : f.type === "nps" || f.type === "rating" ? (
                <div className="flex flex-wrap gap-1.5">{Array.from({ length: f.type === "nps" ? 11 : 5 }, (_, i) => (f.type === "nps" ? i : i + 1)).map((n) => (
                  <button key={n} type="button" onClick={() => set(n)} className={cn("grid size-10 place-items-center rounded-lg border text-sm font-medium", v === n ? "text-white" : "hover:bg-muted")} style={v === n ? { background: color, borderColor: color } : undefined}>
                    {f.type === "rating" ? "★" : n}</button>))}
                  {f.type === "nps" && <div className="flex w-full justify-between text-[11px] text-muted-foreground"><span>Not likely</span><span>Very likely</span></div>}
                </div>)
              : <Input type={f.type === "email" ? "email" : f.type === "phone" ? "tel" : f.type === "number" ? "number" : f.type === "date" ? "date" : "text"} value={v || ""} onChange={(e) => set(e.target.value)} />}
          </div>
        );
      })}
      <input className="hidden" tabIndex={-1} autoComplete="off" value={hp} onChange={(e) => setHp(e.target.value)} aria-hidden />
      {err && <p className="text-sm text-destructive">{err}</p>}
      <Button className="w-full text-white" style={{ background: color }} disabled={state === "sending"} onClick={submit}>
        {state === "sending" ? <Loader2 className="size-4 animate-spin" /> : "Submit"}
      </Button>
    </div>
  );
}
