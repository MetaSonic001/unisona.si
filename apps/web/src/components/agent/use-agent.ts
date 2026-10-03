"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/lib/api";

export type AgentConfig = Record<string, any>;

function setPath(obj: any, path: string, value: any) {
  const keys = path.split(".");
  const copy = structuredClone(obj);
  let cur = copy;
  for (let i = 0; i < keys.length - 1; i++) {
    cur[keys[i]] = cur[keys[i]] ?? {};
    cur = cur[keys[i]];
  }
  cur[keys[keys.length - 1]] = value;
  return copy;
}

export function getPath(obj: any, path: string) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

export function useAgent(id: string) {
  const api = useApi();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["agent", id], queryFn: () => api.get(`/agents/${id}`) });
  const [draft, setDraft] = useState<AgentConfig | null>(null);
  const [name, setName] = useState("");
  const [kbIds, setKbIds] = useState<string[] | null>(null);

  useEffect(() => {
    if (query.data && !draft) {
      setDraft(query.data.config);
      setName(query.data.name);
    }
  }, [query.data, draft]);

  const dirty = useMemo(() => {
    if (!query.data || !draft) return false;
    return JSON.stringify(draft) !== JSON.stringify(query.data.config) || name !== query.data.name || (kbIds !== null && JSON.stringify([...kbIds].sort()) !== JSON.stringify([...query.data.kb_ids].sort()));
  }, [draft, query.data, name, kbIds]);

  const set = useCallback((path: string, value: any) => setDraft((d) => (d ? setPath(d, path, value) : d)), []);

  const save = useMutation({
    mutationFn: () => api.patch(`/agents/${id}`, { config: draft, name, ...(kbIds !== null ? { kb_ids: kbIds } : {}) }),
    onSuccess: (a) => {
      qc.setQueryData(["agent", id], a);
      qc.invalidateQueries({ queryKey: ["agents"] });
      setDraft(a.config);
      setKbIds(null);
      toast.success("Draft saved", { description: "Test it in the Playground, then publish to go live." });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const publish = useMutation({
    mutationFn: async (notes?: string) => {
      if (dirty) await save.mutateAsync();
      return api.post(`/agents/${id}/publish`, { notes });
    },
    onSuccess: (a) => {
      qc.setQueryData(["agent", id], a);
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast.success(`Published version ${a.published_version}`, { description: "Customers on every channel now talk to this version." });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const refresh = () => {
    setDraft(null);
    qc.invalidateQueries({ queryKey: ["agent", id] });
  };

  return { agent: query.data, loading: query.isLoading, draft, set, name, setName, kbIds: kbIds ?? query.data?.kb_ids ?? [], setKbIds, dirty, save, publish, refresh };
}
