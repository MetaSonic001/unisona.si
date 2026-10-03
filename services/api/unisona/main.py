"""Entry point: `uv run python -m unisona.main` (or `pnpm dev:api` from the repo root)."""
from __future__ import annotations

import sys

import uvicorn

from .config import settings
from .log import console, setup_logging


def main() -> None:
    setup_logging()
    reload = "--reload" in sys.argv
    console.print(f"[bold magenta]◆ Unisona API[/bold magenta] starting on port {settings.api_port} (env={settings.unisona_env}, reload={reload})")
    uvicorn.run("unisona.app:app", host="0.0.0.0", port=settings.api_port, reload=reload, log_level="warning",
                reload_dirs=["unisona"] if reload else None, ws="websockets")


if __name__ == "__main__":
    main()
