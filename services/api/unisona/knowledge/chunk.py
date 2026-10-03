"""Structure-aware chunking.

Split on markdown headings first so a chunk never straddles two sections, then pack
paragraphs up to ~1,000 characters with a small overlap. Each chunk carries a
contextual header (document title + heading path), which measurably improves
retrieval for short chunks like FAQ answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TARGET = 1000
OVERLAP = 150
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class ChunkText:
    text: str
    heading: str
    ordinal: int


def _sections(markdown: str) -> list[tuple[list[str], str]]:
    path: list[str] = []
    sections: list[tuple[list[str], str]] = []
    buf: list[str] = []
    for line in markdown.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            if buf:
                sections.append((list(path), "\n".join(buf).strip()))
                buf = []
            level = len(m.group(1))
            path = path[: level - 1] + [m.group(2).strip()]
        else:
            buf.append(line)
    if buf:
        sections.append((list(path), "\n".join(buf).strip()))
    return [(p, t) for p, t in sections if t]


def _pack(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[str] = []
    cur = ""
    for p in paras:
        if len(p) > TARGET * 1.5:  # very long paragraph: split by sentence
            sentences = re.split(r"(?<=[.!?।])\s+", p)
            for s in sentences:
                if len(cur) + len(s) > TARGET and cur:
                    out.append(cur)
                    cur = cur[-OVERLAP:] + " " + s
                else:
                    cur = (cur + " " + s).strip()
            continue
        if len(cur) + len(p) > TARGET and cur:
            out.append(cur)
            cur = cur[-OVERLAP:] + "\n\n" + p
        else:
            cur = (cur + "\n\n" + p).strip()
    if cur.strip():
        out.append(cur)
    return out


def chunk_markdown(markdown: str, title: str) -> list[ChunkText]:
    chunks: list[ChunkText] = []
    for path, body in _sections(markdown) or [([], markdown)]:
        heading = " › ".join(path)
        for piece in _pack(body):
            header = f"[{title}{' › ' + heading if heading else ''}]"
            chunks.append(ChunkText(text=f"{header}\n{piece}", heading=heading, ordinal=len(chunks)))
    return chunks
