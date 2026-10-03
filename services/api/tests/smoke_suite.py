"""End-to-end smoke test for the growth suite + calling features against a running API (dev mode).

    cd services/api && uv run python tests/smoke_suite.py
"""
import asyncio
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
ENV = dict(line.split("=", 1) for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
BASE = os.environ.get("API", "http://127.0.0.1:8000")
H = {"Authorization": f"Bearer dev:{ENV.get('DEV_TOKEN', '').strip()}"}
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail[:160]}")


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, headers=H, timeout=90) as c:
        agents = (await c.get("/agents")).json()["items"]
        dental = next(a for a in agents if "Dental" in a["name"])
        shop = next(a for a in agents if "Shop" in a["name"])

        # ── compliance & capacity
        r = await c.patch("/compliance", json={"calling_start": "08:00", "calling_end": "21:00", "auto_opt_out": True})
        check("compliance settings", r.status_code == 200, r.text)
        r = await c.post("/compliance/dnd", json={"values": ["+91 99999 00001"], "reason": "test"})
        check("dnd add", r.status_code == 200, r.text)
        r = await c.get("/compliance")
        check("dnd list", r.status_code == 200 and r.json()["dnd_count"] >= 1, str(r.json().get("dnd_count")))
        r = await c.get("/calls/capacity")
        check("call capacity", r.status_code == 200 and r.json()["limit"] >= 1, r.text)

        # ── opt-out in conversation (WhatsApp simulator)
        r = await c.post("/dev/simulate", json={"agent_id": dental["id"], "channel": "whatsapp", "from": "+919811100001", "name": "Optout Test",
                                                "text": "Please stop messaging me"})
        check("opt-out honoured", r.status_code == 200 and ("won't" in r.json().get("text", "") or "nahi" in r.json().get("text", "")), r.json().get("text", ""))

        # ── emotion → escalation
        r1 = await c.post("/dev/simulate", json={"agent_id": dental["id"], "channel": "whatsapp", "from": "+919811100002", "name": "Angry Test",
                                                 "text": "This is the third time I'm asking, nobody replied! Worst service!!!"})
        check("emotion escalation", r1.status_code == 200 and r1.json().get("handoff") is True, f"handoff={r1.json().get('handoff')} {r1.json().get('text', '')[:80]}")

        # ── forms
        r = await c.post("/forms/from-template/lead")
        form = r.json()
        check("form from template", r.status_code == 200 and form.get("slug"), form.get("slug", ""))
        pub = await c.get(f"/public/forms/{form['slug']}")
        check("public form", pub.status_code == 200 and len(pub.json()["fields"]) >= 3)
        sub = await c.post(f"/public/forms/{form['slug']}", json={"data": {"name": "Form Lead", "phone": "+919811100003", "service": "Repair",
                                                                            "budget": "₹10k–50k", "consent": True}})
        check("form submit → contact", sub.status_code == 200, sub.text)
        bad = await c.post(f"/public/forms/{form['slug']}", json={"data": {"name": "x"}})
        check("form validation", bad.status_code == 422, bad.text)
        subs = await c.get(f"/forms/{form['id']}/submissions")
        check("form submissions", subs.status_code == 200 and len(subs.json()["items"]) >= 1)

        # ── landing page (AI generated)
        r = await c.post("/pages/generate", json={"agent_id": dental["id"], "form_id": form["id"], "brief": "family dental clinic in Bengaluru"})
        page = r.json()
        check("AI page generate", r.status_code == 200 and len(page.get("blocks", [])) >= 4, f"{len(page.get('blocks', []))} blocks")
        await c.patch(f"/pages/{page['id']}", json={"published": True})
        pp = await c.get(f"/public/pages/{page['slug']}")
        check("public page", pp.status_code == 200 and pp.json()["blocks"], pp.json().get("seo", {}).get("title", ""))

        # ── reputation
        await c.patch("/reputation/settings", json={"review_url": "https://g.page/r/example/review", "threshold": 4})
        contacts = (await c.get("/crm/contacts", params={"q": "Form Lead"})).json()["items"]
        cid = contacts[0]["id"] if contacts else None
        r = await c.post("/reputation/request", json={"contact_id": cid, "channel": "email"})
        check("review request created", r.status_code == 200 and r.json()["results"], r.text)
        rep = (await c.get("/reputation")).json()
        token = rep["items"][0]["token"] if rep["items"] else None
        v = await c.get(f"/public/reviews/{token}")
        check("public review page", v.status_code == 200, v.text)
        happy = await c.post(f"/public/reviews/{token}", json={"rating": 5})
        check("happy → review site", happy.json().get("happy") is True and happy.json().get("review_url"), happy.text)

        # ── payments (no provider connected → clear error)
        r = await c.post("/payments/links", json={"amount": 499, "description": "Consultation"})
        check("payment link needs provider", r.status_code == 400 and "provider" in r.text.lower(), r.text)

        # ── integrations + incoming hooks
        r = await c.get("/integrations")
        check("integrations catalog", r.status_code == 200 and len(r.json()["catalog"]) == 4)
        r = await c.post("/integrations/hubspot", json={"token": "bad"})
        check("hubspot bad token rejected", r.status_code == 400, r.text)
        hook = (await c.post("/incoming-hooks", json={"name": "Zapier leads", "action": "upsert_contact", "config": {"tags": ["zapier"]}})).json()
        r = await httpx.AsyncClient(base_url=BASE).post(f"/hooks/{hook['token']}", json={"full_name": "Zap Lead", "mobile": "+919811100004"})
        check("incoming hook → contact", r.status_code == 200 and r.json().get("contact_id"), r.text)

        # ── flows (playground, draft)
        flow = {"enabled": True, "start": "qualify", "nodes": [
            {"id": "qualify", "title": "Qualify", "instructions": "Find out which treatment the patient wants.",
             "collect": [{"name": "treatment", "description": "treatment they want", "required": True}],
             "transitions": [{"to": "book", "when": "treatment is known"}]},
            {"id": "book", "title": "Offer booking", "instructions": "Offer to book an appointment and ask for a preferred day.", "transitions": []}]}
        await c.patch(f"/agents/{dental['id']}", json={"config": {"flow": flow}})
        conv = None
        for text in ["Hi", "I want teeth whitening"]:
            r = await c.post(f"/chat/{dental['id']}", json={"text": text, "conversation_id": conv, "stream": False})
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            conv = body.get("conversation_id") or conv
        cv = (await c.get(f"/conversations/{conv}")).json() if conv else {}
        fstate = ((cv.get("conversation") or {}).get("meta") or {}).get("flow") or {}
        check("flow advances", fstate.get("node") == "book" or "treatment" in (fstate.get("data") or {}), str(fstate))
        await c.patch(f"/agents/{dental['id']}", json={"config": {"flow": {"enabled": False, "nodes": []}}})

        # ── squads: dental front desk hands orders to the ShopKart agent
        await c.patch(f"/agents/{dental['id']}", json={"config": {"squad": {"members": [
            {"name": "orders", "agent_id": shop["id"], "when": "questions about online orders, deliveries or refunds"}]}}})
        r = await c.post(f"/chat/{dental['id']}", json={"text": "Hi, where is my online order ORD-1001? It hasn't been delivered.", "channel": "whatsapp",
                                                        "identifiers": {"wa_id": "+919811100005"}, "use_draft": True, "stream": False})
        conv_id = r.json().get("conversation_id")
        cv = (await c.get(f"/conversations/{conv_id}")).json()
        moved = (cv.get("conversation") or {}).get("agent_id") == shop["id"]
        check("squad transfer", moved, r.json().get("text", "")[:120])
        if moved:
            r2 = await c.post(f"/chat/{dental['id']}", json={"text": "Order ORD-1001", "channel": "whatsapp", "identifiers": {"wa_id": "+919811100005"},
                                                             "use_draft": True, "stream": False})
            check("specialist answers next turn", r2.json().get("conversation_id") == conv_id, r2.json().get("text", "")[:120])
        await c.patch(f"/agents/{dental['id']}", json={"config": {"squad": {"members": []}}})

        # ── agency
        r = await c.post("/agency/enable", json={"rebilling": {"default_markup_pct": 40}})
        check("agency enable", r.status_code == 200, r.text)
        r = await c.post("/agency/clients", json={"name": "Smoke Test Client", "blueprint_agent_ids": [dental["id"]]})
        client = r.json()
        check("create client + blueprint", r.status_code == 200 and client.get("id"), r.text)
        acc = (await c.get("/workspaces/accessible")).json()
        check("workspace switcher lists client", any(x["id"] == client["id"] for x in acc["clients"]))
        r = await c.get("/agents", headers={**H, "x-workspace-id": client["id"]})
        check("act inside client (blueprint agent copied)", r.status_code == 200 and len(r.json()["items"]) >= 1, f"{len(r.json().get('items', []))} agents")
        r = await c.get("/agents", headers={**H, "x-workspace-id": "ws_doesnotexist"})
        check("foreign workspace rejected", r.status_code == 403, r.text)
        r = await c.get("/agency/report")
        check("rebilling report", r.status_code == 200 and "rows" in r.json())
        r = await c.patch("/workspace/branding", json={"name": "Acme Dental Group", "primary_color": "#0F766E"})
        check("branding", r.status_code == 200)

        # ── WhatsApp templates without WABA → helpful error
        chans = (await c.get(f"/agents/{dental['id']}/channels")).json()
        check("channels listing", isinstance(chans, (list, dict)))

        # ── voice presets + tools present in voice snapshot
        r = await c.get("/evals/voice-presets")
        check("voice eval presets", r.status_code == 200 and len(r.json()["scenarios"]) >= 3)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


sys.exit(asyncio.run(main()))
