"use client";

import { Plus, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export function Field({ label, hint, children, className }: { label: string; hint?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label className="text-xs font-medium">{label}</Label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function TextField({ label, hint, value, onChange, placeholder, type }: { label: string; hint?: string; value?: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <Field label={label} hint={hint}>
      <Input type={type} value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

export function AreaField({ label, hint, value, onChange, placeholder, rows = 4 }: { label: string; hint?: string; value?: string; onChange: (v: string) => void; placeholder?: string; rows?: number }) {
  return (
    <Field label={label} hint={hint}>
      <Textarea rows={rows} value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

export function SwitchRow({ label, hint, checked, onChange }: { label: string; hint?: string; checked?: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <Switch checked={!!checked} onCheckedChange={onChange} />
    </div>
  );
}

export function SliderField({ label, value, onChange, min = 0, max = 100, step = 1, left, right, format }: {
  label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number; left?: string; right?: string; format?: (v: number) => string;
}) {
  return (
    <Field label={`${label}${format ? `: ${format(value)}` : ""}`}>
      <Slider value={[value]} min={min} max={max} step={step} onValueChange={([v]) => onChange(v)} className="py-2" />
      {(left || right) && (
        <div className="flex justify-between text-[11px] text-muted-foreground">
          <span>{left}</span>
          <span>{right}</span>
        </div>
      )}
    </Field>
  );
}

export function ListField({ label, hint, values, onChange, placeholder }: { label: string; hint?: string; values: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  };
  return (
    <Field label={label} hint={hint}>
      <div className="space-y-1.5">
        {values.map((v, i) => (
          <div key={i} className="flex items-center gap-2 rounded-md border bg-muted/30 px-2.5 py-1.5 text-sm">
            <span className="flex-1">{v}</span>
            <button onClick={() => onChange(values.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-destructive" aria-label="Remove">
              <X className="size-3.5" />
            </button>
          </div>
        ))}
        <div className="flex gap-2">
          <Input value={draft} placeholder={placeholder} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())} />
          <Button type="button" variant="outline" size="icon" onClick={add} aria-label="Add">
            <Plus className="size-4" />
          </Button>
        </div>
      </div>
    </Field>
  );
}

export function ChipToggle({ options, value, onChange }: { options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button
            type="button"
            key={o.value}
            onClick={() => onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])}
            className={cn("rounded-full border px-3 py-1 text-xs transition", on ? "border-brand bg-brand-soft text-brand" : "text-muted-foreground hover:bg-muted")}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
