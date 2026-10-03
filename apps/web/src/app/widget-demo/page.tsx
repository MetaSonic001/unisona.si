"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { API_URL } from "@/lib/env";

function Demo() {
  const key = useSearchParams().get("key");
  useEffect(() => {
    if (!key || document.querySelector("script[data-agent]")) return;
    const s = document.createElement("script");
    s.src = `${API_URL}/widget/widget.js?v=${Date.now()}`;
    s.dataset.agent = key;
    s.dataset.api = API_URL;
    s.async = true;
    document.body.appendChild(s);
  }, [key]);
  return (
    <div className="min-h-screen bg-[linear-gradient(135deg,#fdf4ff,#eff6ff)] p-10">
      <div className="mx-auto max-w-3xl rounded-2xl bg-white p-10 shadow-xl">
        <p className="text-sm text-muted-foreground">Example customer website</p>
        <h1 className="mt-2 text-4xl font-bold">BrightSmile Dental Clinic</h1>
        <p className="mt-4 text-muted-foreground">This page simulates your website. The Unisona widget is embedded with a single script tag. Click the bubble at the bottom right to chat or talk.</p>
        {!key && <p className="mt-6 text-destructive">Add ?key=pk_… (the agent&apos;s public key from its Channels tab) to the URL.</p>}
        <pre className="mt-6 overflow-x-auto rounded-lg bg-muted p-4 text-xs">{`<script src="${API_URL}/widget/widget.js" data-agent="${key || "pk_..."}" data-api="${API_URL}" async></script>`}</pre>
      </div>
    </div>
  );
}

export default function WidgetDemo() {
  return <Suspense><Demo /></Suspense>;
}
