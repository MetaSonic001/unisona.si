"""Download ML models at build time: `uv run python -m unisona.prefetch`.

Hosted builds (Render) keep files written during the build, but the runtime disk is wiped on every deploy.
Fetching the embedding model and reranker here means a fresh instance starts serving in seconds instead of
downloading ~400 MB on each boot. Safe to run repeatedly; already-cached models are skipped.
"""
from __future__ import annotations

import sys
import time

from .config import settings
from .log import get_logger, setup_logging


def main() -> int:
    setup_logging()
    log = get_logger("prefetch")
    t0 = time.perf_counter()
    try:
        from fastembed import TextEmbedding

        TextEmbedding(model_name=settings.embedding_model, cache_dir=str(settings.data_path / "models"))
        log.info(f"Embedding model cached: {settings.embedding_model}")
        if settings.reranker_enabled:
            from flashrank import Ranker

            Ranker(model_name="ms-marco-MultiBERT-L-12", cache_dir=str(settings.data_path / "models"))
            log.info("Reranker cached")
        from pipecat.audio.vad.silero import SileroVADAnalyzer

        SileroVADAnalyzer()
        log.info("Silero VAD ready")
    except Exception:
        log.error("Model prefetch failed (the API will download models on first start instead)", exc_info=True)
        return 0  # never fail the build for this
    log.info(f"Models ready in {time.perf_counter() - t0:.0f}s at {settings.data_path / 'models'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
