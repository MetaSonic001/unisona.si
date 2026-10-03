"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { PublicForm } from "@/components/public-form";
import { Card } from "@/components/ui/card";
import { API_URL } from "@/lib/env";

function Page() {
  const { slug } = useParams<{ slug: string }>();
  const embed = useSearchParams().get("embed") === "1";
  const [meta, setMeta] = useState<any>(null);
  useEffect(() => { fetch(`${API_URL}/public/forms/${slug}`).then((r) => r.json()).then(setMeta).catch(() => {}); }, [slug]);
  if (embed) return <div className="p-3"><PublicForm slug={slug} embedded /></div>;
  return (
    <div className="min-h-screen bg-gradient-to-b from-muted/50 to-background px-4 py-12">
      <Card className="mx-auto max-w-lg gap-5 p-6">
        <div>
          {meta?.brand?.logo_url && <img src={meta.brand.logo_url} alt="" className="mb-3 h-8" />}
          <p className="text-sm text-muted-foreground">{meta?.brand?.name}</p>
          <h1 className="font-display text-3xl">{meta?.name}</h1>
        </div>
        <PublicForm slug={slug} />
      </Card>
      {!meta?.brand?.hide_powered_by && <p className="mt-6 text-center text-[11px] text-muted-foreground">Powered by Unisona</p>}
    </div>
  );
}

export default function FormPage() {
  return <Suspense><Page /></Suspense>;
}
