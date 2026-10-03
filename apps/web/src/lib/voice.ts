"use client";

import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { useCallback, useEffect, useRef, useState } from "react";

export type CallState = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "ended" | "error";

/** Browser voice call to an agent over WebRTC (Pipecat SmallWebRTC). */
export function useVoiceCall() {
  const clientRef = useRef<PipecatClient | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<CallState>("idle");
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);

  const stop = useCallback(async () => {
    try {
      await clientRef.current?.disconnect();
    } catch {}
    clientRef.current = null;
    if (audioRef.current) {
      audioRef.current.srcObject = null;
    }
    setState((s) => (s === "error" ? s : "ended"));
    setLevel(0);
    setStartedAt(null);
  }, []);

  const start = useCallback(
    async (opts: { endpoint: string; headers?: Record<string, string>; requestData?: Record<string, unknown> }) => {
      setError(null);
      setState("connecting");
      try {
        if (!audioRef.current) {
          audioRef.current = new Audio();
          audioRef.current.autoplay = true;
        }
        const transport = new SmallWebRTCTransport({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
        const client = new PipecatClient({
          transport,
          enableMic: true,
          enableCam: false,
          callbacks: {
            onTrackStarted: (track, participant) => {
              if (track.kind === "audio" && !participant?.local && audioRef.current) {
                audioRef.current.srcObject = new MediaStream([track]);
                audioRef.current.play().catch(() => {});
              }
            },
            onBotStartedSpeaking: () => setState("speaking"),
            onBotStoppedSpeaking: () => setState("listening"),
            onUserStartedSpeaking: () => setState("listening"),
            onUserStoppedSpeaking: () => setState("thinking"),
            onLocalAudioLevel: (l) => setLevel((prev) => (prev * 0.6 + l * 0.4)),
            onRemoteAudioLevel: (l) => setLevel((prev) => Math.max(prev * 0.7, l)),
            onDisconnected: () => {
              setState((s) => (s === "error" ? s : "ended"));
              setStartedAt(null);
            },
            onError: (m: any) => {
              setError(m?.data?.message || "Call error");
            },
          },
        });
        clientRef.current = client;
        client.on(RTVIEvent.Connected, () => {
          setState("listening");
          setStartedAt(Date.now());
        });
        await client.connect({
          webrtcRequestParams: { endpoint: opts.endpoint, headers: new Headers(opts.headers || {}), requestData: opts.requestData as any },
        } as any);
        setState((s) => (s === "connecting" ? "listening" : s));
        setStartedAt((t) => t ?? Date.now());
      } catch (e: any) {
        setError(e?.message?.includes("Permission") ? "Microphone permission was denied." : e?.message || "Could not start the call");
        setState("error");
        clientRef.current = null;
      }
    },
    [],
  );

  const toggleMute = useCallback(() => {
    const c = clientRef.current;
    if (!c) return;
    const next = !muted;
    c.enableMic(!next);
    setMuted(next);
  }, [muted]);

  useEffect(() => () => void clientRef.current?.disconnect(), []);

  const active = state === "connecting" || state === "listening" || state === "thinking" || state === "speaking";
  return { state, level, error, active, muted, startedAt, start, stop, toggleMute };
}
