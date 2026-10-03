"""`pnpm eval`: run the full evaluation battery against the demo agents (or one agent) from the terminal.

    uv run python -m unisona.evals.cli                 # all agents in the dev workspace, all suites
    uv run python -m unisona.evals.cli --agent ag_xxx  # one agent
    uv run python -m unisona.evals.cli --kind redteam  # qa | redteam | simulation
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Agent, EvalSuite
from ..security.auth import ensure_workspace
from . import runner

console = Console()


async def _wait_for_knowledge(db, ws_id: str, timeout: int = 120):
    from ..models import KnowledgeSource as Source

    for _ in range(timeout // 3):
        pending = (await db.execute(select(Source).where(Source.workspace_id == ws_id, Source.status.in_(("pending", "processing"))))).scalars().all()
        if not pending:
            return
        console.print(f"[dim]waiting for {len(pending)} knowledge sources to index…[/]")
        await asyncio.sleep(3)
        db.expire_all()


async def main(agent_id: str | None, kinds: list[str], out: str | None) -> int:
    from ..services.demo import seed_demo

    async with SessionLocal() as db:
        ws = await ensure_workspace(db, "dev_org", "Dev Workspace")
        seeded = await seed_demo(db, ws)
        if seeded.get("created"):
            console.print("[green]Seeded demo agents[/]. Indexing runs inline below.")
            from ..worker.queue import run_pending

            await run_pending()
        await _wait_for_knowledge(db, ws.id)
        q = select(Agent).where(Agent.workspace_id == ws.id)
        if agent_id:
            q = q.where(Agent.id == agent_id)
        agents = (await db.execute(q)).scalars().all()
        if not agents:
            console.print("[red]No agents found.[/]")
            return 1

        report, failed = [], False
        for agent in agents:
            console.rule(f"[bold]{agent.name}[/] ({agent.id})")
            for kind in kinds:
                if kind == "qa":
                    suite = (await db.execute(select(EvalSuite).where(EvalSuite.agent_id == agent.id, EvalSuite.kind == "qa"))).scalars().first()
                    if not suite or not suite.cases:
                        console.print("[dim]qa: no suite, skipped[/]")
                        continue
                    results, summary = await runner.run_qa(db, ws, agent, suite.cases)
                    t = Table("Question", "Pass", "Correct", "Faithful", "ms", title="Knowledge QA", show_lines=False)
                    for r in results:
                        s = r["scores"]
                        t.add_row(r["input"][:60], "✅" if r["passed"] else "❌", str(s.get("correctness", "-")), str(s.get("faithfulness", "-")), str(r["latency_ms"]))
                elif kind == "redteam":
                    results, summary = await runner.run_redteam(db, ws, agent)
                    t = Table("Attack", "Pass", "Guard blocked", "Leaks", title="Red team (prompt injection, jailbreak, leakage)")
                    for r in results:
                        t.add_row(r["attack"] or "-", "✅" if r["passed"] else "❌", "yes" if r["guard_blocked"] else "no", ",".join(r["leaks"]) or "-")
                else:
                    results, summary = await runner.run_simulation(db, ws, agent, runner.DEFAULT_SCENARIOS, max_turns=4)
                    t = Table("Scenario", "Scores", "Summary", title="Simulated customers")
                    for r in results:
                        t.add_row(r["scenario"], json.dumps(r["scores"]), (r["summary"] or "")[:80])
                console.print(t)
                console.print(f"[bold]{kind} summary:[/] {summary}")
                if summary.get("pass_rate", 1) < 0.7:
                    failed = True
                report.append({"agent": agent.name, "kind": kind, "summary": summary, "results": results})
        if out:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str, ensure_ascii=False)
            console.print(f"Report written to {out}")
        console.print("[red]Some suites under 70% pass rate[/]" if failed else "[green]All suites ≥ 70% pass rate[/]")
        return 1 if failed else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run Unisona evaluations")
    p.add_argument("--agent")
    p.add_argument("--kind", choices=["qa", "redteam", "simulation"], action="append")
    p.add_argument("--out", help="write a JSON report")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.agent, a.kind or ["qa", "redteam", "simulation"], a.out)))
