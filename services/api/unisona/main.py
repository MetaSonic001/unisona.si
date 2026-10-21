"""Entry point: `uv run python -m unisona.main` (or `pnpm dev:api` from the repo root)."""
from __future__ import annotations

import sys

import uvicorn

from .config import settings
from .log import console, setup_logging


def _exit_with_dev_runner() -> None:
    """`pnpm dev` starts the API in its own process group (see scripts/dev.mjs). If the runner is killed hard,
    stop too, so no orphan keeps port 8000 busy."""
    import os
    import threading
    import time

    parent = os.environ.get("UNISONA_DEV_PARENT_PID", "")
    if not parent.isdigit():
        return
    try:
        import psutil
    except ImportError:
        return

    def watch() -> None:
        while psutil.pid_exists(int(parent)):
            time.sleep(2)
        for child in psutil.Process().children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        os._exit(0)

    threading.Thread(target=watch, name="dev-parent-watch", daemon=True).start()


def main() -> None:
    setup_logging()
    _exit_with_dev_runner()
    reload = "--reload" in sys.argv
    console.print(f"[bold magenta]◆ Unisona API[/bold magenta] starting on port {settings.api_port} (env={settings.unisona_env}, reload={reload})")
    hosted = not settings.is_dev
    try:
        uvicorn.run("unisona.app:app", host="0.0.0.0", port=settings.api_port, reload=reload, log_level="warning",
                    reload_dirs=["unisona"] if reload else None, ws="websockets",
                    # Behind Render's proxy the real client IP is in X-Forwarded-For (used by rate limits).
                    # Only trusted when hosted: locally the dev-token loopback check must see the raw socket address.
                    proxy_headers=True, forwarded_allow_ips="*" if hosted else "127.0.0.1",
                    timeout_keep_alive=75 if hosted else 5, timeout_graceful_shutdown=20)
    except Exception:
        import logging

        logging.getLogger("unisona.api").critical("API crashed during startup", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
