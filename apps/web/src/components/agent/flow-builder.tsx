"use client";

import { addEdge, Background, Controls, Handle, MiniMap, Position, ReactFlow, useEdgesState, useNodesState, type Connection, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Flag, GitBranch, PhoneForwarded, Plus, Square, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AreaField, Field, SwitchRow, TextField } from "@/components/agent/fields";
import { Section } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

type FlowNode = {
  id: string; title: string; instructions: string; x?: number; y?: number;
  collect?: { name: string; description: string; required?: boolean }[];
  transitions?: { to: string; when: string }[];
  action?: string | null;
};
type Flow = { enabled: boolean; start: string | null; nodes: FlowNode[] };

const TEMPLATES: Record<string, Flow> = {
  qualify: {
    enabled: true, start: "greet", nodes: [
      { id: "greet", title: "Greet & understand need", instructions: "Greet warmly and ask what they are looking for.", x: 0, y: 0,
        collect: [{ name: "need", description: "what they want help with", required: true }], transitions: [{ to: "qualify", when: "need is known" }] },
      { id: "qualify", title: "Qualify", instructions: "Ask about budget and timeline, one question at a time.", x: 0, y: 170,
        collect: [{ name: "budget", description: "budget", required: true }, { name: "timeline", description: "when they want to start", required: true }],
        transitions: [{ to: "book", when: "qualified (has budget and wants to start within 3 months)" }, { to: "nurture", when: "not ready yet" }] },
      { id: "book", title: "Book a call", instructions: "Offer the next free slots and book an appointment.", x: -180, y: 360, action: "book_appointment", transitions: [{ to: "done", when: "booked" }] },
      { id: "nurture", title: "Nurture", instructions: "Offer to send helpful information on WhatsApp and follow up later.", x: 180, y: 360, transitions: [{ to: "done", when: "info sent" }] },
      { id: "done", title: "Wrap up", instructions: "Summarise next steps and thank them.", x: 0, y: 540, action: "end" },
    ],
  },
  collections: {
    enabled: true, start: "verify", nodes: [
      { id: "verify", title: "Verify identity", instructions: "Confirm you are speaking to the account holder by asking their name and date of birth.", x: 0, y: 0,
        collect: [{ name: "verified_name", description: "full name", required: true }], transitions: [{ to: "remind", when: "identity confirmed" }, { to: "callback", when: "wrong person or busy" }] },
      { id: "remind", title: "Payment reminder", instructions: "Politely remind them of the pending amount and due date. Never threaten. Offer to send a payment link.", x: 0, y: 170,
        transitions: [{ to: "pay", when: "agrees to pay now" }, { to: "promise", when: "wants to pay later" }, { to: "dispute", when: "disputes the amount" }] },
      { id: "pay", title: "Send payment link", instructions: "Send the payment link with send_payment_link and confirm they received it.", x: -220, y: 350, action: "send_payment_link", transitions: [{ to: "done", when: "link sent" }] },
      { id: "promise", title: "Promise to pay", instructions: "Agree a specific date they will pay.", x: 0, y: 350, collect: [{ name: "promise_date", description: "date they promise to pay", required: true }], transitions: [{ to: "done", when: "date agreed" }] },
      { id: "dispute", title: "Dispute", instructions: "Apologise and hand over to the accounts team.", x: 220, y: 350, action: "handoff" },
      { id: "callback", title: "Schedule callback", instructions: "Ask for a better time to call back.", x: 260, y: 170, collect: [{ name: "callback_time", description: "best time to call", required: true }], transitions: [{ to: "done", when: "time noted" }] },
      { id: "done", title: "Close", instructions: "Thank them and end the call.", x: 0, y: 520, action: "end" },
    ],
  },
};

const ACTIONS: Record<string, { label: string; icon: any; tone: string }> = {
  end: { label: "Ends conversation", icon: Square, tone: "text-muted-foreground" },
  handoff: { label: "Hands to human", icon: PhoneForwarded, tone: "text-warning" },
  book_appointment: { label: "Books appointment", icon: Flag, tone: "text-success" },
  send_payment_link: { label: "Sends payment link", icon: Flag, tone: "text-success" },
};

