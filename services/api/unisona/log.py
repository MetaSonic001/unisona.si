"""Console logging: readable, colourful, one logger per subsystem.

`get_logger("rag")` returns a stdlib logger rendered through Rich. Subsystem names are
short tags so a busy console stays scannable: [api] [db] [rag] [voice] [worker] ...
`feature_unavailable()` prints a warning at most once per feature so a missing key
never spams the console or crashes a request.
"""
from __future__ import annotations

import logging
import sys
import threading

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

console = Console(stderr=False, highlight=False, soft_wrap=True)
_configured = False
_warned: set[str] = set()
_lock = threading.Lock()


def setup_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    handler = RichHandler(
        console=console,
        show_path=False,
        rich_tracebacks=True,
        markup=False,
        log_time_format="%H:%M:%S",
    )
    logging.basicConfig(level=level, format="%(message)s", handlers=[handler], force=True)
    for noisy in ("httpx", "httpcore", "chromadb", "bm25s", "flashrank", "edge_tts", "mcp", "sse_starlette", "aiortc", "aioice", "urllib3", "asyncio", "multipart", "watchfiles", "onnxruntime"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    try:  # Pipecat logs through loguru; route it to our console at INFO.
        from loguru import logger as _loguru

        _loguru.remove()
        _loguru.add(sys.stderr, level="WARNING", format="<dim>{time:HH:mm:ss}</dim> <level>[pipecat] {message}</level>")
    except Exception:
        pass
    _configured = True


class _Tagged(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{self.extra['tag']}] {msg}", kwargs


def get_logger(tag: str) -> logging.LoggerAdapter:
    return _Tagged(logging.getLogger(f"unisona.{tag}"), {"tag": tag})


def feature_unavailable(feature: str, env_hint: str, detail: str = "") -> None:
    """Warn once that a feature was skipped because its key is missing."""
    key = f"{feature}|{env_hint}"
    with _lock:
        if key in _warned:
            return
        _warned.add(key)
    extra = f" ({detail})" if detail else ""
    get_logger("features").warning(
        f"SKIPPED: {feature} is not available. Add {env_hint} to .env or to the workspace's Providers page to enable it{extra}."
    )


def banner(title: str, rows: list[tuple[str, str, str]]) -> None:
    table = Table(title=title, show_lines=False, header_style="bold", title_style="bold magenta")
    table.add_column("Feature")
    table.add_column("Status")
    table.add_column("Enable with / note", style="dim")
    for name, status, note in rows:
        table.add_row(name, status, note)
    console.print(table)


def step(msg: str, ok: bool | None = None) -> None:
    icon = {True: "[green]✔[/green]", False: "[red]✖[/red]", None: "[cyan]…[/cyan]"}[ok]
    console.print(f"{icon} {msg}")
