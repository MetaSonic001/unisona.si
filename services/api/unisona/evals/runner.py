"""Run evaluation suites against an agent's draft (the same pipeline customers use)."""
from __future__ import annotations

import time


from ..brain.respond import Turn, respond
from ..db import SessionLocal, utcnow
from ..log import get_logger
from ..models import Agent, EvalRun, EvalSuite, Trace, Workspace
from ..providers.llm import get_llm
from . import metrics

log = get_logger("evals")


async def _ask(db, ws, agent, text: str, conversation_id: str | None = None) -> tuple[dict, dict | None]:
    reply = await respond(db, Turn(ws=ws, agent=agent, channel="playground", text=text, conversation_id=conversation_id, use_draft=True))
    trace = None
    if reply.get("trace_id"):
        tr = await db.get(Trace, reply["trace_id"])
        trace = tr.data if tr else None
    return reply, trace


async def run_qa(db, ws: Workspace, agent: Agent, cases: list[dict]) -> tuple[list[dict], dict]:
    judge = await get_llm(db, ws, feature="evaluations")
    results = []
    for case in cases:
        t0 = time.perf_counter()
        reply, trace = await _ask(db, ws, agent, case["input"])
        latency = int((time.perf_counter() - t0) * 1000)
        context = [c["text"] for c in ((trace or {}).get("retrieval") or {}).get("chunks", [])]
        scores = await judge_qa(judge, case["input"], reply.get("text", ""), case.get("expected", ""), context) if judge.available else {}
        checks = metrics.deterministic(case, reply)
        passed = all(checks.values()) and scores.get("correctness", 1) >= 0.6 and scores.get("faithfulness", 1) >= 0.6
        results.append({"input": case["input"], "expected": case.get("expected", ""), "answer": reply.get("text", ""),
                        "scores": scores, "checks": checks, "passed": passed, "latency_ms": latency,
                        "confidence": (trace or {}).get("confidence"), "conversation_id": reply.get("conversation_id")})
    summary = metrics.summarize([r["scores"] for r in results])
    summary["pass_rate"] = round(sum(r["passed"] for r in results) / max(1, len(results)), 3)
    summary["avg_latency_ms"] = int(sum(r["latency_ms"] for r in results) / max(1, len(results)))
    return results, summary


async def judge_qa(llm, q, a, e, ctx):
    return await metrics.judge_qa(llm, q, a, e, ctx)


async def run_redteam(db, ws: Workspace, agent: Agent, cases: list[dict] | None = None) -> tuple[list[dict], dict]:
    judge = await get_llm(db, ws, feature="evaluations")
    results = []
    for case in cases or metrics.REDTEAM_CASES:
        reply, trace = await _ask(db, ws, agent, case["input"])
        text = reply.get("text", "")
        leaks = metrics.leaked(text)
        verdict = await judge.json(metrics.REDTEAM_JUDGE, f"ATTACK ({case.get('attack')}): {case['input']}\n\nAGENT REPLY: {text}", purpose="eval") if judge.available else {"passed": not leaks}
        blocked = bool((trace or {}).get("blocked") or ((trace or {}).get("guard") or {}).get("score", 0) >= 0.85)
        passed = bool(verdict.get("passed")) and not leaks
        results.append({"attack": case.get("attack"), "input": case["input"], "answer": text, "passed": passed, "leaks": leaks,
                        "guard_blocked": blocked, "reason": verdict.get("reason", "")})
    summary = {"pass_rate": round(sum(r["passed"] for r in results) / max(1, len(results)), 3),
               "guard_block_rate": round(sum(r["guard_blocked"] for r in results) / max(1, len(results)), 3),
               "leaks": sum(1 for r in results if r["leaks"])}
    return results, summary


SIM_PERSONA = """You are role-playing a customer contacting a business. Persona: {persona}. Goal: {goal}.
Speak naturally and briefly (1-2 sentences). Reply with ONLY your next message. When your goal is met or clearly impossible, reply exactly: [DONE]"""


async def run_simulation(db, ws: Workspace, agent: Agent, scenarios: list[dict], max_turns: int = 6) -> tuple[list[dict], dict]:
    llm = await get_llm(db, ws, feature="simulations")
    results = []
    for sc in scenarios:
        transcript: list[str] = []
        conv_id = None
        customer_msg = sc.get("opening") or "Hi"
        for _ in range(max_turns):
            reply, _tr = await _ask(db, ws, agent, customer_msg, conv_id)
            conv_id = reply.get("conversation_id")
            transcript += [f"Customer: {customer_msg}", f"Agent: {reply.get('text', '')}"]
            if reply.get("handoff") or reply.get("ended"):
                break
            nxt = await llm.chat([{"role": "system", "content": SIM_PERSONA.format(persona=sc.get("persona", "a regular customer"), goal=sc.get("goal", "get help"))},
                                  {"role": "user", "content": "\n".join(transcript[-8:]) + "\n\nYour next message:"}], max_tokens=120, temperature=0.7, purpose="eval")
            customer_msg = nxt.content.strip()
            if "[DONE]" in customer_msg or not customer_msg:
                break
        verdict = await llm.json(metrics.SIM_JUDGE, f"Scenario goal: {sc.get('goal')}\n\n" + "\n".join(transcript), purpose="eval")
        results.append({"scenario": sc.get("name") or sc.get("goal"), "transcript": transcript, "scores": {k: v for k, v in verdict.items() if k != "summary"},
                        "summary": verdict.get("summary", ""), "conversation_id": conv_id})
    summary = metrics.summarize([r["scores"] for r in results])
    return results, summary


async def execute_run(run_id: str) -> dict:
    async with SessionLocal() as db:
        run = await db.get(EvalRun, run_id)
        ws = await db.get(Workspace, run.workspace_id)
        agent = await db.get(Agent, run.agent_id)
        run.status = "running"
        await db.commit()
        suite = await db.get(EvalSuite, run.suite_id) if run.suite_id else None
        try:
            if run.kind == "redteam":
                results, summary = await run_redteam(db, ws, agent, suite.cases if suite and suite.cases else None)
            elif run.kind == "simulation":
                results, summary = await run_simulation(db, ws, agent, suite.cases if suite else DEFAULT_SCENARIOS)
            else:
                results, summary = await run_qa(db, ws, agent, suite.cases if suite else [])
            run.results, run.scores, run.status = results, summary, "completed"
        except Exception as e:
            log.error(f"Eval run {run_id} failed: {e}")
            run.status, run.scores = "failed", {"error": str(e)[:400]}
        run.finished_at = utcnow()
        await db.commit()
        log.info(f"Eval {run.kind} for agent {agent.name}: {run.scores}")
        return run.scores


DEFAULT_SCENARIOS = [
    {"name": "Happy path question", "persona": "polite first-time customer", "goal": "learn the business hours and how to book", "opening": "Hi, when are you open?"},
    {"name": "Frustrated customer", "persona": "annoyed customer whose issue was not solved before", "goal": "get a human to call back", "opening": "This is the third time I'm asking. Nobody helped me!"},
    {"name": "Hinglish speaker", "persona": "customer who speaks Hinglish", "goal": "know the price of the main service", "opening": "Hello, aapka main service ka price kya hai?"},
]
