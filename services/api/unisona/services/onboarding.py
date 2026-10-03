"""Onboarding step 1: "What does your business do?" → URL → agent draft in under a minute."""
from __future__ import annotations

import json

from ..brain.templates import TEMPLATES
from ..knowledge.extract import crawl_website
from ..log import get_logger

log = get_logger("onboarding")

PROFILE_SYSTEM = """You set up an AI customer agent for a business from its website content.
Return strict JSON:
{
 "business": {"name": str, "description": "2 sentences", "industry": str, "hours": str|"" , "phone": str|"", "email": str|"", "address": str|"", "website": str},
 "agent": {"name": "a friendly first name suited to the business and its country", "role": str, "greeting": "one-sentence greeting using the business name", "tone": 0-100 (0 formal, 100 casual), "goals": [3-4 strings]},
 "languages": ["locale codes the customers likely speak, e.g. en-IN, hi-IN"],
 "templates": [up to 3 template ids from TEMPLATE_IDS that fit best, best first],
 "faqs": [{"question": str, "answer": str}] (8-10 genuinely useful FAQs answered ONLY from the content; no guesses),
 "summary": "what the agent will be good at, 1 sentence"
}"""


async def analyze_site(llm, url: str, max_pages: int = 8) -> dict:
    docs = await crawl_website(url, max_pages=max_pages)
    if not docs:
        raise ValueError("Could not read that website. Check the URL or add documents instead.")
    content = "\n\n".join(f"## {d.title} ({d.url})\n{d.text[:3500]}" for d in docs)[:24000]
    system = PROFILE_SYSTEM.replace("TEMPLATE_IDS", json.dumps([t["id"] for t in TEMPLATES if t["id"] != "blank"]))
    profile = await llm.json(system, f"Website: {url}\n\n{content}", purpose="onboarding", max_tokens=2500)
    profile["pages"] = [{"title": d.title, "url": d.url, "chars": len(d.text)} for d in docs]
    log.info(f"Onboarding analysis for {url}: {len(docs)} pages, {len(profile.get('faqs', []))} FAQs")
    return profile
