"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

type OrbState = "idle" | "connecting" | "listening" | "thinking" | "speaking";

/** The Unisona voice orb: soft gradient blobs that breathe, and swell with audio level. */
export function VoiceOrb({ level = 0, state = "idle", className, size = 220 }: { level?: number; state?: OrbState; className?: string; size?: number }) {
  const active = state === "speaking" || state === "listening";
  const scale = 1 + Math.min(level, 1) * 0.18;
  const hue = state === "speaking" ? "var(--brand)" : state === "listening" ? "oklch(0.7 0.16 200)" : state === "thinking" ? "oklch(0.75 0.15 330)" : "var(--brand)";
  return (
    <div className={cn("relative grid place-items-center", className)} style={{ width: size, height: size }}>
      {active && (
        <>
          <span className="absolute inset-0 rounded-full border border-brand/30 animate-pulse-ring" />
          <span className="absolute inset-0 rounded-full border border-brand/20 animate-pulse-ring [animation-delay:0.8s]" />
        </>
      )}
      <motion.div
        className="relative overflow-hidden rounded-full shadow-[0_30px_80px_-20px_color-mix(in_oklch,var(--brand)_55%,transparent)]"
        style={{ width: size * 0.82, height: size * 0.82 }}
        animate={{ scale }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_25%,oklch(0.92_0.06_285),transparent_55%)]" />
        <div className="absolute -left-1/4 -top-1/4 size-[90%] rounded-full blur-2xl animate-orb" style={{ background: hue, opacity: 0.85 }} />
        <div className="absolute -bottom-1/4 -right-1/4 size-[85%] rounded-full blur-2xl animate-orb [animation-delay:-3s]" style={{ background: "oklch(0.72 0.15 200)", opacity: 0.7 }} />
        <div className="absolute left-1/4 top-1/3 size-[60%] rounded-full blur-2xl animate-orb [animation-delay:-6s]" style={{ background: "oklch(0.78 0.14 340)", opacity: 0.55 }} />
        <div className="absolute inset-0 rounded-full ring-1 ring-inset ring-white/40" />
        {state === "thinking" && <div className="absolute inset-0 bg-[linear-gradient(110deg,transparent_30%,rgba(255,255,255,0.35)_50%,transparent_70%)] bg-[length:200%_100%] animate-shimmer" />}
      </motion.div>
    </div>
  );
}
