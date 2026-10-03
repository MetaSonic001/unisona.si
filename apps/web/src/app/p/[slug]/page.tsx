"use client";

import { ChevronDown, Quote } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PublicForm } from "@/components/public-form";
import { Button } from "@/components/ui/button";
import { API_URL } from "@/lib/env";

function useWidget(publicKey?: string) {
  useEffect(() => {
    if (!publicKey || document.querySelector("script[data-agent]")) return;
    const s = document.createElement("script");
    s.src = `${API_URL}/widget/widget.js`;
    s.dataset.agent = publicKey;
    s.dataset.api = API_URL;
    s.async = true;
    document.body.appendChild(s);
  }, [publicKey]);
}

export default function LandingPage() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<any>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => { fetch(`${API_URL}/public/pages/${slug}`).then(async (r) => (r.ok ? setPage(await r.json()) : setMissing(true))); }, [slug]);
  const chat = page?.blocks?.find((b: any) => b.type === "chat");
  useWidget(chat?.props?.public_key);
  useEffect(() => { if (page?.seo?.title) document.title = page.seo.title; }, [page]);
  if (missing) return <p className="p-20 text-center text-muted-foreground">This page isn&apos;t published.</p>;
  if (!page) return null;
  const color = page.theme?.color || page.brand?.primary_color || "#6D5EF8";
  const scrollTo = () => document.getElementById("convert")?.scrollIntoView({ behavior: "smooth" });

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-5">
        {page.brand?.logo_url ? <img src={page.brand.logo_url} alt="" className="h-8" /> : <span className="grid size-8 place-items-center rounded-lg font-bold text-white" style={{ background: color }}>{page.brand?.name?.[0]}</span>}
        <span className="font-semibold">{page.brand?.name}</span>
        <Button size="sm" className="ml-auto text-white" style={{ background: color }} onClick={scrollTo}>Contact us</Button>
      </header>
      {page.blocks.map((b: any, i: number) => {
        const p = b.props || {};
        switch (b.type) {
          case "hero":
            return (
              <section key={i} className="relative overflow-hidden px-6 py-24 text-center">
                <div className="pointer-events-none absolute inset-0 opacity-15" style={{ background: `radial-gradient(60% 60% at 50% 0%, ${color}, transparent)` }} />
                <div className="relative mx-auto max-w-3xl">
                  {p.eyebrow && <p className="mb-3 text-sm font-semibold uppercase tracking-wider" style={{ color }}>{p.eyebrow}</p>}
                  <h1 className="font-display text-5xl leading-tight md:text-6xl">{p.title}</h1>
                  {p.subtitle && <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">{p.subtitle}</p>}
                  {p.cta && <Button size="lg" className="mt-8 text-white" style={{ background: color }} onClick={scrollTo}>{p.cta}</Button>}
                </div>
              </section>
            );
          case "features":
            return (
              <section key={i} className="mx-auto max-w-6xl px-6 py-16">
                {p.title && <h2 className="mb-10 text-center font-display text-4xl">{p.title}</h2>}
                <div className="grid gap-5 md:grid-cols-3">
                  {(p.items || []).map((it: any, j: number) => (
                    <div key={j} className="rounded-2xl border p-6">
                      <span className="mb-3 block h-1 w-10 rounded-full" style={{ background: color }} />
                      <p className="font-semibold">{it.title}</p>
                      <p className="mt-1.5 text-sm text-muted-foreground">{it.text}</p>
                    </div>
                  ))}
                </div>
              </section>
            );
          case "text":
            return (
              <section key={i} className="mx-auto max-w-3xl px-6 py-14">
                {p.title && <h2 className="mb-4 font-display text-3xl">{p.title}</h2>}
                <p className="whitespace-pre-line text-muted-foreground">{p.body}</p>
              </section>
            );
          case "testimonials":
            return (
              <section key={i} className="bg-muted/40 px-6 py-16">
                <div className="mx-auto max-w-5xl">
                  {p.title && <h2 className="mb-10 text-center font-display text-4xl">{p.title}</h2>}
                  <div className="grid gap-5 md:grid-cols-3">
                    {(p.items || []).map((it: any, j: number) => (
                      <figure key={j} className="rounded-2xl bg-background p-6 shadow-sm">
                        <Quote className="mb-3 size-5" style={{ color }} />
                        <blockquote className="text-sm">{it.quote}</blockquote>
                        <figcaption className="mt-3 text-xs font-semibold text-muted-foreground">{it.name}</figcaption>
                      </figure>
                    ))}
                  </div>
                </div>
              </section>
            );
          case "faq":
            return (
              <section key={i} className="mx-auto max-w-3xl px-6 py-16">
                {p.title && <h2 className="mb-8 text-center font-display text-4xl">{p.title}</h2>}
                {(p.items || []).map((it: any, j: number) => (
                  <details key={j} className="group border-b py-4">
                    <summary className="flex cursor-pointer list-none items-center justify-between font-medium">{it.q}<ChevronDown className="size-4 transition group-open:rotate-180" /></summary>
                    <p className="mt-2 text-sm text-muted-foreground">{it.a}</p>
                  </details>
                ))}
              </section>
            );
          case "form":
            return page.form_slugs?.[p.form_id] ? (
              <section key={i} id="convert" className="mx-auto max-w-lg px-6 py-16">
                {p.title && <h2 className="mb-6 text-center font-display text-3xl">{p.title}</h2>}
                <div className="rounded-2xl border p-6 shadow-sm"><PublicForm slug={page.form_slugs[p.form_id]} /></div>
              </section>
            ) : null;
          case "booking":
            return p.slug ? (
              <section key={i} id={page.blocks.some((x: any) => x.type === "form") ? undefined : "convert"} className="mx-auto max-w-3xl px-6 py-16 text-center">
                {p.title && <h2 className="mb-4 font-display text-3xl">{p.title}</h2>}
                <iframe src={`/book/${p.slug}`} className="h-[640px] w-full rounded-2xl border" loading="lazy" title="Booking" />
              </section>
            ) : null;
          case "cta":
            return (
              <section key={i} className="px-6 py-16">
                <div className="mx-auto max-w-4xl rounded-3xl px-8 py-14 text-center text-white" style={{ background: color }}>
                  <h2 className="font-display text-4xl">{p.title}</h2>
                  {p.subtitle && <p className="mx-auto mt-3 max-w-xl opacity-90">{p.subtitle}</p>}
                  {p.button && <Button size="lg" variant="secondary" className="mt-6" onClick={scrollTo}>{p.button}</Button>}
                </div>
              </section>
            );
          default:
            return null;
        }
      })}
      <footer className="border-t px-6 py-8 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} {page.brand?.name}
        {!page.brand?.hide_powered_by && <> · Built with <Link href="/" className="underline">Unisona</Link></>}
      </footer>
    </div>
  );
}
