"""Fast language detection tuned for Indian languages and code-mixing.

Unicode script ranges identify Indic scripts reliably even for 3-word replies, where
statistical detectors fail. Latin text falls back to langdetect, with a Hinglish
check (romanised Hindi function words).
"""
from __future__ import annotations

import re

_SCRIPTS = [
    ("hi", r"[ऀ-ॿ]"),  # Devanagari (Hindi/Marathi/Nepali; refined below)
    ("bn", r"[ঀ-৿]"),
    ("pa", r"[਀-੿]"),
    ("gu", r"[઀-૿]"),
    ("or", r"[଀-୿]"),
    ("ta", r"[஀-௿]"),
    ("te", r"[ఀ-౿]"),
    ("kn", r"[ಀ-೿]"),
    ("ml", r"[ഀ-ൿ]"),
    ("ar", r"[؀-ۿ]"),
    ("zh", r"[一-鿿]"),
    ("ja", r"[぀-ヿ]"),
    ("ru", r"[Ѐ-ӿ]"),
]
_MARATHI_HINTS = re.compile(r"(आहे|आहेत|नाही|मला|तुम्ही|काय|कसे)")
_HINGLISH = re.compile(r"\b(hai|haan|nahi|nahin|kya|kaise|mujhe|aap|aapka|mera|kab|kitna|kripya|theek|thik|accha|acha|bhai|karo|chahiye|hoga|batao|ji)\b", re.I)


def detect(text: str) -> str:
    """Return a short language code: en, hi, hinglish, ta, te, bn, mr, gu, kn, ml, ur, ar, ..."""
    t = (text or "").strip()
    if not t:
        return "en"
    counts = {code: len(re.findall(rx, t)) for code, rx in _SCRIPTS}
    code, n = max(counts.items(), key=lambda kv: kv[1])
    if n >= 2:
        if code == "hi" and _MARATHI_HINTS.search(t):
            return "mr"
        if code == "ar" and re.search(r"[ٹڈڑںےۓ]", t):
            return "ur"
        return code
    if len(_HINGLISH.findall(t)) >= 2:
        return "hinglish"
    try:
        from langdetect import DetectorFactory, detect as ld

        DetectorFactory.seed = 0
        guess = ld(t)
        return guess.split("-")[0] if len(t) > 12 else "en"
    except Exception:
        return "en"


LOCALE_FOR = {"en": "en-IN", "hi": "hi-IN", "hinglish": "hi-IN", "ta": "ta-IN", "te": "te-IN", "bn": "bn-IN", "mr": "mr-IN",
              "gu": "gu-IN", "kn": "kn-IN", "ml": "ml-IN", "ur": "ur-IN", "ar": "ar-SA", "es": "es-ES", "fr": "fr-FR",
              "de": "de-DE", "pt": "pt-BR", "ja": "ja-JP", "zh": "zh-CN", "it": "it-IT", "ru": "ru-RU", "id": "id-ID", "tr": "tr-TR", "ne": "ne-NP"}

NAMES = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish (Hindi in Latin script)", "ta": "Tamil", "te": "Telugu",
         "bn": "Bengali", "mr": "Marathi", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "ur": "Urdu", "ar": "Arabic",
         "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "ja": "Japanese", "zh": "Chinese",
         "it": "Italian", "ru": "Russian", "id": "Indonesian", "tr": "Turkish", "ne": "Nepali", "pa": "Punjabi", "or": "Odia"}
