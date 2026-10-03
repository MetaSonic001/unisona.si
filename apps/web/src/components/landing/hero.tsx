"use client";

import { ArrowRight, Globe, Mail, MessageCircle, Phone, Play, Send, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { VoiceOrb } from "@/components/orb";
import { Button } from "@/components/ui/button";

const ORBIT = [
  { icon: Phone, label: "Phone", color: "text-ch-phone", angle: -150 },
  { icon: MessageCircle, label: "WhatsApp", color: "text-ch-whatsapp", angle: -30 },
  { icon: Globe, label: "Website", color: "text-ch-web", angle: 30 },
  { icon: Send, label: "Telegram", color: "text-ch-telegram", angle: 150 },
  { icon: Sparkles, label: "Widget", color: "text-ch-voice", angle: 90 },
  { icon: Mail, label: "Email", color: "text-ch-email", angle: -90 },
];
const LINES = [
  "Hi Rahul, welcome back! Is the tooth feeling better since your WhatsApp message?",
  "नमस्ते! रविवार को क्लिनिक बंद रहता है, पर इमरजेंसी लाइन 24x7 खुली है।",
  "Order SK10231 shipped with Delhivery. It should reach you by Sunday.",
  "I've sent the booking link to your WhatsApp. Anything else I can help with?",
];

export function Hero() {
  const [line, setLine] = useState(0);
  const [level, setLevel] = useState(0.2);
  useEffect(() => {
    const t = setInterval(() => setLine((l) => (l + 1) % LINES.length), 3800);
    const a = setInterval(() => setLevel(0.15 + Math.random() * 0.55), 160);
    return () => {
      clearInterval(t);
      clearInterval(a);
    };
  }, []);

  return (
    <section className="relative overflow-hidden pt-28 pb-16 sm:pt-36">
      <div className="absolute inset-0 -z-10 bg-grid mask-radial opacity-60" />
      <div className="absolute left-1/2 top-24 -z-10 h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-brand/15 blur-[120px]" />
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 lg:grid-cols-[1.1fr_1fr]">
        <div>
          <motion.a
            href="#memory"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 rounded-full border bg-background/70 px-3 py-1 text-xs text-muted-foreground backdrop-blur"
          >
            <span className="size-1.5 rounded-full bg-success" /> One brain · every channel · shared memory
            <ArrowRight className="size-3" />
          </motion.a>
          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="mt-6 font-display text-5xl leading-[1.02] tracking-tight sm:text-6xl lg:text-[4.4rem]"
          >
            One AI agent.
            <br />
            <span className="bg-gradient-to-r from-brand via-[oklch(0.62_0.2_300)] to-[oklch(0.68_0.16_230)] bg-clip-text pr-1 italic text-transparent">Every voice</span> your
            <br /> customers use.
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="mt-6 max-w-xl text-lg text-muted-foreground">
            Build an agent from your website and documents in minutes. It answers phone calls, WhatsApp, Telegram, web chat and your site&apos;s
            widget, remembers every customer across all of them, and hands off to your team the moment it should.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }} className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg" className="h-11 bg-brand px-6 text-brand-foreground hover:bg-brand/90">
              <Link href="/sign-up">
                Build your agent free <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="h-11 px-6">
              <a href="#product">
                <Play className="size-4" /> See how it works
              </a>
            </Button>
          </motion.div>
          <p className="mt-5 text-xs text-muted-foreground">
            Free plan · bring your own AI keys · 25+ languages including हिन्दी, தமிழ், తెలుగు, বাংলা, मराठी
          </p>
        </div>

        <div className="relative mx-auto aspect-square w-full max-w-[460px]">
          <div className="absolute inset-[12%] rounded-full border border-dashed border-brand/20" />
          <div className="absolute inset-[2%] rounded-full border border-dashed border-border" />
          <div className="absolute inset-0 grid place-items-center">
            <VoiceOrb level={level} state="speaking" size={230} />
          </div>
          {ORBIT.map(({ icon: Icon, label, color, angle }, i) => {
            const r = 47;
            const x = 50 + r * Math.cos((angle * Math.PI) / 180);
            const y = 50 + r * Math.sin((angle * Math.PI) / 180);
            return (
              <motion.div
                key={label}
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.3 + i * 0.08 }}
                className="absolute -translate-x-1/2 -translate-y-1/2"
                style={{ left: `${x}%`, top: `${y}%` }}
              >
                <div className="flex items-center gap-1.5 rounded-full border bg-background/90 px-2.5 py-1.5 text-xs font-medium shadow-sm backdrop-blur animate-float" style={{ animationDelay: `${i * 0.7}s` }}>
                  <Icon className={`size-3.5 ${color}`} /> {label}
                </div>
              </motion.div>
            );
          })}
          <motion.div
            key={line}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="absolute bottom-2 left-1/2 w-[92%] -translate-x-1/2 rounded-2xl border bg-background/90 p-3 text-sm shadow-lg backdrop-blur"
          >
            <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
              <span className="size-1.5 animate-pulse rounded-full bg-brand" /> Agent speaking
            </div>
            {LINES[line]}
          </motion.div>
        </div>
      </div>
    </section>
  );
}
