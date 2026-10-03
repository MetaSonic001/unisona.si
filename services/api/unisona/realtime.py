"""In-process pub/sub for live dashboards and chat sessions.

Topics: workspace-wide (`ws_id`) for inbox/monitor/notifications, and per conversation
(`conv:<id>`) so a widget visitor receives human-agent replies instantly. Single
process today; swap `publish` for Postgres NOTIFY or Redis when running several API
instances.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from .log import get_logger

log = get_logger("realtime")


class Hub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs[topic].add(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        self._subs[topic].discard(q)
        if not self._subs[topic]:
            self._subs.pop(topic, None)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        for q in list(self._subs.get(topic, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def listeners(self, topic: str) -> int:
        return len(self._subs.get(topic, ()))


hub = Hub()
