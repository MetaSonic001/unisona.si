"""Channel renderers: one answer, shaped for each channel.

The brain returns plain text plus structured extras (citations, quick replies). Renderers
enforce channel rules after generation, so a model that slips markdown into a voice
reply still sounds right.
"""
from __future__ import annotations

import re

_OPTIONS = re.compile(r"\n?\s*OPTIONS:\s*(.+)\s*$", re.I)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_URL = re.compile(r"https?://\S+")


def split_options(text: str) -> tuple[str, list[str]]:
    m = _OPTIONS.search(text or "")
    if not m:
        return text, []
    opts = [o.strip() for o in m.group(1).split("|") if o.strip()][:10]
    return text[: m.start()].rstrip(), opts


def for_voice(text: str) -> str:
    t, _ = split_options(text)
    t = _MD_LINK.sub(r"\1", t)
    t = _URL.sub("the link I can send you", t)
    t = re.sub(r"\[\d+\]", "", t)                    # citation markers
    t = re.sub(r"[*_`#>|~]+", "", t)                  # markdown symbols
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)     # bullets
    t = re.sub(r"\s*\n+\s*", " ", t)
    t = t.replace("&", " and ").replace("%", " percent")
    t = re.sub(r"₹\s?([\d,]+)", lambda m: f"{m.group(1)} rupees", t)
    t = re.sub(r"\$\s?([\d,.]+)", lambda m: f"{m.group(1)} dollars", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def for_whatsapp(text: str) -> tuple[str, list[str]]:
    t, opts = split_options(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)          # **bold** → *bold*
    t = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", t, flags=re.M)
    t = _MD_LINK.sub(r"\1: \2", t)
    t = re.sub(r"\[\d+\]", "", t)
    return t.strip(), opts


def for_telegram(text: str) -> tuple[str, list[str]]:
    t, opts = split_options(text)
    t = re.sub(r"\[\d+\]", "", t)
    return t.strip(), opts


def for_web(text: str) -> tuple[str, list[str]]:
    return split_options(text)


_MARKERS = re.compile(r"\s?【[^】]{0,12}】|\s?\[\d+(?:,\s*\d+)*\](?!\()")


def render(channel: str, text: str) -> dict:
    """Return the channel-ready payload: {text, options}."""
    text = _MARKERS.sub("", text or "")
    if channel in {"voice", "phone"}:
        return {"text": for_voice(text), "options": []}
    if channel == "whatsapp":
        t, o = for_whatsapp(text)
        return {"text": t, "options": o}
    if channel in {"telegram", "instagram", "messenger"}:
        t, o = for_telegram(text)
        return {"text": t, "options": o}
    if channel == "sms":
        t, o = for_telegram(text)
        t = t.replace("*", "").replace("_", "")
        if o:
            t += "\n" + " / ".join(o)
        return {"text": t, "options": []}
    t, o = for_web(text)
    return {"text": t, "options": o}
