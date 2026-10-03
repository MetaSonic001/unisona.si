"use client";

import { Heart, Loader2, Star } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { API_URL } from "@/lib/env";
import { cn } from "@/lib/utils";

export default function ReviewPage() {
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<any>(null);
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [feedback, setFeedback] = useState("");
  const [done, setDone] = useState<null | "public" | "private">(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    fetch(`${API_URL}/public/reviews/${token}`).then((r) => r.json()).then((d) => {
      setInfo(d);
      if (d.status === "feedback") setDone("private");
      else if (d.status === "reviewed") setDone("public");
    });
  }, [token]);
  const send = async (r: number, fb = "") => {
    setBusy(true);
    const res = await (await fetch(`${API_URL}/public/reviews/${token}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rating: r, feedback: fb }) })).json();
    setBusy(false);
    if (res.happy && res.review_url) {
      setDone("public");
      window.location.href = res.review_url;
    } else setDone(res.happy ? "public" : "private");
  };
  const pick = (n: number) => {
    setRating(n);
    if (info && n >= info.threshold) send(n);
  };
  if (!info) return <div className="grid min-h-screen place-items-center"><Loader2 className="size-5 animate-spin" /></div>;
  const color = info.color || "#6D5EF8";
  return (
    <div className="grid min-h-screen place-items-center bg-gradient-to-b from-muted/50 to-background px-4">
      <Card className="w-full max-w-md items-center gap-5 p-8 text-center">
        {info.logo && <img src={info.logo} alt="" className="h-10" />}
        {done === "private" ? (
          <>
            <Heart className="size-10" style={{ color }} />
            <p className="text-lg font-semibold">Thank you for telling us.</p>
            <p className="text-sm text-muted-foreground">{info.business} will look into this personally and get back to you.</p>
          </>
        ) : done === "public" ? (
          <p className="text-lg font-semibold">Thank you! Taking you to leave a review…</p>
        ) : (
          <>
            <div>
              <p className="text-sm text-muted-foreground">{info.business}</p>
              <h1 className="mt-1 text-2xl font-semibold">How was your experience?</h1>
            </div>
            <div className="flex gap-1.5" onMouseLeave={() => setHover(0)}>
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} onMouseEnter={() => setHover(n)} onClick={() => pick(n)} aria-label={`${n} stars`} disabled={busy}>
                  <Star className={cn("size-11 transition", (hover || rating) >= n ? "fill-current" : "text-muted-foreground/40")} style={(hover || rating) >= n ? { color } : undefined} />
                </button>
              ))}
            </div>
            {rating > 0 && rating < info.threshold && (
              <div className="w-full space-y-3 text-left">
                <p className="text-sm">We&apos;re sorry it wasn&apos;t great. What went wrong? Your message goes straight to the team.</p>
                <Textarea rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
                <Button className="w-full text-white" style={{ background: color }} disabled={busy} onClick={() => send(rating, feedback)}>{busy ? <Loader2 className="size-4 animate-spin" /> : "Send privately"}</Button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
