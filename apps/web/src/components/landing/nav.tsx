"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Logo } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "#product", label: "Product" },
  { href: "#memory", label: "Memory" },
  { href: "#glass-box", label: "Glass box" },
  { href: "#compare", label: "Compare" },
  { href: "#pricing", label: "Pricing" },
];

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 12);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className={cn("fixed inset-x-0 top-0 z-50 transition-all", scrolled ? "border-b bg-background/75 backdrop-blur-xl" : "bg-transparent")}>
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Link href="/" aria-label="Unisona home">
          <Logo />
        </Link>
        <nav className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition hover:bg-accent hover:text-foreground">
              {l.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/sign-in">Sign in</Link>
          </Button>
          <Button asChild size="sm" className="bg-brand text-brand-foreground hover:bg-brand/90">
            <Link href="/sign-up">Start free</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
