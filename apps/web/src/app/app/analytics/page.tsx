"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Bot, Clock, Coins, Handshake, MessagesSquare, PhoneCall, Smile } from "lucide-react";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, XAxis, YAxis } from "recharts";
import { LoadingBlock, PageHeader, StatCard } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { useApi } from "@/lib/api";
import { money, pct } from "@/lib/format";

const CH = ["voice", "phone", "web", "widget", "whatsapp", "telegram", "email"];
const COLOR: Record<string, string> = { voice: "var(--ch-voice)", phone: "var(--ch-phone)", web: "var(--ch-web)", widget: "oklch(0.7 0.13 250)", whatsapp: "var(--ch-whatsapp)", telegram: "var(--ch-telegram)", email: "var(--ch-email)" };

export default function AnalyticsPage() {
  const api = useApi();
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({ queryKey: ["analytics", days], queryFn: () => api.get(`/analytics/overview?days=${days}`) });
  const k = data?.kpis;
  const config = Object.fromEntries(CH.map((c) => [c, { label: c, color: COLOR[c] }]));
  const sentiment = Object.entries(k?.sentiment || {}).map(([name, value]) => ({ name, value }));
  const outcomes = Object.entries(k?.outcomes || {}).map(([name, value]) => ({ name: name.replaceAll("_", " "), value })).sort((a: any, b: any) => b.value - a.value).slice(0, 8);

  return (
    <div>
      <PageHeader icon={BarChart3} title="Analytics" description="Every channel, one view: volume, resolution, quality, speed and cost."
        actions={[7, 30, 90].map((d) => <Button key={d} size="sm" variant={days === d ? "default" : "ghost"} onClick={() => setDays(d)}>{d}d</Button>)} />
      {isLoading || !k ? <LoadingBlock /> : (
        <div className="space-y-6 p-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-8">
            <StatCard label="Conversations" value={k.conversations} icon={MessagesSquare} />
            <StatCard label="AI replies" value={k.ai_messages} icon={Bot} />
            <StatCard label="Resolved by AI" value={pct(k.containment_rate)} icon={Bot} />
            <StatCard label="Handoffs" value={k.handoffs} icon={Handshake} />
            <StatCard label="Calls" value={k.calls} hint={`${k.call_minutes} min`} icon={PhoneCall} />
            <StatCard label="Avg reply" value={k.avg_response_ms ? `${(k.avg_response_ms / 1000).toFixed(1)}s` : "—"} icon={Clock} />
            <StatCard label="CSAT" value={k.csat ? `${k.csat}/5` : "—"} icon={Smile} hint={`👍 ${k.thumbs_up} · 👎 ${k.thumbs_down}`} />
            <StatCard label="Provider spend" value={`$${k.llm_cost_usd}`} icon={Coins} hint={`${(k.llm_tokens / 1000).toFixed(1)}k tokens`} />
          </div>
          <div className="grid gap-6 xl:grid-cols-3">
            <Card className="gap-3 p-5 xl:col-span-2">
              <p className="text-sm font-semibold">Conversations by channel</p>
              <ChartContainer config={config} className="h-64 w-full">
                <AreaChart data={data.series}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickLine={false} axisLine={false} fontSize={11} />
                  <YAxis tickLine={false} axisLine={false} fontSize={11} allowDecimals={false} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  {CH.map((c) => <Area key={c} dataKey={c} stackId="1" type="monotone" stroke={COLOR[c]} fill={COLOR[c]} fillOpacity={0.35} />)}
                </AreaChart>
              </ChartContainer>
            </Card>
            <Card className="gap-3 p-5">
              <p className="text-sm font-semibold">Sentiment</p>
              <ChartContainer config={{ positive: { label: "positive", color: "var(--success)" }, neutral: { label: "neutral", color: "var(--muted-foreground)" }, negative: { label: "negative", color: "var(--destructive)" } }} className="h-64 w-full">
                <PieChart>
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Pie data={sentiment} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                    {sentiment.map((s: any) => <Cell key={s.name} fill={s.name === "positive" ? "var(--success)" : s.name === "negative" ? "var(--destructive)" : "var(--muted-foreground)"} />)}
                  </Pie>
                </PieChart>
              </ChartContainer>
            </Card>
          </div>
          <div className="grid gap-6 xl:grid-cols-3">
            <Card className="gap-3 p-5">
              <p className="text-sm font-semibold">Outcomes</p>
              <ChartContainer config={{ value: { label: "conversations", color: "var(--brand)" } }} className="h-64 w-full">
                <BarChart data={outcomes} layout="vertical" margin={{ left: 20 }}>
                  <XAxis type="number" hide />
                  <YAxis type="category" dataKey="name" width={120} tickLine={false} axisLine={false} fontSize={11} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="value" fill="var(--brand)" radius={4} />
                </BarChart>
              </ChartContainer>
            </Card>
            <Card className="gap-3 p-5">
              <p className="text-sm font-semibold">Top customer intents</p>
              {(data.top_intents || []).length === 0 && <p className="text-sm text-muted-foreground">Appears after conversations are analysed.</p>}
              {(data.top_intents || []).map((i: any) => (
                <div key={i.intent} className="space-y-1">
                  <div className="flex justify-between text-xs"><span>{i.intent}</span><span className="tabular-nums">{i.count}</span></div>
                  <div className="h-1.5 rounded-full bg-muted"><div className="h-full rounded-full bg-brand" style={{ width: `${(i.count / data.top_intents[0].count) * 100}%` }} /></div>
                </div>
              ))}
            </Card>
            <Card className="gap-3 p-5">
              <p className="text-sm font-semibold">CRM impact</p>
              {[["New contacts", data.crm.new_contacts], ["Open deals", data.crm.open_deals], ["Pipeline value", money(data.crm.pipeline_value)], ["Appointments booked", data.crm.appointments], ["Tasks created by AI", data.crm.ai_tasks], ["Open tasks", data.crm.open_tasks]].map(([l, v]) => (
                <div key={l as string} className="flex justify-between border-b py-1.5 text-sm last:border-0"><span className="text-muted-foreground">{l}</span><span className="font-medium tabular-nums">{v}</span></div>
              ))}
              <p className="pt-2 text-sm font-semibold">Agents</p>
              {data.agents.map((a: any) => <div key={a.id} className="flex justify-between text-xs"><span>{a.name}</span><span className="tabular-nums">{a.conversations}</span></div>)}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
