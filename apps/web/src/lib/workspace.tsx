"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { activeWorkspace, useApi } from "./api";
import { API_URL } from "./env";

type Me = {
  user: { id: string; email?: string; name?: string; role: string; via: string };
  workspace: { id: string; name: string; plan: string; onboarding: Record<string, any>; timezone?: string; currency?: string; llm?: any };
  counts: { agents: number; contacts: number; conversations: number; sources: number };
  providers: { provider: string; status: string }[];
  ai_ready: boolean;
  dev_mode: boolean;
};

type Listener = (ev: any) => void;
const Ctx = createContext<{ me?: Me; loading: boolean; error?: Error | null; refetch: () => void; subscribe: (l: Listener) => () => void; connected: boolean } | null>(null);

function beep() {
  try {
    const ctx = new AudioContext();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.connect(g);
    g.connect(ctx.destination);
    o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.15, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.35);
    o.start();
    o.stop(ctx.currentTime + 0.4);
  } catch {}
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const api = useApi();
  const qc = useQueryClient();
  const router = useRouter();
  const listeners = useRef(new Set<Listener>());
  const [connected, setConnected] = useState(false);
  const { data: me, isLoading, error, refetch } = useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/me") });

  const subscribe = useCallback((l: Listener) => {
    listeners.current.add(l);
    return () => listeners.current.delete(l);
  }, []);

  useEffect(() => {
    if (!me) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 1000;
    const connect = async () => {
      try {
        const token = await api.token();
        const client = activeWorkspace();
        ws = new WebSocket(`${API_URL.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(token)}${client ? `&workspace=${client}` : ""}`);
        ws.onopen = () => {
          setConnected(true);
          retry = 1000;
        };
        ws.onclose = () => {
          setConnected(false);
          if (!closed) setTimeout(connect, (retry = Math.min(retry * 2, 15000)));
        };
        ws.onmessage = (m) => {
          const ev = JSON.parse(m.data);
          if (ev.type === "ping" || ev.type === "ready") return;
          listeners.current.forEach((l) => l(ev));
          if (ev.type === "message.created" || ev.type?.startsWith("conversation.")) qc.invalidateQueries({ queryKey: ["conversations"] });
          if (ev.type?.startsWith("knowledge.")) qc.invalidateQueries({ queryKey: ["sources"] });
          if (ev.type?.startsWith("call.")) qc.invalidateQueries({ queryKey: ["live"] });
          if (ev.type === "notification") qc.invalidateQueries({ queryKey: ["notifications"] });
          if (ev.type === "handoff.requested") {
            beep();
            toast.warning("A customer needs a human", {
              description: ev.brief?.slice(0, 140) || `${ev.reason?.replaceAll("_", " ")} on ${ev.channel}`,
              duration: 15000,
              action: { label: "Open", onClick: () => router.push(`/app/inbox?c=${ev.conversation_id}`) },
            });
            if (typeof Notification !== "undefined" && Notification.permission === "granted") {
              new Notification("Unisona: human needed", { body: ev.brief?.slice(0, 120) || ev.reason });
            }
          }
        };
      } catch {
        if (!closed) setTimeout(connect, 5000);
      }
    };
    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, [me?.workspace.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return <Ctx.Provider value={{ me, loading: isLoading, error: error as Error | null, refetch, subscribe, connected }}>{children}</Ctx.Provider>;
}

export function useWorkspace() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace outside provider");
  return v;
}

export function useRealtime(handler: Listener) {
  const { subscribe } = useWorkspace();
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => subscribe((ev) => ref.current(ev)), [subscribe]);
}
