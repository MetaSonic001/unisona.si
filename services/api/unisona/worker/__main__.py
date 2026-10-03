"""Standalone worker: `uv run python -m unisona.worker` (use with RUN_WORKER=false on the API)."""
from __future__ import annotations

import asyncio
import signal

from ..log import console, setup_logging
from .jobs import scheduler_loop
from .queue import worker_loop


async def _main() -> None:
    setup_logging()
    console.rule("[bold magenta]Unisona worker")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    await asyncio.gather(worker_loop(stop), scheduler_loop(stop))


if __name__ == "__main__":
    asyncio.run(_main())
