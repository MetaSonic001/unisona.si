"use client";

import { MailX } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { API_URL } from "@/lib/env";

export default function UnsubscribePage() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<"ask" | "done" | "error">("ask");
  const [biz, setBiz] = useState("");
  const confirm = async () => {
    const r = await fetch(`${API_URL}/public/unsubscribe/${token}`, { method: "POST" });
    if (!r.ok) return setState("error");
    setBiz((await r.json()).business);
    setState("done");
  };
  return (
    <div className="grid min-h-screen place-items-center bg-muted/40 px-4">
      <Card className="w-full max-w-sm items-center gap-4 p-8 text-center">
        <MailX className="size-9 text-muted-foreground" />
        {state === "ask" && <><p className="font-semibold">Unsubscribe from these emails?</p><Button onClick={confirm}>Yes, unsubscribe me</Button></>}
        {state === "done" && <p className="text-sm">You won&apos;t receive marketing messages from {biz} any more.</p>}
        {state === "error" && <p className="text-sm text-destructive">This link is invalid or expired.</p>}
      </Card>
    </div>
  );
}
