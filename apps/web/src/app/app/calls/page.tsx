"use client";

import { useQuery } from "@tanstack/react-query";
import { PhoneCall, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import Link from "next/link";
import { EmptyState, LoadingBlock, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useApi } from "@/lib/api";
import { duration, timeAgo } from "@/lib/format";

export default function CallsPage() {
  const api = useApi();
  const { data, isLoading } = useQuery({ queryKey: ["calls"], queryFn: () => api.get("/calls?limit=200") });
  return (
    <div>
      <PageHeader icon={PhoneCall} title="Calls" description="Every voice conversation with recordings, transcripts, summaries and latency." />
      <div className="p-6">
        {isLoading ? <LoadingBlock /> : (data?.items || []).length === 0 ? <EmptyState icon={PhoneCall} title="No calls yet" description="Start a browser call from an agent's Playground, the widget, or connect a phone number." /> : (
          <Card className="gap-0 overflow-x-auto p-0">
            <table className="w-full min-w-[820px] text-sm">
              <thead className="border-b bg-muted/30 text-left text-xs text-muted-foreground"><tr><th className="px-4 py-2 font-medium">Caller</th><th className="font-medium">Agent</th><th className="font-medium">Duration</th><th className="font-medium">Latency</th><th className="font-medium">Outcome</th><th className="font-medium">Summary</th><th className="pr-4 text-right font-medium">When</th></tr></thead>
              <tbody>
                {data.items.map((c: any) => (
                  <tr key={c.id} className="border-b last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5">
                      <Link href={`/app/inbox?c=${c.conversation_id}`} className="flex items-center gap-2 hover:underline">
                        {c.direction === "outbound" ? <PhoneOutgoing className="size-3.5 text-ch-phone" /> : <PhoneIncoming className="size-3.5 text-ch-voice" />}
                        {c.contact?.name || c.from_number || c.contact?.phone || "Browser visitor"}
                      </Link>
                    </td>
                    <td className="text-xs">{c.agent_name}</td>
                    <td className="tabular-nums">{duration(c.duration_s)}</td>
                    <td className="text-xs tabular-nums">{c.metrics?.avg_latency_ms ? `${c.metrics.avg_latency_ms}ms` : "—"}</td>
                    <td>{c.outcome ? <Badge variant="outline">{c.outcome.replaceAll("_", " ")}</Badge> : <Badge variant="secondary">{c.status}</Badge>}</td>
                    <td className="max-w-[320px]"><p className="truncate text-xs text-muted-foreground">{c.summary}</p></td>
                    <td className="pr-4 text-right text-xs text-muted-foreground">{timeAgo(c.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
}
