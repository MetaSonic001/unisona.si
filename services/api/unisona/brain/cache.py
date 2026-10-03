"""Tiny TTL caches for hot-path data (agent setup, contact briefs).

Every database round-trip costs ~100ms+ against a remote Postgres, so per-turn reads that
rarely change are cached briefly. Writes that change them call `invalidate_*`.
"""
from __future__ import annotations

import time
from typing import Any

_store: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Any | None:
    hit = _store.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    _store.pop(key, None)
    return None


def put(key: str, value: Any, ttl: float) -> Any:
    _store[key] = (time.monotonic() + ttl, value)
    if len(_store) > 5000:
        now = time.monotonic()
        for k in [k for k, (exp, _) in _store.items() if exp < now]:
            _store.pop(k, None)
    return value


def invalidate_prefix(prefix: str) -> None:
    for k in [k for k in _store if k.startswith(prefix)]:
        _store.pop(k, None)
