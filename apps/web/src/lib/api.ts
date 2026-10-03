"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useMemo } from "react";
import { API_URL, CLERK_ENABLED, isDevSession } from "./env";

let devTokenPromise: Promise<string> | null = null;

async function devToken(): Promise<string> {
  if (!devTokenPromise) {
    devTokenPromise = fetch("/api/dev-token").then(async (r) => {
      if (!r.ok) throw new Error("Dev mode is not available");
      return (await r.json()).token as string;
    });
  }
  return devTokenPromise;
}

/** Agency mode: the client sub-account currently being managed (sent as X-Workspace-Id; verified by the API). */
export function activeWorkspace(): string | null {
  try {
    return localStorage.getItem("unisona_workspace");
  } catch {
    return null;
  }
}

export function setActiveWorkspace(id: string | null) {
  try {
    if (id) localStorage.setItem("unisona_workspace", id);
    else localStorage.removeItem("unisona_workspace");
  } catch {}
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export type Api = ReturnType<typeof useApi>;

function useClerkToken() {
  // useAuth must only run under ClerkProvider; CLERK_ENABLED is a build-time constant so hook order is stable.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const auth = CLERK_ENABLED ? useAuth() : null;
  return auth?.getToken;
}

export function useApi() {
  const getClerkToken = useClerkToken();

  const token = useCallback(async (): Promise<string> => {
    if (isDevSession()) return devToken();
    const t = getClerkToken ? await getClerkToken() : null;
    if (!t) throw new ApiError("Not signed in", 401);
    return t;
  }, [getClerkToken]);

  const request = useCallback(
    async <T = any>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> => {
      const headers: Record<string, string> = { Authorization: `Bearer ${await token()}` };
      const wsHeader = activeWorkspace();
      if (wsHeader) headers["x-workspace-id"] = wsHeader;
      const isForm = typeof FormData !== "undefined" && body instanceof FormData;
      if (body !== undefined && !isForm) headers["content-type"] = "application/json";
      const res = await fetch(`${API_URL}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
        ...init,
      });
      if (!res.ok) {
        let msg = `Request failed (${res.status})`;
        try {
          const j = await res.json();
          msg = typeof j.detail === "string" ? j.detail : j.detail?.[0]?.msg || msg;
        } catch {}
        throw new ApiError(msg, res.status);
      }
      const ct = res.headers.get("content-type") || "";
      return (ct.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
    },
    [token],
  );

  /** POST and consume a server-sent-event stream, calling onEvent for each JSON event. */
  const stream = useCallback(
    async (path: string, body: unknown, onEvent: (ev: any) => void, signal?: AbortSignal) => {
      const res = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${await token()}`, "content-type": "application/json", ...(activeWorkspace() ? { "x-workspace-id": activeWorkspace()! } : {}) },
        body: JSON.stringify(body),
        signal,
      });
      if (!res.ok || !res.body) {
        let msg = `Request failed (${res.status})`;
        try {
          msg = (await res.json()).detail || msg;
        } catch {}
        throw new ApiError(msg, res.status);
      }
      await readSSE(res.body, onEvent);
    },
    [token],
  );

  return useMemo(
    () => ({
      token,
      get: <T = any>(p: string) => request<T>("GET", p),
      post: <T = any>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
      put: <T = any>(p: string, b?: unknown) => request<T>("PUT", p, b ?? {}),
      patch: <T = any>(p: string, b?: unknown) => request<T>("PATCH", p, b ?? {}),
      del: <T = any>(p: string) => request<T>("DELETE", p),
      upload: <T = any>(p: string, form: FormData) => request<T>("POST", p, form),
      stream,
    }),
    [request, stream, token],
  );
}

export async function readSSE(body: ReadableStream<Uint8Array>, onEvent: (ev: any) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) {
          try {
            onEvent(JSON.parse(line.slice(6)));
          } catch {}
        }
      }
    }
  }
}

export const apiUrl = (p: string) => `${API_URL}${p}`;
