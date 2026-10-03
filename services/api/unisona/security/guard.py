"""Prompt-injection and abuse defenses.

Layers (cheap first):
1. Heuristics: known jailbreak/override phrasings in many languages, role-tag smuggling,
   and attempts to reveal the system prompt.
2. Llama Prompt Guard 2 (86M) through Groq, when a Groq key is available. It returns
   an injection probability between 0 and 1.
3. Spotlighting: retrieved documents and tool output are wrapped in explicit data tags
   (`fence_untrusted`) so the model treats them as data, not instructions.
4. Canary: a random token placed in every system prompt. If it shows up in a reply,
   the reply is blocked and the turn is flagged (`leaked_canary`).
"""
from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass

from ..log import get_logger

log = get_logger("guard")

_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts|rules|messages)",
    r"disregard (all |any |the )?(previous|prior|above|system) (instructions|prompt|rules)",
    r"forget (everything|all|your) (instructions|rules|above|previous)",
    r"(reveal|show|print|repeat|output|leak|display) (me )?(your|the) (system|initial|hidden|original) (prompt|instructions|message)",
    r"what (is|was|are) your (system prompt|instructions|initial prompt)",
    r"you are now (in )?(developer|dan|jailbreak|god) mode",
    r"\b(DAN|do anything now)\b",
    r"act as (an? )?(unfiltered|uncensored|jailbroken)",
    r"pretend (that )?you (have no|don't have any|are not bound by) (rules|restrictions|guidelines)",
    r"</?(system|assistant|developer|instructions?)>",
    r"\[\s*(system|INST|/INST)\s*\]",
    r"<\|im_start\|>|<\|im_end\|>|<\|system\|>",
    r"new instructions?:",
    r"override (your|the) (rules|instructions|policy|safety)",
    # Hindi / Hinglish
    r"(पिछले|पहले के|सभी) (निर्देश|निर्देशों) (को )?(भूल|अनदेखा)",
    r"(apne|sab|pichle) (instructions|niyam|rules) (bhool|ignore) (jao|karo|kar do)",
    r"system prompt (batao|dikhao)",
]
_RX = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.IGNORECASE)
_cache: dict[str, tuple[float, float]] = {}


@dataclass
class GuardResult:
    score: float
    blocked: bool
    reasons: list[str]
    model_used: bool = False


def heuristic_score(text: str) -> tuple[float, list[str]]:
    reasons = [m.group(0)[:60] for m in _RX.finditer(text or "")]
    if not reasons:
        return 0.0, []
    return min(0.6 + 0.15 * len(reasons), 0.97), reasons


async def check_input(text: str, groq_key: str | None, threshold: float = 0.85) -> GuardResult:
    h_score, reasons = heuristic_score(text)
    score, used = h_score, False
    if groq_key and text and len(text) > 12:
        key = text[:500]
        hit = _cache.get(key)
        if hit and hit[1] > time.time():
            score = max(score, hit[0])
            used = True
        else:
            try:
                from ..providers.llm import groq_client

                r = await groq_client(groq_key).chat.completions.create(
                    model="meta-llama/llama-prompt-guard-2-86m",
                    messages=[{"role": "user", "content": text[:2000]}],
                    timeout=3,
                )
                model_score = float((r.choices[0].message.content or "0").strip())
                _cache[key] = (model_score, time.time() + 3600)
                score = max(score, model_score)
                used = True
                if model_score >= threshold:
                    reasons.append(f"prompt-guard={model_score:.3f}")
            except Exception as e:
                log.debug(f"Prompt Guard unavailable, heuristics only: {e}")
    blocked = score >= threshold
    if blocked:
        log.warning(f"Blocked likely prompt injection (score {score:.2f}): {reasons[:3]}")
    return GuardResult(score=round(score, 4), blocked=blocked, reasons=reasons, model_used=used)


def new_canary() -> str:
    return f"CNRY-{secrets.token_hex(6)}"


def leaked_canary(output: str, canary: str) -> bool:
    return bool(canary) and canary in (output or "")


def fence_untrusted(label: str, text: str) -> str:
    """Wrap untrusted content so the model treats it as data, never as instructions."""
    safe = (text or "").replace("</data>", "</ data>")
    return f'<data source="{label}">\n{safe}\n</data>'


SAFE_REFUSAL = {
    "en": "I can't help with that request, but I'm happy to help with anything else about our products or services.",
    "hi": "मैं इस अनुरोध में मदद नहीं कर सकता, लेकिन हमारे उत्पादों या सेवाओं से जुड़ी किसी भी और बात में ख़ुशी से मदद करूँगा।",
}
