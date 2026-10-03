"""PII redaction for stored transcripts and logs (opt-in per workspace)."""
from __future__ import annotations

import re

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(?:\d[ -]?){9,11}\d(?!\d)")),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
]


def redact(text: str, kinds: set[str] | None = None) -> str:
    out = text or ""
    for label, rx in _RULES:
        if kinds and label not in kinds:
            continue
        out = rx.sub(f"[{label}]", out)
    return out
