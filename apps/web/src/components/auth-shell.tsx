"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/brand";
import { VoiceOrb } from "@/components/orb";
import { Button } from "@/components/ui/button";
import { DEV_MODE_ENABLED, setDevSession } from "@/lib/env";

export function AuthShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-foreground text-background lg:flex lg:flex-col lg:justify-between lg:p-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,color-mix(in_oklch,var(--brand)_50%,transparent),transparent_60%)]" />
        <Link href="/" className="relative">
          <Logo className="text-background" />
        </Link>
        <div className="relative mx-auto">
          <VoiceOrb state="speaking" level={0.35} size={260} />
        </div>
        <div className="relative">
          <p className="font-display text-3xl leading-tight">“The caller who chatted on our website at 2 PM was greeted by name when she called at 4.”</p>
          <p className="mt-3 text-sm text-background/60">One brain, many voices: shared memory across every channel.</p>
        </div>
      </div>
      <div className="flex flex-col items-center justify-center gap-6 p-6">
        <Link href="/" className="lg:hidden">
          <Logo />
        </Link>
        {children}
        {DEV_MODE_ENABLED && (
          <div className="w-full max-w-sm rounded-xl border border-dashed p-4 text-center">
            <p className="text-xs text-muted-foreground">Local development only. Skips Clerk and signs you into a dev workspace.</p>
            <Button
              variant="outline"
              className="mt-3 w-full"
              onClick={() => {
                setDevSession(true);
                router.push("/app");
              }}
            >
              <FlaskConical className="size-4" /> Continue in dev mode
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
