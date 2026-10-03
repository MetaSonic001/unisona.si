import { formatDistanceToNowStrict } from "date-fns";
import { Globe, Mail, MessageCircle, Mic, Phone, Send, Sparkles, SquareTerminal, type LucideIcon } from "lucide-react";

export function timeAgo(iso?: string | null) {
  if (!iso) return "";
  try {
    return formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
  } catch {
    return "";
  }
}

export function duration(seconds?: number | null) {
  if (!seconds && seconds !== 0) return "—";
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  return m ? `${m}m ${s % 60}s` : `${s}s`;
}

export function initials(name?: string | null) {
  if (!name) return "?";
  return name.split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
}

export const CHANNELS: Record<string, { label: string; icon: LucideIcon; color: string; bg: string }> = {
  voice: { label: "Voice", icon: Mic, color: "text-ch-voice", bg: "bg-ch-voice/10" },
  phone: { label: "Phone", icon: Phone, color: "text-ch-phone", bg: "bg-ch-phone/10" },
  web: { label: "Web chat", icon: Globe, color: "text-ch-web", bg: "bg-ch-web/10" },
  widget: { label: "Widget", icon: Sparkles, color: "text-ch-web", bg: "bg-ch-web/10" },
  whatsapp: { label: "WhatsApp", icon: MessageCircle, color: "text-ch-whatsapp", bg: "bg-ch-whatsapp/10" },
  telegram: { label: "Telegram", icon: Send, color: "text-ch-telegram", bg: "bg-ch-telegram/10" },
  email: { label: "Email", icon: Mail, color: "text-ch-email", bg: "bg-ch-email/10" },
  playground: { label: "Playground", icon: SquareTerminal, color: "text-muted-foreground", bg: "bg-muted" },
  booking: { label: "Booking", icon: Globe, color: "text-ch-web", bg: "bg-ch-web/10" },
  manual: { label: "Manual", icon: Sparkles, color: "text-muted-foreground", bg: "bg-muted" },
  import: { label: "Import", icon: Sparkles, color: "text-muted-foreground", bg: "bg-muted" },
};

export const channelMeta = (c?: string | null) => CHANNELS[c || "web"] || CHANNELS.web;

export function money(v: number, currency = "INR") {
  try {
    return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(v);
  } catch {
    return `${currency} ${v}`;
  }
}

export function pct(v?: number | null) {
  return v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;
}
