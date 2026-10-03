"""Shared helpers for messaging channels: secrets, debounce buffering, dedupe."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Awaitable, Callable

from ..models import Channel, Workspace
from ..security.crypto import decrypt_json, encrypt_json


def channel_secret(ws: Workspace, ch: Channel) -> dict:
    if not ch.enc_secret:
        return {}
    return decrypt_json(ws.id, ws.settings["dek"], f"channel:{ch.id}", ch.enc_secret)


def set_channel_secret(ws: Workspace, ch: Channel, data: dict) -> None:
    ch.enc_secret = encrypt_json(ws.id, ws.settings["dek"], f"channel:{ch.id}", data)


class Deduper:
    def __init__(self, size: int = 5000):
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._size = size

    def seen(self, key: str) -> bool:
        if not key:
            return False
        if key in self._seen:
            return True
        self._seen[key] = time.time()
        if len(self._seen) > self._size:
            self._seen.popitem(last=False)
        return False


class Debouncer:
    """Merge rapid consecutive messages from one sender into a single turn."""

    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self._buf: dict[str, list[str]] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def push(self, key: str, text: str, flush: Callable[[str], Awaitable[None]]) -> None:
        self._buf.setdefault(key, []).append(text)
        if key in self._tasks and not self._tasks[key].done():
            self._tasks[key].cancel()

        async def run():
            try:
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                return
            texts = self._buf.pop(key, [])
            self._tasks.pop(key, None)
            if texts:
                await flush("\n".join(texts))

        self._tasks[key] = asyncio.create_task(run())