function StepNode({ data, selected }: NodeProps) {
  const d = data as any;
  const action = d.action ? ACTIONS[d.action] : null;
  return (
    <div className={cn("w-[220px] rounded-xl border bg-card px-3 py-2.5 shadow-sm transition", selected && "ring-2 ring-brand", d.isStart && "border-brand")}>
      <Handle type="target" position={Position.Top} className="!size-2.5 !bg-muted-foreground" />
      <div className="flex items-center gap-1.5">
        {d.isStart && <Badge className="h-4 bg-brand px-1 text-[9px] text-brand-foreground">START</Badge>}
        <p className="truncate text-sm font-semibold">{d.title}</p>
      </div>
      <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{d.instructions || "No instructions yet"}</p>
      {(d.collect?.length > 0 || action) && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {(d.collect || []).map((c: any) => <span key={c.name} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px]">{c.name}</span>)}
          {action && <span className={cn("flex items-center gap-0.5 text-[10px]", action.tone)}><action.icon className="size-3" />{action.label}</span>}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!size-2.5 !bg-brand" />
    </div>
  );
}
const nodeTypes = { step: StepNode };

function toGraph(flow: Flow): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = flow.nodes.map((n, i) => ({ id: n.id, type: "step", position: { x: n.x ?? (i % 3) * 260, y: n.y ?? Math.floor(i / 3) * 180 },
    data: { ...n, isStart: flow.start === n.id } }));
  const edges: Edge[] = flow.nodes.flatMap((n) => (n.transitions || []).map((t) => ({ id: `${n.id}->${t.to}`, source: n.id, target: t.to, label: t.when, animated: true,
    labelStyle: { fontSize: 10 }, labelBgPadding: [4, 2] as [number, number], style: { strokeWidth: 1.5 } })));
  return { nodes, edges };
}

export function FlowBuilder({ cfg, set }: { cfg: any; set: (path: string, v: any) => void }) {
  const flow: Flow = { enabled: false, start: null, nodes: [], ...(cfg.flow || {}) };
  const graph = useMemo(() => toGraph(flow), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);
  const [selected, setSelected] = useState<string | null>(flow.start);

  // Graph → agent config (positions, transitions) whenever the canvas changes.
  useEffect(() => {
    const byId = Object.fromEntries(flow.nodes.map((n) => [n.id, n]));
    const next: FlowNode[] = nodes.map((nd) => {
      const base = (byId[nd.id] || nd.data) as FlowNode;
      const trans = edges.filter((e) => e.source === nd.id).map((e) => ({ to: e.target, when: String(e.label || (base.transitions || []).find((t) => t.to === e.target)?.when || "appropriate") }));
      return { ...base, id: nd.id, x: Math.round(nd.position.x), y: Math.round(nd.position.y), transitions: trans };
    });
    const changed = JSON.stringify(next) !== JSON.stringify(flow.nodes);
    if (changed) set("flow", { ...flow, nodes: next, start: flow.start || next[0]?.id || null });
  }, [nodes, edges]); // eslint-disable-line react-hooks/exhaustive-deps

  const onConnect = useCallback((c: Connection) => setEdges((es) => addEdge({ ...c, id: `${c.source}->${c.target}`, label: "when …", animated: true }, es)), [setEdges]);
  const current = flow.nodes.find((n) => n.id === selected);
  const update = (patch: Partial<FlowNode>) => {
    const nodesNext = flow.nodes.map((n) => (n.id === selected ? { ...n, ...patch } : n));
    set("flow", { ...flow, nodes: nodesNext });
    setNodes((ns) => ns.map((n) => (n.id === selected ? { ...n, data: { ...n.data, ...patch } } : n)));
  };
  const addStep = () => {
    const id = `step_${Math.random().toString(36).slice(2, 7)}`;
    const node: FlowNode = { id, title: "New step", instructions: "", x: 40, y: (flow.nodes.length + 1) * 140, transitions: [] };
    set("flow", { ...flow, nodes: [...flow.nodes, node], start: flow.start || id });
    setNodes((ns) => [...ns, { id, type: "step", position: { x: node.x!, y: node.y! }, data: { ...node, isStart: !flow.start } }]);
    setSelected(id);
  };
  const remove = () => {
    if (!selected) return;
    set("flow", { ...flow, nodes: flow.nodes.filter((n) => n.id !== selected), start: flow.start === selected ? null : flow.start });
    setNodes((ns) => ns.filter((n) => n.id !== selected));
    setEdges((es) => es.filter((e) => e.source !== selected && e.target !== selected));
    setSelected(null);
  };
  const loadTemplate = (key: string) => {
    const t = structuredClone(TEMPLATES[key]);
    set("flow", t);
    const g = toGraph(t);
    setNodes(g.nodes);
    setEdges(g.edges);
    setSelected(t.start);
  };
  const setStart = () => {
    set("flow", { ...flow, start: selected });
    setNodes((ns) => ns.map((n) => ({ ...n, data: { ...n.data, isStart: n.id === selected } })));
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
      <Card className="gap-0 overflow-hidden p-0">
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
          <GitBranch className="size-4 text-brand" />
          <p className="text-sm font-semibold">Conversation flow</p>
          <span className="text-xs text-muted-foreground">Drag from a step&apos;s bottom dot to another step to connect. Works on chat and calls.</span>
          <div className="ml-auto flex gap-2">
            <Select onValueChange={loadTemplate}>
              <SelectTrigger className="h-8 w-[170px]"><Wand2 className="size-3.5" /><SelectValue placeholder="Start from template" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="qualify">Lead qualification</SelectItem>
                <SelectItem value="collections">Payment collections</SelectItem>
              </SelectContent>
            </Select>
            <Button size="sm" variant="outline" onClick={addStep}><Plus className="size-3.5" /> Step</Button>
          </div>
        </div>
        <div className="h-[600px]">
          <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} nodeTypes={nodeTypes}
            onNodeClick={(_, n) => setSelected(n.id)} fitView proOptions={{ hideAttribution: true }}>
            <Background gap={18} size={1} />
            <MiniMap pannable zoomable className="!bg-background" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      </Card>
      <div className="space-y-4">
        <Card className="gap-3 p-4">
          <SwitchRow label="Use this flow" hint="The agent follows the steps in order but still answers questions naturally. Off = free-form prompt agent." checked={flow.enabled} onChange={(v) => set("flow", { ...flow, enabled: v })} />
        </Card>
        {current ? (
          <Card className="gap-3 p-4">
            <Section title="Step">
              <TextField label="Title" value={current.title} onChange={(v) => update({ title: v })} />
              <AreaField label="What the agent should do here" rows={4} value={current.instructions} onChange={(v) => update({ instructions: v })} />
              <Field label="Information to collect" hint="Saved on the conversation and the CRM contact.">
                <div className="space-y-1.5">
                  {(current.collect || []).map((c, i) => (
                    <div key={i} className="flex gap-1.5">
                      <Input className="h-8 w-28 font-mono text-xs" value={c.name} onChange={(e) => update({ collect: (current.collect || []).map((x, j) => (j === i ? { ...x, name: e.target.value.replace(/\W/g, "_") } : x)) })} />
                      <Input className="h-8 text-xs" value={c.description} placeholder="description" onChange={(e) => update({ collect: (current.collect || []).map((x, j) => (j === i ? { ...x, description: e.target.value } : x)) })} />
                      <Button size="icon" variant="ghost" className="size-8" onClick={() => update({ collect: (current.collect || []).filter((_, j) => j !== i) })}><Trash2 className="size-3.5" /></Button>
                    </div>
                  ))}
                  <Button size="sm" variant="ghost" onClick={() => update({ collect: [...(current.collect || []), { name: "field", description: "", required: true }] })}><Plus className="size-3" /> field</Button>
                </div>
              </Field>
              <Field label="Then">
                <Select value={current.action || "none"} onValueChange={(v) => update({ action: v === "none" ? null : v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Continue to connected steps</SelectItem>
                    {Object.entries(ACTIONS).map(([k, a]) => <SelectItem key={k} value={k}>{a.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
              {edges.filter((e) => e.source === current.id).map((e) => (
                <Field key={e.id} label={`Go to "${flow.nodes.find((n) => n.id === e.target)?.title}" when…`}>
                  <Input value={String(e.label || "")} onChange={(ev) => setEdges((es) => es.map((x) => (x.id === e.id ? { ...x, label: ev.target.value } : x)))} />
                </Field>
              ))}
              <div className="flex gap-2 pt-1">
                {flow.start !== current.id && <Button size="sm" variant="outline" onClick={setStart}><Flag className="size-3.5" /> Make start</Button>}
                <Button size="sm" variant="ghost" className="text-destructive" onClick={remove}><Trash2 className="size-3.5" /> Delete step</Button>
              </div>
            </Section>
          </Card>
        ) : (
          <Card className="p-4 text-sm text-muted-foreground">Select a step to edit it, or start from a template.</Card>
        )}
      </div>
    </div>
  );
}
