import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex size-7 items-center justify-center", className)}>
      <span className="absolute inset-0 rounded-full bg-[conic-gradient(from_200deg,var(--brand),oklch(0.72_0.15_200),oklch(0.75_0.16_330),var(--brand))] opacity-90" />
      <span className="absolute inset-[3px] rounded-full bg-background/90" />
      <span className="relative flex h-3 items-end gap-[2px]">
        {[0.45, 1, 0.7, 0.35].map((h, i) => (
          <span key={i} className="w-[2.5px] rounded-full bg-brand" style={{ height: `${h * 100}%` }} />
        ))}
      </span>
    </span>
  );
}

export function Logo({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <LogoMark />
      {!compact && (
        <span className="text-[17px]">
          unisona<span className="text-brand">.</span>
        </span>
      )}
    </span>
  );
}
