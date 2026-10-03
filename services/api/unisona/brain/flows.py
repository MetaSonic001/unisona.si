"""Conversation flows: a visual, step-by-step script layered on top of a prompt agent.

A flow is a graph of steps. Each step has instructions, fields to collect and transitions to
other steps. The agent always sees only the current step (plus what it has collected) and moves
with the `flow_goto` tool; `flow_save` stores collected answers on the conversation and the CRM
contact. Works identically for text and voice, so a flow built once runs on every channel.

Config (agent.config["flow"]):
{
  "enabled": true, "start": "greet",
  "nodes": [{"id": "greet", "title": "Greet & qualify", "instructions": "...",
             "collect": [{"name": "budget", "description": "monthly budget in INR", "required": true}],
             "transitions": [{"to": "book", "when": "budget captured and interested"}],
             "action": null | "handoff" | "end" | "book_appointment" | "send_payment_link",
             "x": 0, "y": 0}]
}
"""
from __future__ import annotations

from typing import Any


def enabled(cfg: dict) -> bool:
    f = cfg.get("flow") or {}
    return bool(f.get("enabled") and f.get("nodes"))


def nodes(cfg: dict) -> dict[str, dict]:
    return {n["id"]: n for n in (cfg.get("flow") or {}).get("nodes", []) if n.get("id")}


def initial_state(cfg: dict) -> dict:
    f = cfg.get("flow") or {}
    start = f.get("start") or next(iter(nodes(cfg)), None)
    return {"node": start, "data": {}, "history": [start] if start else []}


def current(cfg: dict, state: dict | None) -> dict | None:
    state = state or initial_state(cfg)
    return nodes(cfg).get(state.get("node") or "")


def prompt_section(cfg: dict, state: dict | None) -> str:
    """Instructions for the current step only, so the model cannot skip ahead."""
    state = state or initial_state(cfg)
    node = current(cfg, state)
    if not node:
        return ""
    all_nodes = nodes(cfg)
    lines = [f"CONVERSATION SCRIPT. You are on step \"{node.get('title') or node['id']}\".", node.get("instructions", "").strip()]
    collect = node.get("collect") or []
    if collect:
        have = state.get("data") or {}
        lines.append("Collect from the customer (ask naturally, one at a time), saving each with flow_save:")
        for c in collect:
            status = f"already have: {have[c['name']]}" if c["name"] in have else ("required" if c.get("required", True) else "optional")
            lines.append(f"- {c['name']}: {c.get('description', '')} ({status})")
    trans = [t for t in node.get("transitions") or [] if t.get("to") in all_nodes]
    if trans:
        lines.append("When a condition below is met, call flow_goto with that step id (do not mention steps to the customer):")
        lines += [f"- go to \"{t['to']}\" ({all_nodes[t['to']].get('title', '')}) when: {t.get('when', 'appropriate')}" for t in trans]
    if node.get("action") == "end":
        lines.append("This is the final step: wrap up warmly and end the conversation.")
    elif node.get("action") == "handoff":
        lines.append("This step hands the customer to a human: summarise, then call handoff_to_human.")
    if state.get("data"):
        lines.append("Collected so far: " + ", ".join(f"{k}={v}" for k, v in state["data"].items()))
    return "\n".join(x for x in lines if x)


def tool_schemas(cfg: dict, state: dict | None) -> list[dict]:
    node = current(cfg, state)
    if not node:
        return []
    targets = [t["to"] for t in node.get("transitions") or [] if t.get("to") in nodes(cfg)]
    out = []
    if targets:
        out.append({"type": "function", "function": {
            "name": "flow_goto", "description": "Move the conversation script to the next step once its condition is met.",
            "parameters": {"type": "object", "properties": {"step": {"type": "string", "enum": targets}, "reason": {"type": "string"}},
                           "required": ["step"]}}})
    names = [c["name"] for c in node.get("collect") or []]
    if names:
        out.append({"type": "function", "function": {
            "name": "flow_save", "description": "Save a piece of information the customer gave for the current script step.",
            "parameters": {"type": "object", "properties": {"field": {"type": "string", "enum": names}, "value": {"type": "string"}},
                           "required": ["field", "value"]}}})
    return out


def goto(cfg: dict, state: dict, step: str) -> tuple[dict, str]:
    node = current(cfg, state)
    allowed = {t["to"] for t in (node or {}).get("transitions") or []}
    if step not in nodes(cfg) or (node and step not in allowed):
        return state, f"Step '{step}' is not reachable from here. Allowed: {', '.join(sorted(allowed)) or 'none'}."
    missing = [c["name"] for c in (node or {}).get("collect") or [] if c.get("required", True) and c["name"] not in (state.get("data") or {})]
    if missing:
        return state, f"Before moving on, collect: {', '.join(missing)}."
    new = {**state, "node": step, "history": [*(state.get("history") or []), step][-50:]}
    target = nodes(cfg)[step]
    return new, f"Now on step '{target.get('title') or step}'. Follow its instructions: {target.get('instructions', '')[:600]}"


def save(cfg: dict, state: dict, field: str, value: Any) -> tuple[dict, str]:
    data = {**(state.get("data") or {}), field: value}
    return {**state, "data": data}, f"Saved {field}."
