"""Real-time emotion signal per customer turn (English, Hindi, Hinglish), no model call needed.

Returns a label (angry | frustrated | confused | neutral | happy) and a 0..1 intensity. Used for the
live-call monitor, the inbox, and to escalate to a human before a frustrated customer gives up.
Post-conversation analysis still produces the authoritative sentiment with an LLM.
"""
from __future__ import annotations

import re

_ANGRY = re.compile(r"\b(worst|useless|pathetic|ridiculous|scam|fraud|cheat(ed|ing)?|disgusting|horrible|terrible|nonsense|stupid|idiot|"
                    r"hate|furious|angry|complaint|consumer court|legal action|bakwas|bekaar|bekar|ghatiya|chor|dhokha|pagal|"
                    r"बकवास|बेकार|घटिया|धोखा|चोर)\b", re.I)
_FRUSTRATED = re.compile(r"\b(again|still( not)?|already (told|said|asked)|third time|how many times|waiting (for|since)|no one|nobody|"
                         r"not working|doesn'?t work|never (got|received)|kab tak|kitni baar|abhi tak|phir se|koi nahi|"
                         r"कब तक|कितनी बार|अभी तक)\b", re.I)
_CONFUSED = re.compile(r"\b(what do you mean|don'?t understand|confus|samajh nahi|kya matlab|huh|i'?m lost|समझ नहीं)\b", re.I)
_HAPPY = re.compile(r"\b(thanks?|thank you|great|awesome|perfect|excellent|love|amazing|helpful|wonderful|dhanyavad|shukriya|badhiya|"
                    r"bahut accha|mast|धन्यवाद|शुक्रिया|बढ़िया)\b", re.I)


def score(text: str) -> dict:
    t = text or ""
    angry, frus, conf, happy = len(_ANGRY.findall(t)), len(_FRUSTRATED.findall(t)), len(_CONFUSED.findall(t)), len(_HAPPY.findall(t))
    shouting = sum(1 for w in re.findall(r"\b[A-Z]{3,}\b", t)) >= 2
    bangs = t.count("!") >= 3 or "??" in t
    neg = angry * 2 + frus + (1 if shouting else 0) + (1 if bangs else 0)
    if angry or (neg >= 3):
        label, intensity = "angry", min(1.0, 0.55 + 0.15 * neg)
    elif frus or shouting or bangs:
        label, intensity = "frustrated", min(1.0, 0.4 + 0.15 * neg)
    elif conf:
        label, intensity = "confused", 0.4
    elif happy:
        label, intensity = "happy", min(1.0, 0.5 + 0.1 * happy)
    else:
        label, intensity = "neutral", 0.0
    return {"label": label, "intensity": round(intensity, 2)}


def trend(history: list[dict], new: dict, keep: int = 8) -> tuple[list[dict], bool]:
    """Append and decide whether to escalate: two strongly negative turns in a row, or one very angry turn."""
    h = [*history, new][-keep:]
    negative = [x for x in h[-2:] if x["label"] in {"angry", "frustrated"} and x["intensity"] >= 0.5]
    escalate = (new["label"] == "angry" and new["intensity"] >= 0.85) or len(negative) == 2
    return h, escalate
