"use client";

import { SignIn } from "@clerk/nextjs";
import { AuthShell } from "@/components/auth-shell";
import { CLERK_ENABLED } from "@/lib/env";

export default function Page() {
  return <AuthShell>{CLERK_ENABLED ? <SignIn /> : <p className="text-sm text-muted-foreground">Clerk is not configured. Add the Clerk keys to .env.</p>}</AuthShell>;
}
