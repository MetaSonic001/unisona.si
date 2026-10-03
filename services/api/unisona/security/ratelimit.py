"""In-memory sliding-window rate limiter (single process; swap for Redis when scaling out)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

_hits: dict[str, deque[float]] = defaultdict(deque)


def check(key: str, limit: int, window_s: int = 60) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and q[0] < now - window_s:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests. Please slow down.")
    q.append(now)
